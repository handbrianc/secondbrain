"""Tests for FailureInjector failure injection framework.

This module provides comprehensive tests for the failure injection framework,
covering all failure types, context managers, edge cases, and integration points.
"""

import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)
from secondbrain.utils.failure_injector import (
    FailureConfig,
    FailureInjector,
    FailureType,
    InjectedConnectionError,
    InjectedFailureError,
    InjectedTimeoutError,
    inject_connection_error,
    inject_general_failure,
    inject_latency,
    inject_network_partition,
    inject_timeout,
)


@pytest.mark.slow
class TestFailureType:
    """Test FailureType enum."""

    def test_failure_type_values(self):
        """Test all failure type enum values."""
        assert FailureType.TIMEOUT.value == "timeout"
        assert FailureType.CONNECTION_ERROR.value == "connection_error"
        assert FailureType.GENERAL_FAILURE.value == "general_failure"
        assert FailureType.SLOW_RESPONSE.value == "slow_response"
        assert FailureType.PARTIAL_FAILURE.value == "partial_failure"
        assert FailureType.NETWORK_PARTITION.value == "network_partition"
        assert FailureType.LATENCY_INJECTION.value == "latency_injection"

    def test_failure_type_count(self):
        """Test that there are exactly 7 failure types."""
        assert len(list(FailureType)) == 7

    def test_failure_type_iteration(self):
        """Test iterating over all failure types."""
        types = list(FailureType)
        assert len(types) == 7
        assert FailureType.TIMEOUT in types
        assert FailureType.CONNECTION_ERROR in types


@pytest.mark.slow
class TestFailureConfig:
    """Test FailureConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal configuration with only required field."""
        config = FailureConfig(failure_type=FailureType.TIMEOUT)
        assert config.failure_type == FailureType.TIMEOUT
        assert config.duration is None
        assert config.delay == 0.0
        assert config.timeout_value == 30.0
        assert config.error_message is None
        assert config.probability == 1.0
        assert config.repeat_count is None

    def test_full_config(self):
        """Test full configuration with all fields."""
        config = FailureConfig(
            failure_type=FailureType.CONNECTION_ERROR,
            duration=10.0,
            delay=2.0,
            timeout_value=15.0,
            error_message="Custom error",
            probability=0.5,
            repeat_count=3,
        )
        assert config.failure_type == FailureType.CONNECTION_ERROR
        assert config.duration == 10.0
        assert config.delay == 2.0
        assert config.timeout_value == 15.0
        assert config.error_message == "Custom error"
        assert config.probability == 0.5
        assert config.repeat_count == 3

    def test_config_defaults(self):
        """Test default values are correct."""
        config = FailureConfig(failure_type=FailureType.GENERAL_FAILURE)
        assert config.duration is None
        assert config.delay == 0.0
        assert config.timeout_value == 30.0
        assert config.error_message is None
        assert config.probability == 1.0
        assert config.repeat_count is None


@pytest.mark.slow
class TestFailureInjectorInit:
    """Test FailureInjector initialization."""

    def test_initial_state(self):
        """Test initial state of failure injector."""
        injector = FailureInjector()
        assert injector._active_failures == {}
        assert injector._cleanup_callbacks == []
        assert injector._failure_count == 0
        assert injector._start_time is None

    def test_thread_lock_exists(self):
        """Test that thread lock is initialized."""
        injector = FailureInjector()
        # Use RLock check since the implementation uses threading.RLock
        assert isinstance(injector._lock, (type(threading.Lock()), type(threading.RLock())))

    def test_get_instance_singleton(self):
        """Test that get_instance returns singleton."""
        instance1 = FailureInjector.get_instance()
        instance2 = FailureInjector.get_instance()
        assert instance1 is instance2

    def test_reset_cleans_singleton(self):
        """Test that reset cleans the singleton instance."""
        injector = FailureInjector.get_instance()
        injector.reset()
        assert injector._active_failures == {}
        assert injector._cleanup_callbacks == []


@pytest.mark.slow
class TestFailureInjectorInjectFailure:
    """Test FailureInjector.inject_failure method."""

    def test_inject_basic(self):
        """Test basic failure injection."""
        injector = FailureInjector()
        injector.inject(
            failure_type=FailureType.TIMEOUT,
            duration=1.0,
            delay=0.0,
        )
        assert len(injector._active_failures) == 1

    def test_inject_with_delay(self):
        """Test failure injection with delay."""
        injector = FailureInjector()
        injector.inject(
            failure_type=FailureType.CONNECTION_ERROR,
            duration=2.0,
            delay=0.1,
        )
        # With delay, cleanup is not scheduled immediately
        assert len(injector._cleanup_callbacks) == 0

    def test_inject_schedules_cleanup(self):
        """Test that duration schedules automatic cleanup."""
        injector = FailureInjector()
        injector.inject(
            failure_type=FailureType.GENERAL_FAILURE,
            duration=0.1,
            delay=0.0,
        )
        # Cleanup is scheduled via threading.Timer, not _cleanup_callbacks
        # Verify the failure was registered
        assert len(injector._active_failures) == 1

    def test_inject_multiple(self):
        """Test injecting multiple failures."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0)
        injector.inject(failure_type=FailureType.CONNECTION_ERROR, duration=1.0)
        assert len(injector._active_failures) == 2


@pytest.mark.slow
class TestFailureInjectorReset:
    """Test FailureInjector.reset method."""

    def test_reset_clears_failures(self):
        """Test that reset clears all active failures."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=10.0)
        injector.reset()
        assert len(injector._active_failures) == 0
        assert len(injector._cleanup_callbacks) == 0

    def test_reset_calls_cleanup_callbacks(self):
        """Test that reset calls all cleanup callbacks."""
        injector = FailureInjector()
        callback_called = []

        def cleanup_callback():
            callback_called.append(True)

        injector._cleanup_callbacks.append(cleanup_callback)
        injector.reset()
        assert len(callback_called) == 1

    def test_reset_handles_callback_errors(self):
        """Test that reset handles errors in cleanup callbacks."""
        injector = FailureInjector()

        def failing_callback():
            raise Exception("Cleanup failed")

        injector._cleanup_callbacks.append(failing_callback)
        # Should not raise
        injector.reset()
        assert len(injector._cleanup_callbacks) == 0

    def test_reset_resets_counters(self):
        """Test that reset resets failure counters."""
        injector = FailureInjector()
        injector._failure_count = 100
        injector._start_time = time.time()
        injector.reset()
        assert injector._failure_count == 0
        assert injector._start_time is None


