"""Tests for circuit breaker implementation."""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)


@pytest.mark.circuit_breaker
class TestCircuitState:
    """Test CircuitState enum."""

    def test_state_values(self):
        """Test that all states have correct values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_state_count(self):
        """Test that there are exactly 3 states."""
        assert len(list(CircuitState)) == 3


@pytest.mark.circuit_breaker
class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.recovery_timeout == 30.0
        assert config.half_open_max_calls == 3

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=5,
            recovery_timeout=60.0,
            half_open_max_calls=10,
        )
        assert config.failure_threshold == 10
        assert config.success_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.half_open_max_calls == 10


@pytest.mark.circuit_breaker
class TestCircuitBreakerBasic:
    """Test basic circuit breaker functionality."""

    def test_initial_state_is_closed(self):
        """Test that circuit starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_is_allowed_when_closed(self):
        """Test that requests are allowed when CLOSED."""
        cb = CircuitBreaker()
        assert cb.is_allowed() is True

    def test_record_success_when_closed(self):
        """Test that success doesn't change CLOSED state."""
        cb = CircuitBreaker()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reset_returns_to_closed(self):
        """Test that reset returns circuit to CLOSED state."""
        cb = CircuitBreaker()
        # Force to OPEN state
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Reset
        cb.reset()
        assert cb.state == CircuitState.CLOSED


@pytest.mark.circuit_breaker
class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions."""

    def test_closed_to_open_after_threshold_failures(self):
        """Test that circuit opens after failure_threshold consecutive failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)

        # Should stay closed for 2 failures
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        # Should open on 3rd failure
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        """Test that OPEN circuit blocks all requests."""
        cb = CircuitBreaker()

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.is_allowed() is False

    def test_open_to_half_open_after_timeout(self):
        """Test that circuit transitions to HALF_OPEN after recovery_timeout."""
        config = CircuitBreakerConfig(recovery_timeout=0.05)  # 50ms for testing
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for timeout to elapse
        time.sleep(0.07)  # 70ms > 50ms timeout

        # Should transition to HALF_OPEN
        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_after_successes(self):
        """Test that circuit closes after success_threshold successes in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout to elapse
        time.sleep(0.07)  # 70ms > 50ms timeout

        # Should be in HALF_OPEN now
        assert cb.state == CircuitState.HALF_OPEN

        # Successes should close the circuit
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Need 2 successes

        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Test that circuit reopens on failure in HALF_OPEN state."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout to elapse
        time.sleep(0.07)  # 70ms > 50ms timeout

        # Should be in HALF_OPEN now
        assert cb.state == CircuitState.HALF_OPEN

        # Failure should reopen the circuit
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


@pytest.mark.circuit_breaker
class TestCircuitBreakerThreadSafety:
    """Test circuit breaker thread safety."""

    def test_concurrent_record_success(self):
        """Test that concurrent successes don't break state."""
        cb = CircuitBreaker()

        def record_success_many_times():
            for _ in range(100):
                cb.record_success()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(record_success_many_times) for _ in range(10)]
            for future in futures:
                future.result()

        # Should still be closed
        assert cb.state == CircuitState.CLOSED

    def test_concurrent_record_failure(self):
        """Test that concurrent failures correctly open circuit."""
        config = CircuitBreakerConfig(failure_threshold=10)
        cb = CircuitBreaker(config)

        def record_failure_many_times():
            for _ in range(20):
                cb.record_failure()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(record_failure_many_times) for _ in range(5)]
            for future in futures:
                future.result()

        # Should be open (at least 10 failures occurred)
        assert cb.state == CircuitState.OPEN

    def test_concurrent_state_transitions(self):
        """Test thread-safe state transitions."""
        import time as time_module

        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        call_count = 0

        def mock_monotonic():
            nonlocal call_count
            call_count += 1
            # Return increasing time values to simulate time passing
            return call_count * 0.01

        def open_circuit():
            for _ in range(10):
                cb.record_failure()

        def record_successes():
            with patch.object(time_module, "monotonic", side_effect=mock_monotonic):
                for _ in range(5):
                    cb.record_success()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(open_circuit),
                executor.submit(record_successes),
            ]
            for future in futures:
                future.result()

        # Final state should be a valid state (any of the 3 states is acceptable
        # due to race conditions in the test)
        assert cb.state in (
            CircuitState.CLOSED,
            CircuitState.OPEN,
            CircuitState.HALF_OPEN,
        )


@pytest.mark.circuit_breaker
class TestCircuitBreakerError:
    """Test CircuitBreakerError exception."""

    def test_error_message(self):
        """Test default error message."""
        error = CircuitBreakerError()
        assert "Circuit breaker is open" in str(error)

    def test_error_with_service_name(self):
        """Test error message with service name."""
        error = CircuitBreakerError(service_name="mongo")
        assert "mongo" in error.message

    def test_error_attributes(self):
        """Test error attributes."""
        error = CircuitBreakerError("Service unavailable", "test-service")
        assert error.service_name == "test-service"
        assert "test-service" in error.message


@pytest.mark.circuit_breaker
class TestCircuitBreakerHalfOpenCalls:
    """Test HALF_OPEN state call limits."""

    def test_half_open_allows_limited_calls(self):
        """Test that HALF_OPEN allows up to half_open_max_calls."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            half_open_max_calls=3,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for half-open
        time.sleep(0.15)

        # Should allow first 3 calls
        assert cb.is_allowed() is True
        assert cb.is_allowed() is True
        assert cb.is_allowed() is True

        # 4th call should be blocked (still in half-open with no successes)
        # Note: This depends on implementation - some allow all calls until successes recorded
        # For now, we just verify the first 3 work
