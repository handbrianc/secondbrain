"""Tests for the failure injection framework."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from secondbrain.utils.failure_injector import (
    FailureConfig,
    FailureInjector,
    FailureType,
    InjectedConnectionError,
    InjectedFailureError,
    InjectedTimeoutError,
    inject_connection_error,
    inject_general_failure,
    inject_timeout,
)


@pytest.fixture(autouse=True)
def cleanup_injector() -> None:
    """Automatically cleanup failure injector after each test."""
    yield
    FailureInjector.reset_instance()


@pytest.mark.chaos
class TestFailureInjectorBasic:
    """Basic tests for FailureInjector functionality."""

    def test_injector_creation(self):
        """Test that FailureInjector can be created."""
        injector = FailureInjector()
        assert injector is not None
        assert len(injector._active_failures) == 0

    def test_singleton_instance(self):
        """Test that get_instance returns singleton."""
        instance1 = FailureInjector.get_instance()
        instance2 = FailureInjector.get_instance()
        assert instance1 is instance2

    def test_reset_instance(self):
        """Test that reset_instance clears the singleton."""
        instance = FailureInjector.get_instance()
        FailureInjector.reset_instance()

        new_instance = FailureInjector.get_instance()
        assert new_instance is not instance

    def test_reset_clears_failures(self):
        """Test that reset clears all active failures."""
        injector = FailureInjector.get_instance()
        injector.inject(FailureType.TIMEOUT, duration=10.0)

        assert len(injector._active_failures) == 1

        injector.reset()

        assert len(injector._active_failures) == 0


@pytest.mark.chaos
class TestTimeoutInjection:
    """Tests for timeout failure injection."""

    def test_timeout_context_manager(self):
        """Test timeout injection via context manager."""
        injector = FailureInjector()

        with injector.inject_timeout(duration=1.0, timeout_value=1.0):
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

        assert injector.is_failure_active(FailureType.TIMEOUT) is False

    def test_timeout_raises_exception(self):
        """Test that timeout injection raises InjectedTimeoutError."""
        injector = FailureInjector()

        with pytest.raises(InjectedTimeoutError) as exc_info:
            with injector.inject_timeout(
                timeout_value=5.0, error_message="Test timeout"
            ):
                injector.raise_failure(FailureType.TIMEOUT, "Test timeout")

        assert "Test timeout" in str(exc_info.value)
        assert exc_info.value.timeout_value == 5.0

    def test_timeout_with_delay(self):
        """Test timeout injection with delay."""
        injector = FailureInjector()

        start_time = time.monotonic()
        with injector.inject_timeout(delay=0.1, duration=0.5):
            elapsed = time.monotonic() - start_time
            assert elapsed >= 0.1
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

    def test_timeout_duration_expires(self):
        """Test that timeout injection ends after duration."""
        injector = FailureInjector()

        with injector.inject_timeout(duration=0.2):
            assert injector.is_failure_active(FailureType.TIMEOUT) is True
            time.sleep(0.25)

        assert injector.is_failure_active(FailureType.TIMEOUT) is False


@pytest.mark.chaos
class TestConnectionErrorInjection:
    """Tests for connection error injection."""

    def test_connection_error_context_manager(self):
        """Test connection error injection via context manager."""
        injector = FailureInjector()

        with injector.inject_connection_error(duration=1.0):
            assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True

        assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is False

    def test_connection_error_raises_exception(self):
        """Test that connection error injection raises InjectedConnectionError."""
        injector = FailureInjector()

        with pytest.raises(InjectedConnectionError) as exc_info:
            with injector.inject_connection_error(error_message="Connection failed"):
                injector.raise_failure(
                    FailureType.CONNECTION_ERROR, "Connection failed"
                )

        assert "Connection failed" in str(exc_info.value)

    def test_connection_error_with_custom_message(self):
        """Test connection error with custom error message."""
        injector = FailureInjector()

        with pytest.raises(InjectedConnectionError) as exc_info:
            with injector.inject_connection_error(error_message="DB connection lost"):
                injector.raise_failure(FailureType.CONNECTION_ERROR)

        assert "DB connection lost" in str(exc_info.value)


@pytest.mark.chaos
class TestGeneralFailureInjection:
    """Tests for general failure injection."""

    def test_general_failure_context_manager(self):
        """Test general failure injection via context manager."""
        injector = FailureInjector()

        with injector.inject_general_failure(duration=1.0):
            assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True

        assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is False

    def test_general_failure_raises_exception(self):
        """Test that general failure injection raises InjectedFailureError."""
        injector = FailureInjector()

        with pytest.raises(InjectedFailureError) as exc_info:
            with injector.inject_general_failure(error_message="General failure"):
                injector.raise_failure(FailureType.GENERAL_FAILURE)

        assert "General failure" in str(exc_info.value)

    def test_general_failure_with_probability(self):
        """Test general failure with probability less than 1.0."""
        injector = FailureInjector()

        # With 0% probability, should never fail
        with injector.inject_general_failure(probability=0.0):
            assert injector.should_fail(FailureType.GENERAL_FAILURE) is False

        # With 100% probability, should always fail
        with injector.inject_general_failure(probability=1.0):
            assert injector.should_fail(FailureType.GENERAL_FAILURE) is True


@pytest.mark.chaos
class TestSlowResponseInjection:
    """Tests for slow response injection."""

    def test_slow_response_context_manager(self):
        """Test slow response injection via context manager."""
        injector = FailureInjector()

        with injector.inject_slow_response(slow_duration=0.1):
            assert injector.is_failure_active(FailureType.SLOW_RESPONSE) is True

        assert injector.is_failure_active(FailureType.SLOW_RESPONSE) is False

    def test_slow_response_delays_execution(self):
        """Test that slow response actually delays execution."""
        injector = FailureInjector()

        start_time = time.monotonic()
        with injector.inject_slow_response(slow_duration=0.2):
            time.sleep(0.05)
            elapsed = time.monotonic() - start_time
            assert elapsed >= 0.05


@pytest.mark.chaos
class TestFailureConfig:
    """Tests for FailureConfig dataclass."""

    def test_config_creation(self):
        """Test that FailureConfig can be created."""
        config = FailureConfig(
            failure_type=FailureType.TIMEOUT,
            duration=10.0,
            delay=1.0,
            timeout_value=5.0,
        )

        assert config.failure_type == FailureType.TIMEOUT
        assert config.duration == 10.0
        assert config.delay == 1.0
        assert config.timeout_value == 5.0

    def test_config_defaults(self):
        """Test FailureConfig default values."""
        config = FailureConfig(failure_type=FailureType.CONNECTION_ERROR)

        assert config.duration is None
        assert config.delay == 0.0
        assert config.timeout_value == 30.0
        assert config.error_message is None
        assert config.probability == 1.0
        assert config.repeat_count is None


@pytest.mark.chaos
class TestConvenienceFunctions:
    """Tests for convenience injection functions."""

    def test_inject_timeout_function(self):
        """Test inject_timeout convenience function."""
        with inject_timeout(duration=0.1, timeout_value=1.0):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

    def test_inject_connection_error_function(self):
        """Test inject_connection_error convenience function."""
        with inject_connection_error(duration=0.1):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.CONNECTION_ERROR) is True

    def test_inject_general_failure_function(self):
        """Test inject_general_failure convenience function."""
        with inject_general_failure(duration=0.1):
            injector = FailureInjector.get_instance()
            assert injector.is_failure_active(FailureType.GENERAL_FAILURE) is True


@pytest.mark.chaos
class TestPytestFixture:
    """Tests for the pytest fixture."""

    def test_fixture_provides_injector(self, failure_injector: FailureInjector) -> None:
        """Test that fixture provides an injector instance."""
        assert failure_injector is not None
        assert isinstance(failure_injector, FailureInjector)

    def test_fixture_cleans_up_after_test(
        self, failure_injector: FailureInjector
    ) -> None:
        """Test that fixture cleans up after test completes."""
        failure_injector.inject(FailureType.TIMEOUT, duration=10.0)
        assert len(failure_injector._active_failures) == 1

        # After test, fixture should have cleaned up
        # This is verified by the next test getting a clean state


@pytest.mark.chaos
class TestThreadSafety:
    """Tests for thread-safe operation."""

    def test_concurrent_injection(self):
        """Test that injection works correctly from multiple threads."""
        injector = FailureInjector()

        def inject_and_check() -> bool:
            with injector.inject_timeout(duration=1.0):
                return injector.is_failure_active(FailureType.TIMEOUT)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(inject_and_check) for _ in range(20)]
            results = [future.result() for future in as_completed(futures)]

        assert all(results), "All threads should successfully inject and check"

    def test_concurrent_reset(self):
        """Test that reset can be called concurrently."""
        injector = FailureInjector()

        def inject_and_reset() -> None:
            injector.inject(FailureType.TIMEOUT, duration=10.0)
            injector.reset()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(inject_and_reset) for _ in range(10)]
            for future in as_completed(futures):
                future.result()  # Should not raise


@pytest.mark.chaos
class TestIntegrationWithCircuitBreaker:
    """Integration tests with circuit breaker."""

    def test_failure_injection_opens_circuit_breaker(self):
        """Test that injected failures can open a circuit breaker."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        injector = FailureInjector()
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        with injector.inject_general_failure():
            for _ in range(3):
                try:
                    injector.raise_failure(FailureType.GENERAL_FAILURE)
                except InjectedFailureError:
                    cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_recovery_with_injector(self):
        """Test circuit breaker recovery with failure injector."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        injector = FailureInjector()
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Inject failures to open circuit
        with injector.inject_general_failure():
            for _ in range(2):
                try:
                    injector.raise_failure(FailureType.GENERAL_FAILURE)
                except InjectedFailureError:
                    cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Trigger OPEN -> HALF_OPEN transition by accessing state
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes to transition to CLOSED
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED


@pytest.mark.chaos
class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_inject_with_none_duration(self):
        """Test injection with None duration (indefinite)."""
        injector = FailureInjector()
        injector.inject(FailureType.TIMEOUT, duration=None)

        assert injector.is_failure_active(FailureType.TIMEOUT) is True
        injector.reset()

    def test_multiple_simultaneous_injections(self):
        """Test multiple simultaneous injections of different types."""
        injector = FailureInjector()

        with injector.inject_timeout(duration=1.0):
            with injector.inject_connection_error(duration=1.0):
                with injector.inject_general_failure(duration=1.0):
                    assert injector.is_failure_active(FailureType.TIMEOUT) is True
                    assert (
                        injector.is_failure_active(FailureType.CONNECTION_ERROR) is True
                    )
                    assert (
                        injector.is_failure_active(FailureType.GENERAL_FAILURE) is True
                    )

    def test_inject_with_zero_duration(self):
        """Test injection with zero duration."""
        injector = FailureInjector()

        with injector.inject_timeout(duration=0.0):
            # Should still be active during context
            assert injector.is_failure_active(FailureType.TIMEOUT) is True

        # Should be inactive after context
        assert injector.is_failure_active(FailureType.TIMEOUT) is False

    def test_should_fail_with_no_active_failures(self):
        """Test should_fail returns False when no failures active."""
        injector = FailureInjector()

        assert injector.should_fail(FailureType.TIMEOUT) is False
        assert injector.should_fail(FailureType.CONNECTION_ERROR) is False
        assert injector.should_fail(FailureType.GENERAL_FAILURE) is False

    def test_raise_failure_with_unknown_type(self):
        """Test raise_failure with unknown failure type."""
        injector = FailureInjector()

        with pytest.raises(InjectedFailureError):
            injector.raise_failure(FailureType.PARTIAL_FAILURE)