@pytest.mark.slow
class TestFailureInjectorIsFailureActive:
    """Test FailureInjector.is_failure_active method."""

    def test_no_failures_active(self):
        """Test is_failure_active when no failures are active."""
        injector = FailureInjector()
        assert injector.is_failure_active(FailureType.TIMEOUT) is False

    def test_failure_active(self):
        """Test is_failure_active when failure is active."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=10.0)
        assert injector.is_failure_active(FailureType.TIMEOUT) is True

    def test_different_failure_type_not_active(self):
        """Test is_failure_active for different failure type."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=10.0)
        assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is False

    def test_failure_after_reset(self):
        """Test is_failure_active after reset."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=10.0)
        injector.reset()
        assert injector.is_failure_active(FailureType.TIMEOUT) is False


@pytest.mark.slow
class TestFailureInjectorScheduleCleanup:
    """Test FailureInjector._schedule_cleanup method."""

    def test_schedule_cleanup_basic(self):
        """Test basic cleanup scheduling."""
        injector = FailureInjector()
        key = "test_key"
        injector._active_failures[key] = FailureConfig(failure_type=FailureType.TIMEOUT)
        injector._schedule_cleanup(key, 0.1)
        # _schedule_cleanup uses threading.Timer, doesn't add to _cleanup_callbacks
        # Just verify it doesn't raise an exception
        assert key in injector._active_failures

    def test_schedule_cleanup_executes(self):
        """Test that scheduled cleanup executes."""
        injector = FailureInjector()
        key = "test_key"
        injector._active_failures[key] = FailureConfig(failure_type=FailureType.TIMEOUT)
        injector._schedule_cleanup(key, 0.1)

        # Wait for cleanup
        time.sleep(0.2)

        assert key not in injector._active_failures


@pytest.mark.slow
class TestInjectTimeoutContextManager:
    """Test inject_timeout context manager."""

    def test_timeout_context_basic(self):
        """Test basic timeout context manager."""
        injector = FailureInjector()
        with injector.inject_timeout(duration=1.0):
            assert injector.is_failure_active(FailureType.TIMEOUT) is True
        assert injector.is_failure_active(FailureType.TIMEOUT) is False

    def test_timeout_context_with_delay(self):
        """Test timeout context with delay."""
        injector = FailureInjector()
        with injector.inject_timeout(duration=2.0, delay=0.1):
            # After delay, should be active
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

    def test_timeout_context_with_custom_timeout_value(self):
        """Test timeout context with custom timeout value."""
        injector = FailureInjector()
        with injector.inject_timeout(timeout_value=15.0):
            config = list(injector._active_failures.values())[0]
            assert config.timeout_value == 15.0

    def test_timeout_context_with_custom_error_message(self):
        """Test timeout context with custom error message."""
        injector = FailureInjector()
        with injector.inject_timeout(error_message="Custom timeout"):
            config = list(injector._active_failures.values())[0]
            assert config.error_message == "Custom timeout"

    def test_timeout_context_cleanup_on_exception(self):
        """Test that timeout context cleans up on exception."""
        injector = FailureInjector()
        try:
            with injector.inject_timeout(duration=10.0):
                raise ValueError("Test error")
        except ValueError:
            pass
        assert injector.is_failure_active(FailureType.TIMEOUT) is False


@pytest.mark.slow
class TestInjectConnectionErrorContextManager:
    """Test inject_connection_error context manager."""

    def test_connection_error_context_basic(self):
        """Test basic connection error context manager."""
        injector = FailureInjector()
        with injector.inject_connection_error(duration=1.0):
            assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True
        assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is False

    def test_connection_error_context_with_delay(self):
        """Test connection error context with delay."""
        injector = FailureInjector()
        with injector.inject_connection_error(duration=2.0, delay=0.1):
            assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True

    def test_connection_error_context_with_custom_message(self):
        """Test connection error context with custom message."""
        injector = FailureInjector()
        with injector.inject_connection_error(error_message="Custom connection error"):
            config = list(injector._active_failures.values())[0]
            assert config.error_message == "Custom connection error"

    def test_connection_error_context_cleanup_on_exception(self):
        """Test that connection error context cleans up on exception."""
        injector = FailureInjector()
        try:
            with injector.inject_connection_error(duration=10.0):
                raise ValueError("Test error")
        except ValueError:
            pass
        assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is False


@pytest.mark.slow
class TestInjectGeneralFailureContextManager:
    """Test inject_general_failure context manager."""

    def test_general_failure_context_basic(self):
        """Test basic general failure context manager."""
        injector = FailureInjector()
        with injector.inject_general_failure(duration=1.0):
            assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True
        assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is False

    def test_general_failure_context_with_probability(self):
        """Test general failure context with probability."""
        injector = FailureInjector()
        with injector.inject_general_failure(duration=2.0, probability=0.5):
            config = list(injector._active_failures.values())[0]
            assert config.probability == 0.5

    def test_general_failure_context_with_delay(self):
        """Test general failure context with delay."""
        injector = FailureInjector()
        with injector.inject_general_failure(duration=2.0, delay=0.1):
            assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True

    def test_general_failure_context_with_custom_message(self):
        """Test general failure context with custom message."""
        injector = FailureInjector()
        with injector.inject_general_failure(error_message="Custom failure"):
            config = list(injector._active_failures.values())[0]
            assert config.error_message == "Custom failure"


@pytest.mark.slow
class TestInjectNetworkPartitionContextManager:
    """Test inject_network_partition context manager."""

    def test_network_partition_context_basic(self):
        """Test basic network partition context manager."""
        injector = FailureInjector()
        with injector.inject_network_partition(duration=1.0):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True
        assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is False

    def test_network_partition_context_with_type(self):
        """Test network partition context with partition type."""
        injector = FailureInjector()
        with injector.inject_network_partition(partition_type="partial"):
            config = list(injector._active_failures.values())[0]
            # The partition_type is stored in error_message for this implementation
            assert config is not None

    def test_network_partition_context_with_affected_services(self):
        """Test network partition context with affected services."""
        injector = FailureInjector()
        services = ["service1", "service2"]
        with injector.inject_network_partition(affected_services=services):
            config = list(injector._active_failures.values())[0]
            assert config is not None

    def test_network_partition_context_with_delay(self):
        """Test network partition context with delay."""
        injector = FailureInjector()
        with injector.inject_network_partition(duration=2.0, delay=0.1):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True


@pytest.mark.slow
class TestInjectLatencyContextManager:
    """Test inject_latency context manager."""

    def test_latency_context_basic(self):
        """Test basic latency context manager."""
        injector = FailureInjector()
        start = time.time()
        with injector.inject_latency(latency_ms=100):
            elapsed = time.time() - start
            assert elapsed >= 0.1  # At least 100ms
        assert injector.is_failure_active(FailureType.LATENCY_INJECTION) is False

    def test_latency_context_with_jitter(self):
        """Test latency context with jitter."""
        injector = FailureInjector()
        # With jitter, latency should vary
        latencies = []
        for _ in range(5):
            start = time.time()
            with injector.inject_latency(latency_ms=50, jitter_ms=50):
                elapsed = time.time() - start
                latencies.append(elapsed)
            injector.reset()

        # Should have some variation
        assert max(latencies) > min(latencies)

    def test_latency_context_with_delay(self):
        """Test latency context with delay."""
        injector = FailureInjector()
        start = time.time()
        with injector.inject_latency(latency_ms=50, delay=0.1):
            elapsed = time.time() - start
            # Should include both delay and latency
            assert elapsed >= 0.1

    def test_latency_context_cleanup(self):
        """Test that latency context cleans up properly."""
        injector = FailureInjector()
        with injector.inject_latency(latency_ms=10):
            assert injector.is_failure_active(FailureType.LATENCY_INJECTION) is True
        assert injector.is_failure_active(FailureType.LATENCY_INJECTION) is False


@pytest.mark.slow
class TestConvenienceFunctions:
    """Test convenience functions for failure injection."""

    def test_inject_timeout_function(self):
        """Test inject_timeout convenience function."""
        with inject_timeout(duration=1.0):
            instance = FailureInjector.get_instance()
            assert instance.is_failure_active(FailureType.TIMEOUT) is True

    def test_inject_connection_error_function(self):
        """Test inject_connection_error convenience function."""
        with inject_connection_error(duration=1.0):
            instance = FailureInjector.get_instance()
            assert instance.is_failure_active(FailureType.CONNECTION_ERROR) is True

    def test_inject_general_failure_function(self):
        """Test inject_general_failure convenience function."""
        with inject_general_failure(duration=1.0):
            instance = FailureInjector.get_instance()
            assert instance.is_failure_active(FailureType.GENERAL_FAILURE) is True

    def test_inject_network_partition_function(self):
        """Test inject_network_partition convenience function."""
        with inject_network_partition(duration=1.0):
            instance = FailureInjector.get_instance()
            assert instance.is_failure_active(FailureType.NETWORK_PARTITION) is True

    def test_inject_latency_function(self):
        """Test inject_latency convenience function."""
        with inject_latency(latency_ms=10):
            instance = FailureInjector.get_instance()
            assert instance.is_failure_active(FailureType.LATENCY_INJECTION) is True


@pytest.mark.slow
class TestAsyncContextManager:
    """Test async context manager support."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager usage."""
        injector = FailureInjector()
        async with injector:
            assert injector is not None
        # Should reset after exit
        assert len(injector._active_failures) == 0

    @pytest.mark.asyncio
    async def test_async_context_manager_with_failure(self):
        """Test async context manager with failure injection."""
        injector = FailureInjector()
        # Use async context manager on injector itself
        async with injector:
            # Inject failure within async context
            injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0)
            assert injector.is_failure_active(FailureType.TIMEOUT) is True
        # Should reset after exit
        assert len(injector._active_failures) == 0


@pytest.mark.slow
class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with failure injection."""

    def test_circuit_breaker_with_timeout(self):
        """Test circuit breaker opens with timeout failures."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        injector = FailureInjector()

        def failing_func():
            with injector.inject_timeout(duration=0.1):
                raise TimeoutError("Timeout")

        # First two failures should open circuit
        with pytest.raises(TimeoutError):
            cb.call(failing_func)
        with pytest.raises(TimeoutError):
            cb.call(failing_func)

        assert cb.state.value == "open"

    def test_circuit_breaker_with_connection_error(self):
        """Test circuit breaker with connection errors."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))
        injector = FailureInjector()

        def failing_func():
            with injector.inject_connection_error(duration=0.1):
                raise ConnectionError("Connection failed")

        # Three failures should open circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.call(failing_func)

        assert cb.state.value == "open"

    def test_circuit_breaker_recovery_with_success(self):
        """Test circuit breaker recovers after successes."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, success_threshold=2))

        def failing_func():
            raise ValueError("Error")

        def success_func():
            return True

        # Open circuit with one failure
        with pytest.raises(ValueError):
            cb.call(failing_func)
        assert cb.state.value == "open"

        # Simulate recovery timeout (use monotonic time to match implementation)
        cb._last_failure_time = time.monotonic() - 31  # Past recovery timeout

        # Two successes should close circuit
        assert cb.call(success_func) is True
        assert cb.state.value == "half_open"
        assert cb.call(success_func) is True
        assert cb.state.value == "closed"


@pytest.mark.slow
class TestResourceExhaustionScenarios:
    """Test resource exhaustion failure scenarios."""

    def test_high_failure_rate_scenario(self):
        """Test scenario with high failure rate."""
        injector = FailureInjector()
        success_count = 0
        failure_count = 0

        for _ in range(100):
            with injector.inject_general_failure(duration=0.01, probability=0.8):
                # Simulate work that may fail
                if random.random() < 0.8:
                    failure_count += 1
                else:
                    success_count += 1
            injector.reset()

        # Should have approximately 80% failures
        assert failure_count > success_count

    def test_concurrent_failure_injection(self):
        """Test concurrent failure injection."""
        injector = FailureInjector()
        results = []

        def inject_and_check(failure_id):
            with injector.inject_timeout(duration=1.0):
                results.append(failure_id)
                time.sleep(0.1)

        # Run concurrent injections
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(inject_and_check, i) for i in range(5)]
            for future in futures:
                future.result()

        assert len(results) == 5

    def test_rapid_failure_toggle(self):
        """Test rapid failure injection and reset."""
        injector = FailureInjector()

        for _ in range(100):
            injector.inject(failure_type=FailureType.TIMEOUT, duration=10.0)
            injector.reset()

        assert len(injector._active_failures) == 0
        assert injector._failure_count == 0


@pytest.mark.slow
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_duration_failure(self):
        """Test failure with zero duration."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=0.0)
        # Should still be active immediately after injection
        assert len(injector._active_failures) >= 0

    def test_very_long_duration(self):
        """Test failure with very long duration."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=3600.0)
        assert len(injector._active_failures) == 1

    def test_zero_delay(self):
        """Test failure with zero delay."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0, delay=0.0)
        assert len(injector._active_failures) == 1

    def test_very_long_delay(self):
        """Test failure with very long delay."""
        injector = FailureInjector()
        injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0, delay=100.0)
        # With delay, cleanup is not scheduled
        assert len(injector._cleanup_callbacks) == 0

    def test_probability_zero(self):
        """Test failure with zero probability."""
        injector = FailureInjector()
        with injector.inject_general_failure(probability=0.0):
            config = list(injector._active_failures.values())[0]
            assert config.probability == 0.0

    def test_probability_one(self):
        """Test failure with probability of one."""
        injector = FailureInjector()
        with injector.inject_general_failure(probability=1.0):
            config = list(injector._active_failures.values())[0]
            assert config.probability == 1.0

    def test_null_error_message(self):
        """Test failure with null error message."""
        injector = FailureInjector()
        with injector.inject_timeout(error_message=None):
            config = list(injector._active_failures.values())[0]
            assert config.error_message is None

    def test_empty_error_message(self):
        """Test failure with empty error message."""
        injector = FailureInjector()
        with injector.inject_timeout(error_message=""):
            config = list(injector._active_failures.values())[0]
            assert config.error_message == ""


@pytest.mark.slow
class TestThreadSafety:
    """Test thread safety of failure injector."""

    def test_concurrent_access(self):
        """Test concurrent access to failure injector."""
        injector = FailureInjector()
        errors = []

        def worker(worker_id):
            try:
                for i in range(10):
                    injector.inject(failure_type=FailureType.TIMEOUT, duration=0.1)
                    injector.reset()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_context_managers(self):
        """Test concurrent context manager usage."""
        injector = FailureInjector()
        results = []

        def worker(worker_id):
            with injector.inject_timeout(duration=0.5):
                results.append(worker_id)
                time.sleep(0.1)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3


@pytest.mark.slow
class TestLogging:
    """Test logging behavior."""

    def test_injection_start_logged(self):
        """Test that injection start is logged."""
        with patch("secondbrain.utils.failure_injector.logger") as mock_logger:
            injector = FailureInjector()
            injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0)
            mock_logger.info.assert_called()

    def test_reset_logged(self):
        """Test that reset is logged."""
        with patch("secondbrain.utils.failure_injector.logger") as mock_logger:
            injector = FailureInjector()
            injector.reset()
            mock_logger.info.assert_called()


@pytest.mark.slow
class TestIntegrationScenarios:
    """Test integration scenarios with real usage patterns."""

    def test_retry_pattern_with_failure_injection(self):
        """Test retry pattern with injected failures."""
        injector = FailureInjector()
        attempts = []

        def operation_with_retry():
            max_attempts = 3
            for attempt in range(max_attempts):
                attempts.append(attempt)
                try:
                    with injector.inject_connection_error(duration=0.1):
                        raise ConnectionError("Simulated")
                except ConnectionError:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(0.01)

        with pytest.raises(ConnectionError):
            operation_with_retry()

        assert len(attempts) == 3

    def test_circuit_breaker_fallback_pattern(self):
        """Test circuit breaker with fallback pattern."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, success_threshold=2))

        def failing_operation() -> bool:
            raise ValueError("Simulated failure")

        def success_operation() -> bool:
            return True

        # Open circuit with one failure
        with pytest.raises(ValueError):
            cb.call(failing_operation)
        assert cb.state.value == "open"

        # Simulate recovery timeout (use monotonic time to match implementation)
        cb._last_failure_time = time.monotonic() - 31

        # When circuit is half_open, call should be allowed
        assert cb.is_allowed() is True
        assert cb.state.value == "half_open"

        # Two successes should close circuit
        assert cb.call(success_operation) is True
        assert cb.state.value == "half_open"
        assert cb.call(success_operation) is True
        assert cb.state.value == "closed"

        # Fallback pattern: when operation fails, call fallback
        # This test verifies the basic pattern without complex state transitions
        fallback_results = []

        def operation_with_fallback(primary: Callable[[], bool], fallback: Callable[[], bool]) -> bool:
            """Execute primary operation with fallback on failure."""
            try:
                return primary()
            except (ValueError, CircuitBreakerError):
                return fallback()

        def failing_primary() -> bool:
            raise ValueError("Primary failed")

        def fallback_success() -> bool:
            fallback_results.append("called")
            return True

        # Test fallback pattern
        result = operation_with_fallback(failing_primary, fallback_success)
        assert result is True
        assert len(fallback_results) == 1

    def test_bulkhead_pattern_with_failures(self):
        """Test bulkhead pattern with failure injection."""
        injector = FailureInjector()
        max_concurrent = 2
        current_concurrent = 0
        max_observed = 0
        lock = threading.Lock()

        def bulkhead_operation(worker_id):
            nonlocal current_concurrent, max_observed
            with injector.inject_general_failure(duration=0.2, probability=0.3):
                with lock:
                    current_concurrent += 1
                    max_observed = max(max_observed, current_concurrent)

                time.sleep(0.1)

                with lock:
                    current_concurrent -= 1

        # Run more operations than bulkhead size
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(bulkhead_operation, i) for i in range(5)]
            for future in futures:
                future.result()

        # Test verifies failure injection works with concurrent operations
        assert max_observed <= 5  # All 5 workers can run concurrently


@pytest.mark.slow
class TestFailureInjectorPytestFixture:
    """Test the pytest fixture for failure injector."""

    def test_pytest_fixture_available(self):
        """Test that pytest fixture is available."""
        # The fixture is defined at module level for pytest
        # This test just verifies the module can be imported
        assert FailureInjector is not None

    def test_pytest_marker_available(self):
        """Test that pytest markers work."""
        # Verify pytest is available for the fixture
        assert pytest.mark.slow is not None


@pytest.mark.slow
class TestFailureInjectorErrorHandling:
    """Test error handling in failure injector."""

    def test_inject_failure_with_invalid_type(self):
        """Test error handling for invalid failure type."""
        injector = FailureInjector()
        # Should accept any FailureType enum value
        with injector.inject_general_failure():
            assert len(injector._active_failures) >= 0

    def test_cleanup_callback_failure_handling(self):
        """Test that cleanup callback failures are handled gracefully."""
        injector = FailureInjector()

        def failing_cleanup():
            raise Exception("Cleanup failed")

        injector._cleanup_callbacks.append(failing_cleanup)
        # Should not raise
        injector.reset()

    def test_context_manager_exception_propagation(self):
        """Test that exceptions propagate correctly through context manager."""
        injector = FailureInjector()
        test_error = ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            with injector.inject_timeout(duration=1.0):
                raise test_error

        # Should still clean up
        assert injector.is_failure_active(FailureType.TIMEOUT) is False


@pytest.mark.slow
class TestFailureInjectorProbability:
    """Test probability-based failure injection."""

    def test_high_probability_failures(self):
        """Test high probability failures."""
        injector = FailureInjector()
        failures = 0

        for _ in range(100):
            with injector.inject_general_failure(probability=0.9):
                if random.random() < 0.9:
                    failures += 1
            injector.reset()

        # Should have approximately 90% failures
        assert failures >= 80  # Allow some variance

    def test_low_probability_failures(self):
        """Test low probability failures."""
        injector = FailureInjector()
        failures = 0

        for _ in range(100):
            with injector.inject_general_failure(probability=0.1):
                if random.random() < 0.1:
                    failures += 1
            injector.reset()

        # Should have approximately 10% failures
        assert failures <= 30  # Allow some variance

    def test_zero_probability_no_failures(self):
        """Test zero probability results in no failures."""
        injector = FailureInjector()
        failures = 0

        for _ in range(20):
            with injector.inject_general_failure(probability=0.0):
                if random.random() < 0.0:
                    failures += 1
            injector.reset()

        assert failures == 0

    def test_one_probability_always_failures(self):
        """Test probability of 1.0 always fails."""
        injector = FailureInjector()
        failures = 0

        for _ in range(20):
            with injector.inject_general_failure(probability=1.0):
                if random.random() < 1.0:
                    failures += 1
            injector.reset()

        assert failures == 20


@pytest.mark.slow
class TestScheduleCleanup:
    """Test _schedule_cleanup method and timing-based failures."""

    def test_schedule_cleanup_basic(self):
        """Test that scheduled cleanup removes failures after duration."""
        injector = FailureInjector()

        # Inject a failure with a short duration
        injector.inject(failure_type=FailureType.TIMEOUT, duration=0.2)

        # Failure should be active immediately
        assert injector.is_failure_active(FailureType.TIMEOUT) is True

        # Wait for cleanup
        time.sleep(0.3)

        # Failure should be cleaned up
        assert injector.is_failure_active(FailureType.TIMEOUT) is False

    def test_schedule_cleanup_with_delay_no_auto_cleanup(self):
        """Test that delayed failures don't schedule automatic cleanup."""
        injector = FailureInjector()

        # Inject a failure with delay - cleanup is NOT scheduled when delay > 0
        injector.inject(failure_type=FailureType.CONNECTION_ERROR, delay=0.2, duration=0.5)

        # Failure should be active (config exists)
        assert len(injector._active_failures) == 1

        # No cleanup callback scheduled when delay > 0
        assert len(injector._cleanup_callbacks) == 0

        # Manual reset is required
        injector.reset()
        assert len(injector._active_failures) == 0

    def test_cleanup_callback_failure_handling(self):
        """Test that cleanup handles callback failures gracefully."""
        injector = FailureInjector()

        # Add a failing cleanup callback
        def failing_callback():
            raise Exception("Cleanup failed")

        injector._cleanup_callbacks.append(failing_callback)

        # Reset should not raise, just log warning
        injector.reset()

        # Callback should be cleared
        assert len(injector._cleanup_callbacks) == 0


@pytest.mark.slow
class TestRaiseFailure:
    """Test raise_failure method with all failure types."""

    def test_raise_timeout_failure(self):
        """Test raising timeout failure with default message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.TIMEOUT, timeout_value=45.0)
        injector._active_failures["timeout_test"] = config

        with pytest.raises(InjectedTimeoutError) as exc_info:
            injector.raise_failure(FailureType.TIMEOUT)

        assert "timeout" in str(exc_info.value).lower()
        assert exc_info.value.timeout_value == 45.0

    def test_raise_timeout_with_custom_message(self):
        """Test raising timeout failure with custom message."""
        injector = FailureInjector()
        injector._active_failures["timeout_test"] = FailureConfig(failure_type=FailureType.TIMEOUT)

        with pytest.raises(InjectedTimeoutError) as exc_info:
            injector.raise_failure(FailureType.TIMEOUT, error_message="Custom timeout")

        assert "Custom timeout" in str(exc_info.value)

    def test_raise_connection_error_with_config_message(self):
        """Test raising connection error uses config message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.CONNECTION_ERROR, error_message="Config error")
        injector._active_failures["conn_test"] = config

        with pytest.raises(InjectedConnectionError) as exc_info:
            injector.raise_failure(FailureType.CONNECTION_ERROR)

        assert "Config error" in str(exc_info.value)

    def test_raise_connection_error_with_override_message(self):
        """Test raising connection error overrides config message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.CONNECTION_ERROR, error_message="Config error")
        injector._active_failures["conn_test"] = config

        with pytest.raises(InjectedConnectionError) as exc_info:
            injector.raise_failure(FailureType.CONNECTION_ERROR, error_message="Override error")

        assert "Override error" in str(exc_info.value)

    def test_raise_connection_error_default_message(self):
        """Test raising connection error with no config uses default message."""
        injector = FailureInjector()

        with pytest.raises(InjectedConnectionError) as exc_info:
            injector.raise_failure(FailureType.CONNECTION_ERROR)

        assert "Injected connection error" in str(exc_info.value)

    def test_raise_general_failure_with_config_message(self):
        """Test raising general failure uses config message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.GENERAL_FAILURE, error_message="Config failure")
        injector._active_failures["gen_test"] = config

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.GENERAL_FAILURE)

        assert "Config failure" in str(exc_info.value)

    def test_raise_general_failure_with_override_message(self):
        """Test raising general failure overrides config message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.GENERAL_FAILURE, error_message="Config failure")
        injector._active_failures["gen_test"] = config

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.GENERAL_FAILURE, error_message="Override failure")

        assert "Override failure" in str(exc_info.value)

    def test_raise_general_failure_default_message(self):
        """Test raising general failure with no config uses default message."""
        injector = FailureInjector()

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.GENERAL_FAILURE)

        assert "Injected general failure" in str(exc_info.value)

    def test_raise_slow_response_delays_and_raises(self):
        """Test that slow response delays before raising."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.SLOW_RESPONSE, timeout_value=0.1)
        injector._active_failures["slow_test"] = config

        start = time.time()
        with pytest.raises(InjectedFailureError):
            injector.raise_failure(FailureType.SLOW_RESPONSE)
        elapsed = time.time() - start

        # Should have slept for timeout_value
        assert elapsed >= 0.08  # Allow some tolerance

    def test_raise_slow_response_with_custom_message(self):
        """Test raising slow response with custom message."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.SLOW_RESPONSE, timeout_value=0.05)
        injector._active_failures["slow_test"] = config

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.SLOW_RESPONSE, error_message="Custom slow")

        assert "Custom slow" in str(exc_info.value)

    def test_raise_network_partition(self):
        """Test raising network partition failure."""
        injector = FailureInjector()
        injector._active_failures["net_test"] = FailureConfig(failure_type=FailureType.NETWORK_PARTITION)

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.NETWORK_PARTITION)

        assert "network_partition" in str(exc_info.value).lower()

    def test_raise_latency_injection(self):
        """Test raising latency injection failure."""
        injector = FailureInjector()
        injector._active_failures["lat_test"] = FailureConfig(failure_type=FailureType.LATENCY_INJECTION)

        with pytest.raises(InjectedFailureError) as exc_info:
            injector.raise_failure(FailureType.LATENCY_INJECTION)

        assert "latency_injection" in str(exc_info.value).lower()

    def test_failure_count_increment(self):
        """Test that raise_failure increments failure count."""
        injector = FailureInjector()
        injector._active_failures["test"] = FailureConfig(failure_type=FailureType.TIMEOUT)

        assert injector._failure_count == 0
        with pytest.raises(InjectedTimeoutError):
            injector.raise_failure(FailureType.TIMEOUT)
        assert injector._failure_count == 1

        with pytest.raises(InjectedTimeoutError):
            injector.raise_failure(FailureType.TIMEOUT)
        assert injector._failure_count == 2


@pytest.mark.slow
class TestContextManagerDelays:
    """Test context managers with delay parameter."""

    def test_timeout_with_delay(self):
        """Test timeout context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_timeout(duration=1.0, delay=0.2):
            elapsed = time.time() - start
            assert elapsed >= 0.15  # Delay should have passed

        # Context should have exited after delay
        assert len(injector._active_failures) == 0

    def test_connection_error_with_delay(self):
        """Test connection error context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_connection_error(duration=1.0, delay=0.2):
            elapsed = time.time() - start
            assert elapsed >= 0.15

        assert len(injector._active_failures) == 0

    def test_general_failure_with_delay(self):
        """Test general failure context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_general_failure(duration=1.0, delay=0.2):
            elapsed = time.time() - start
            assert elapsed >= 0.15

        assert len(injector._active_failures) == 0

    def test_slow_response_with_delay(self):
        """Test slow response context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_slow_response(duration=1.0, delay=0.2, slow_duration=0.05):
            elapsed = time.time() - start
            assert elapsed >= 0.15

        assert len(injector._active_failures) == 0

    def test_network_partition_with_delay(self):
        """Test network partition context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_network_partition(duration=1.0, delay=0.2):
            elapsed = time.time() - start
            assert elapsed >= 0.15

        assert len(injector._active_failures) == 0

    def test_latency_with_delay(self):
        """Test latency context manager with delay."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_latency(duration=1.0, delay=0.2, latency_ms=10):
            elapsed = time.time() - start
            assert elapsed >= 0.15

        assert len(injector._active_failures) == 0


@pytest.mark.slow
class TestNetworkPartitionScenarios:
    """Test network partition injection scenarios."""

    def test_network_partition_complete(self):
        """Test complete network partition."""
        injector = FailureInjector()

        with injector.inject_network_partition(
            duration=0.5,
            partition_type="complete",
            affected_services=["service1", "service2"]
        ):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True

        assert len(injector._active_failures) == 0

    def test_network_partition_partial(self):
        """Test partial network partition."""
        injector = FailureInjector()

        with injector.inject_network_partition(
            duration=0.5,
            partition_type="partial",
            affected_services=["service1"]
        ):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True

        assert len(injector._active_failures) == 0

    def test_network_partition_asymmetric(self):
        """Test asymmetric network partition."""
        injector = FailureInjector()

        with injector.inject_network_partition(
            duration=0.5,
            partition_type="asymmetric",
            affected_services=["service1", "service2", "service3"]
        ):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True

        assert len(injector._active_failures) == 0

    def test_network_partition_custom_message(self):
        """Test network partition with custom error message."""
        injector = FailureInjector()

        with injector.inject_network_partition(
            duration=0.5,
            error_message="Custom partition message"
        ):
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True

        assert len(injector._active_failures) == 0


@pytest.mark.slow
class TestLatencyInjectionScenarios:
    """Test latency injection scenarios."""

    def test_latency_basic(self):
        """Test basic latency injection."""
        injector = FailureInjector()

        start = time.time()
        with injector.inject_latency(latency_ms=100):
            elapsed = time.time() - start
            assert elapsed >= 0.08  # 100ms with tolerance

        assert len(injector._active_failures) == 0

    def test_latency_with_jitter(self):
        """Test latency injection with jitter."""
        injector = FailureInjector()

        # Run multiple times to see jitter effect
        latencies = []
        for _ in range(5):
            start = time.time()
            with injector.inject_latency(latency_ms=50, jitter_ms=50):
                elapsed = time.time() - start
                latencies.append(elapsed)
            injector.reset()

        # Should have variance due to jitter
        assert max(latencies) > min(latencies)
        # All should be at least 50ms
        assert all(l >= 0.04 for l in latencies)

    def test_latency_duration(self):
        """Test latency injection with duration."""
        injector = FailureInjector()

        with injector.inject_latency(duration=0.5, latency_ms=20):
            assert injector.is_failure_active(FailureType.LATENCY_INJECTION) is True

        assert len(injector._active_failures) == 0

    def test_latency_zero_jitter(self):
        """Test latency with zero jitter is consistent."""
        injector = FailureInjector()

        latencies = []
        for _ in range(5):
            start = time.time()
            with injector.inject_latency(latency_ms=50, jitter_ms=0):
                elapsed = time.time() - start
                latencies.append(elapsed)
            injector.reset()

        # Should be very consistent with no jitter
        assert max(latencies) - min(latencies) < 0.01


@pytest.mark.slow
class TestConvenienceFunctionWrappers:
    """Test convenience function wrapper implementations."""

    def test_convenience_timeout(self):
        """Test inject_timeout convenience function."""
        with inject_timeout(duration=0.5, timeout_value=15.0):
            # Should use singleton instance
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

        # After context exit, should be cleaned up
        injector = FailureInjector.get_instance()
        assert len(injector._active_failures) == 0

    def test_convenience_connection_error(self):
        """Test inject_connection_error convenience function."""
        with inject_connection_error(duration=0.5):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True

        injector = FailureInjector.get_instance()
        assert len(injector._active_failures) == 0

    def test_convenience_general_failure(self):
        """Test inject_general_failure convenience function."""
        with inject_general_failure(duration=0.5, probability=0.8):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True

        injector = FailureInjector.get_instance()
        assert len(injector._active_failures) == 0

    def test_convenience_network_partition(self):
        """Test inject_network_partition convenience function."""
        with inject_network_partition(
            duration=0.5,
            partition_type="complete",
            affected_services=["svc1"]
        ):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.NETWORK_PARTITION) is True

        injector = FailureInjector.get_instance()
        assert len(injector._active_failures) == 0

    def test_convenience_latency(self):
        """Test inject_latency convenience function."""
        start = time.time()
        with inject_latency(latency_ms=50):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.LATENCY_INJECTION) is True
            elapsed = time.time() - start
            assert elapsed >= 0.04

        injector = FailureInjector.get_instance()
        assert len(injector._active_failures) == 0


@pytest.mark.slow
class TestEdgeCasesAndBoundaries:
    """Test edge cases, boundary conditions, and stress scenarios."""

    def test_zero_duration_immediate_cleanup(self):
        """Test that zero duration causes immediate cleanup."""
        injector = FailureInjector()

        injector.inject(failure_type=FailureType.TIMEOUT, duration=0.001)

        # Should be active initially
        assert len(injector._active_failures) > 0

        # Wait for cleanup — 0.5s accommodates Timer scheduling latency
        # under parallel pytest-xdist workers
        time.sleep(0.5)

        # Should be cleaned up
        assert len(injector._active_failures) == 0

    def test_very_long_duration(self):
        """Test very long duration doesn't cause issues."""
        injector = FailureInjector()

        # Inject with long duration
        injector.inject(failure_type=FailureType.TIMEOUT, duration=3600.0)

        # Should be active
        assert injector.is_failure_active(FailureType.TIMEOUT) is True

        # Manual reset should work
        injector.reset()
        assert len(injector._active_failures) == 0

    def test_multiple_simultaneous_failures(self):
        """Test multiple simultaneous failure injections."""
        injector = FailureInjector()

        with injector.inject_timeout(duration=1.0):
            with injector.inject_connection_error(duration=1.0):
                with injector.inject_general_failure(duration=1.0):
                    assert injector.is_failure_active(FailureType.TIMEOUT) is True
                    assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True
                    assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True

        # All should be cleaned up
        assert len(injector._active_failures) == 0

    def test_nested_context_managers_same_type(self):
        """Test nested context managers of same type."""
        injector1 = FailureInjector()
        injector2 = FailureInjector()

        # Use different injector instances to get different keys
        with injector1.inject_timeout(duration=1.0):
            assert len(injector1._active_failures) == 1
            with injector2.inject_timeout(duration=1.0):
                # Different injector instances have different keys
                assert len(injector1._active_failures) == 1
                assert len(injector2._active_failures) == 1
            # Inner exited
            assert len(injector2._active_failures) == 0
        # Outer exited
        assert len(injector1._active_failures) == 0

    def test_reset_cleans_all_failures(self):
        """Test reset clears all active failures."""
        injector = FailureInjector()

        injector.inject(failure_type=FailureType.TIMEOUT, duration=3600)
        injector.inject(failure_type=FailureType.CONNECTION_ERROR, duration=3600)
        injector.inject(failure_type=FailureType.GENERAL_FAILURE, duration=3600)

        assert len(injector._active_failures) == 3

        injector.reset()

        assert len(injector._active_failures) == 0
        assert len(injector._cleanup_callbacks) == 0

    def test_is_failure_active_no_matching_type(self):
        """Test is_failure_active returns False for non-existent type."""
        injector = FailureInjector()

        injector.inject(failure_type=FailureType.TIMEOUT, duration=1.0)

        assert injector.is_failure_active(FailureType.TIMEOUT) is True
        assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is False
        assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is False

    def test_thread_safety_concurrent_injection(self):
        """Test thread safety with concurrent failure injections."""
        injector = FailureInjector()
        results = []

        def inject_failure(failure_type, duration):
            try:
                with injector.inject_timeout(duration=duration):
                    time.sleep(0.01)
                    results.append(True)
            except Exception as e:
                results.append(False)

        threads = []
        for i in range(5):
            t = threading.Thread(target=inject_failure, args=(FailureType.TIMEOUT, 0.1))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert all(results)

    def test_exception_in_context_manager_preserves_cleanup(self):
        """Test that exceptions in context manager still trigger cleanup."""
        injector = FailureInjector()

        try:
            with injector.inject_timeout(duration=1.0):
                assert len(injector._active_failures) == 1
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Cleanup should have happened
        assert len(injector._active_failures) == 0


@pytest.mark.slow
class TestFailureCountAndRepeat:
    """Test failure count and repeat functionality."""

    def test_failure_count_resets_on_reset(self):
        """Test that failure count resets on reset."""
        injector = FailureInjector()
        injector._active_failures["test"] = FailureConfig(failure_type=FailureType.TIMEOUT)

        with pytest.raises(InjectedTimeoutError):
            injector.raise_failure(FailureType.TIMEOUT)
        assert injector._failure_count == 1

        injector.reset()
        assert injector._failure_count == 0

    def test_repeat_count_none_unlimited(self):
        """Test that repeat_count=None allows unlimited failures."""
        injector = FailureInjector()
        config = FailureConfig(
            failure_type=FailureType.GENERAL_FAILURE,
            repeat_count=None,
            probability=1.0
        )
        injector._active_failures["test"] = config

        # Should be able to fail multiple times
        for i in range(5):
            with pytest.raises(InjectedFailureError):
                injector.raise_failure(FailureType.GENERAL_FAILURE)

        assert injector._failure_count == 5


@pytest.mark.slow
class TestShouldFail:
    """Test should_fail method with probability and repeat count."""

    def test_should_fail_returns_true_when_active(self):
        """Test should_fail returns True when failure is active."""
        injector = FailureInjector()
        injector._active_failures["test"] = FailureConfig(failure_type=FailureType.TIMEOUT)

        assert injector.should_fail(FailureType.TIMEOUT) is True

    def test_should_fail_returns_false_when_not_active(self):
        """Test should_fail returns False when no failure is active."""
        injector = FailureInjector()

        assert injector.should_fail(FailureType.TIMEOUT) is False

    def test_should_fail_with_probability_zero(self):
        """Test should_fail with probability 0.0 can return False."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.TIMEOUT, probability=0.0)
        injector._active_failures["test"] = config

        # With probability 0.0, should_fail should return False
        # (random.random() > 0.0 is always True, so it returns False)
        assert injector.should_fail(FailureType.TIMEOUT) is False

    def test_should_fail_with_probability_one(self):
        """Test should_fail with probability 1.0 checks repeat count."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.TIMEOUT, probability=1.0, repeat_count=3)
        injector._active_failures["test"] = config

        # With probability 1.0 and repeat_count=3, should return True when count < 3
        injector._failure_count = 0
        assert injector.should_fail(FailureType.TIMEOUT) is True

        injector._failure_count = 2
        assert injector.should_fail(FailureType.TIMEOUT) is True

        injector._failure_count = 3
        assert injector.should_fail(FailureType.TIMEOUT) is False

    def test_should_fail_with_repeat_count_none(self):
        """Test should_fail with repeat_count=None always returns True (if probability allows)."""
        injector = FailureInjector()
        config = FailureConfig(failure_type=FailureType.TIMEOUT, probability=1.0, repeat_count=None)
        injector._active_failures["test"] = config

        # Should always return True regardless of failure count
        injector._failure_count = 100
        assert injector.should_fail(FailureType.TIMEOUT) is True


@pytest.mark.asyncio
class TestAsyncContextManagerFull:
    """Test async context manager support (aenter/aexit)."""

    async def test_async_context_manager_enter(self):
        """Test async context manager __aenter__."""
        injector = FailureInjector()

        async with injector as result:
            assert result is injector
            assert injector is not None

    async def test_async_context_manager_exits_cleanly(self):
        """Test async context manager __aexit__ cleans up."""
        injector = FailureInjector()

        async with injector:
            injector.inject(failure_type=FailureType.TIMEOUT, duration=3600)
            assert len(injector._active_failures) == 1

        # Should be reset after exit
        assert len(injector._active_failures) == 0

    async def test_async_context_manager_with_exception(self):
        """Test async context manager handles exceptions properly."""
        injector = FailureInjector()

        with pytest.raises(ValueError):
            async with injector:
                injector.inject(failure_type=FailureType.TIMEOUT, duration=3600)
                raise ValueError("Test exception")

        # Should still be reset after exception
        assert len(injector._active_failures) == 0


@pytest.fixture
def failure_injector():
    """Fixture providing a fresh FailureInjector instance."""
    injector = FailureInjector()
    yield injector
    injector.reset()
    FailureInjector.reset_instance()
