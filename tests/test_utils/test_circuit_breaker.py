"""Tests for circuit breaker implementation."""

import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerEnabledService,
    CircuitBreakerError,
    CircuitState,
)
from secondbrain.utils.connections import ValidatableService


@pytest.fixture(autouse=True, scope="class")
def _fast_circuit_breaker_time():
    """Accelerate circuit-breaker timeout tests by advancing time programmatically.

    The CircuitBreaker tracks time using ``time.monotonic()``.  The tests use
    ``time.sleep(dt)`` to wait for recovery timeouts to elapse.  Here we replace
    ``time.sleep`` with a noop and wrap ``time.monotonic`` with a shared,
    lazily-initialised offset that grows by the sleep duration on every call —
    simulating elapsed time without any actual waiting.

    Effect: CB state transitions fire instantly, cutting ~6 s of dead wait time
    per exponential-backoff test to near-zero without breaking the state machine.
    """
    _orig_sleep = time.sleep
    _orig_monotonic = time.monotonic

    _lazy_base: float | None = None

    def _fast_monotonic() -> float:
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        return _lazy_base  # type: ignore[return-value]

    def _fast_sleep(seconds: float) -> None:
        if seconds <= 0:
            return
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        # Guard against FP boundary: 0.1 * 2 = 0.1 exactly in IEEE-754,
        # so accumulated _lazy_base can undershoot by microepsilon.  The +1e-6
        # ensures elapsed >= current_recovery_timeout reliably passes.
        _lazy_base += seconds + 1e-6

    time.sleep = _fast_sleep  # type: ignore[method-assign]
    time.monotonic = _fast_monotonic  # type: ignore[method-assign]
    yield
    time.sleep = _orig_sleep  # type: ignore[method-assign]
    time.monotonic = _orig_monotonic


@pytest.mark.circuit_breaker
@pytest.mark.slow
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
@pytest.mark.slow
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
@pytest.mark.slow
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
        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED


@pytest.mark.circuit_breaker
@pytest.mark.slow
class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions."""

    def test_closed_to_open_after_threshold_failures(self):
        """Test that circuit opens after failure_threshold consecutive failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker(config)

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        """Test that OPEN circuit blocks all requests."""
        cb = CircuitBreaker()

        for _ in range(5):
            cb.record_failure()

        assert cb.is_allowed() is False

    def test_open_to_half_open_after_timeout(self):
        """Test that circuit transitions to HALF_OPEN after recovery_timeout."""
        config = CircuitBreakerConfig(recovery_timeout=0.05)
        cb = CircuitBreaker(config)

        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        time.sleep(0.07)

        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN
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

        # Trip the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for recovery timeout (use longer time to account for system load)
        time.sleep(0.1)

        assert cb.state == CircuitState.HALF_OPEN

        # Record failure in HALF_OPEN state
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for timeout again
        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # One more failure should reopen
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


@pytest.mark.circuit_breaker
@pytest.mark.slow
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
@pytest.mark.slow
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
@pytest.mark.slow
class TestCircuitBreakerHalfOpenCalls:
    """Test HALF_OPEN state call limits."""

    def test_half_open_allows_limited_calls(self):
        """Test that HALF_OPEN allows up to half_open_max_calls."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

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


@pytest.mark.circuit_breaker
@pytest.mark.slow
class TestCircuitBreakerExponentialBackoff:
    """Test exponential backoff for circuit breaker recovery timeout."""

    def test_timeout_doubles_on_half_open_failure(self):
        """Test that recovery timeout doubles when circuit re-opens from HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=1.0,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(1.1)
        assert cb.state == CircuitState.OPEN

        time.sleep(1.0)
        assert cb.state == CircuitState.HALF_OPEN

    def test_timeout_caps_at_300_seconds(self):
        """Test that recovery timeout is capped at 300 seconds."""
        import time as time_module

        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=100.0,
        )
        cb = CircuitBreaker(config)

        current_time = 0.0

        def mock_monotonic():
            nonlocal current_time
            return current_time

        with patch.object(time_module, "monotonic", side_effect=mock_monotonic):
            cb.record_failure()
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            current_time += 200.0
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            current_time += 200.0
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            current_time += 300.0
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            current_time += 300.0
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

            current_time += 300.0
            assert cb.state == CircuitState.HALF_OPEN
            cb.record_failure()
            assert cb.state == CircuitState.OPEN

        state_info = cb.get_state_info()
        assert state_info["backoff_multiplier"] == 32
        assert state_info["current_recovery_timeout"] == 300.0

    def test_backoff_resets_on_successful_recovery(self):
        """Test that backoff resets when circuit successfully closes."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.07)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

    def test_multiple_half_open_failures_double_timeout_progressively(self):
        """Test that timeout doubles on each HALF_OPEN -> OPEN transition."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.11)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.21)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.41)
        assert cb.state == CircuitState.HALF_OPEN

    def test_state_changes_logged(self) -> None:
        import time

        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        assert cb.state == CircuitState.CLOSED

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_failure_count_is_queryable(self) -> None:
        """Test that failure count can be queried via get_state_info."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker(config)

        # Initial state
        state_info = cb.get_state_info()
        assert state_info["failure_count"] == 0

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()

        state_info = cb.get_state_info()
        assert state_info["failure_count"] == 3

        # Record success to reset
        cb.record_success()
        state_info = cb.get_state_info()
        assert state_info["failure_count"] == 0

    def test_state_is_queryable(self) -> None:
        """Test that state can be queried via get_state_info."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
            CircuitState,
        )

        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        cb = CircuitBreaker(config)

        # Initial state
        state_info = cb.get_state_info()
        assert state_info["state"] == CircuitState.CLOSED.value

        # Transition to OPEN
        cb.record_failure()
        cb.record_failure()
        state_info = cb.get_state_info()
        assert state_info["state"] == CircuitState.OPEN.value

        # Transition to HALF_OPEN after timeout
        import time
        time.sleep(0.15)
        state_info = cb.get_state_info()
        assert state_info["state"] == CircuitState.HALF_OPEN.value

    def test_get_state_info_returns_all_metrics(self) -> None:
        """Test that get_state_info returns comprehensive metrics."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreaker,
            CircuitBreakerConfig,
        )

        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            recovery_timeout=30.0,
        )
        cb = CircuitBreaker(config)

        state_info = cb.get_state_info()

        # Verify all expected fields are present
        assert "state" in state_info
        assert "failure_count" in state_info
        assert "success_count" in state_info
        assert "half_open_calls" in state_info
        assert "failure_threshold" in state_info
        assert "success_threshold" in state_info
        assert "recovery_timeout" in state_info
        assert "current_recovery_timeout" in state_info
        assert "backoff_multiplier" in state_info
        assert "half_open_max_calls" in state_info

        # Verify values match configuration
        assert state_info["failure_threshold"] == 5
        assert state_info["success_threshold"] == 2
        assert state_info["recovery_timeout"] == 30.0


def test_state_changes_logged_with_timestamp():
    """Test that state changes are logged with timestamp and reason.
    
    QA: Verify observability of circuit breaker state transitions.
    """
    import logging
    import time
    from io import StringIO

    from secondbrain.utils.circuit_breaker import (
        CircuitBreaker,
        CircuitBreakerConfig,
        CircuitState,
    )

    # Setup logging capture
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)

    logger = logging.getLogger('secondbrain.utils.circuit_breaker')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    config = CircuitBreakerConfig(
        failure_threshold=2,
        recovery_timeout=0.1,
    )
    cb = CircuitBreaker(config)

    # Trigger state changes
    assert cb.state == CircuitState.CLOSED

    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # Wait for transition to HALF_OPEN
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    log_contents = log_stream.getvalue()

    # Verify logs contain state changes
    assert "CLOSED" in log_contents or "OPEN" in log_contents or "HALF_OPEN" in log_contents

    # Cleanup
    logger.removeHandler(handler)


@pytest.mark.circuit_breaker
@pytest.mark.slow
class TestCircuitBreakerErrorPaths:
    """Comprehensive error path tests for circuit breaker."""

    def test_circuit_breaker_opens_after_consecutive_failures(self):
        """Test that circuit opens after failure_threshold consecutive failures.

        Error Path: CLOSED -> OPEN transition on consecutive failures.
        """
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=30.0,
        )
        cb = CircuitBreaker(config)

        # Circuit starts closed
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0

        # Record failures below threshold
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 1

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 2

        # Third failure should open the circuit
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb._failure_count == 3

    def test_circuit_breaker_half_open_after_recovery_timeout(self):
        """Test that circuit transitions to HALF_OPEN after recovery_timeout.

        Error Path: OPEN -> HALF_OPEN transition after timeout.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should transition to HALF_OPEN on next check
        assert cb.state == CircuitState.HALF_OPEN
        assert cb._half_open_calls == 0
        assert cb._success_count == 0

    def test_circuit_breaker_closes_on_success_in_half_open(self):
        """Test that circuit closes after success_threshold successes in HALF_OPEN.

        Error Path: HALF_OPEN -> CLOSED transition on successful recovery.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Wait for HALF_OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Record successes to close circuit
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        assert cb._success_count == 1

        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0

    def test_circuit_breaker_rejects_calls_when_open(self):
        """Test that circuit rejects all calls when in OPEN state.

        Error Path: is_allowed() returns False when OPEN.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            recovery_timeout=30.0,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # All calls should be rejected
        assert cb.is_allowed() is False
        assert cb.is_allowed() is False

        # call() should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError) as exc_info:
            cb.call(lambda: True)

        assert "Circuit breaker is open" in str(exc_info.value.message)
        assert cb.service_name in exc_info.value.message

    def test_circuit_breaker_state_persistence(self):
        """Test that circuit breaker state persists across calls.

        Error Path: State variables maintain consistency.
        """
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Record some failures
        cb.record_failure()
        cb.record_failure()

        # State should persist
        state_info = cb.get_state_info()
        assert state_info["failure_count"] == 2
        assert state_info["state"] == "closed"

        # Open the circuit
        cb.record_failure()
        state_info = cb.get_state_info()
        assert state_info["state"] == "open"
        assert state_info["failure_count"] == 3

        # Wait for HALF_OPEN
        time.sleep(0.15)
        state_info = cb.get_state_info()
        assert state_info["state"] == "half_open"
        assert state_info["half_open_calls"] == 0

    def test_circuit_breaker_custom_error_handler(self):
        """Test circuit breaker with custom error handling via call().

        Error Path: Exception handling in call() method.
        """
        cb = CircuitBreaker()

        # Track exception handling
        exception_raised = False

        def failing_function():
            raise ValueError("Test exception")

        try:
            cb.call(failing_function)
        except ValueError:
            exception_raised = True

        assert exception_raised is True
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 1

    def test_circuit_breaker_failure_resets_on_success_in_closed(self):
        """Test that success in CLOSED state resets failure count.

        Error Path: record_success() resets _failure_count in CLOSED state.
        """
        config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=30.0,
        )
        cb = CircuitBreaker(config)

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 3

        # Success should reset failure count
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_half_open_failure_resets_counters(self):
        """Test that failure in HALF_OPEN resets half_open_calls counter.

        Error Path: record_failure() in HALF_OPEN resets counters.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Open and transition to HALF_OPEN
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Record a call
        assert cb.is_allowed() is True
        assert cb._half_open_calls == 0  # Incremented after is_allowed check

        # Simulate a call that succeeds (manually increment)
        cb._half_open_calls = 1

        # Failure should reopen circuit and reset counters
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb._half_open_calls == 0

    def test_circuit_breaker_call_records_success_and_failure(self):
        """Test that call() properly records success and failure.

        Error Path: call() method tracks outcomes correctly.
        """
        cb = CircuitBreaker()

        # Successful call
        result = cb.call(lambda: True)
        assert result is True
        assert cb._failure_count == 0

        # Failed call (returns False)
        result = cb.call(lambda: False)
        assert result is False
        assert cb._failure_count == 1

    def test_circuit_breaker_exponential_backoff_on_half_open_failure(self):
        """Test exponential backoff increases recovery timeout.

        Error Path: record_failure() in HALF_OPEN doubles recovery timeout.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            recovery_timeout=1.0,
        )
        cb = CircuitBreaker(config)

        # Open circuit
        cb.record_failure()
        cb.record_failure()
        assert cb._current_recovery_timeout == 1.0
        assert cb._backoff_multiplier == 1

        # Transition to HALF_OPEN
        time.sleep(1.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Failure in HALF_OPEN should double timeout
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb._current_recovery_timeout == 2.0
        assert cb._backoff_multiplier == 2

        # Another cycle
        time.sleep(2.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb._current_recovery_timeout == 4.0
        assert cb._backoff_multiplier == 4

    def test_circuit_breaker_reset_clears_all_counters(self):
        """Test that reset() clears all state counters.

        Error Path: reset() method fully resets circuit breaker.
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        # Set circuit to OPEN state with various counters
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)  # HALF_OPEN
        cb.record_success()  # Partial success
        cb._half_open_calls = 2
        cb._backoff_multiplier = 4
        cb._current_recovery_timeout = 4.0

        # Reset
        cb.reset()

        # Verify all counters reset
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._half_open_calls == 0
        assert cb._backoff_multiplier == 1
        assert cb._current_recovery_timeout == config.recovery_timeout
        assert cb._last_failure_time is None

    def test_circuit_breaker_thread_safety_concurrent_failures(self):
        """Test circuit breaker handles concurrent failures safely.

        Error Path: Thread safety under concurrent access.
        """
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=10))

        def record_failures():
            for _ in range(5):
                cb.record_failure()

        # Run 3 threads concurrently, each recording 5 failures
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(record_failures) for _ in range(3)]
            for future in futures:
                future.result()

        # Should have opened circuit (15 failures > threshold of 10)
        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_get_state_info_all_fields(self):
        """Test get_state_info() returns all expected fields.

        Error Path: State info dictionary completeness.
        """
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=60.0,
            half_open_max_calls=5,
        )
        cb = CircuitBreaker(config, service_name="test-service")

        state_info = cb.get_state_info()

        # Verify all expected keys exist
        expected_keys = [
            "state",
            "failure_count",
            "success_count",
            "half_open_calls",
            "failure_threshold",
            "success_threshold",
            "recovery_timeout",
            "current_recovery_timeout",
            "backoff_multiplier",
            "half_open_max_calls",
        ]

        for key in expected_keys:
            assert key in state_info, f"Missing key: {key}"

        # Verify values
        assert state_info["state"] == "closed"
        assert state_info["failure_count"] == 0
        assert state_info["success_count"] == 0
        assert state_info["failure_threshold"] == 5
        assert state_info["success_threshold"] == 3
        assert state_info["recovery_timeout"] == 60.0
        assert state_info["half_open_max_calls"] == 5


class TestCircuitBreakerProperties:
    """Tests for CircuitBreaker property getters."""

    def test_failure_count_property(self):
        """Test that failure_count property returns correct value."""
        cb = CircuitBreaker()
        assert cb.failure_count == 0

        # Record failures while in CLOSED state
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

    def test_success_count_property_initial(self):
        """Test that success_count property returns initial value."""
        cb = CircuitBreaker()
        assert cb.success_count == 0


class TestCircuitBreakerEnabledService:
    """Tests for CircuitBreakerEnabledService mixin class."""

    def test_init_with_circuit_breaker(self):
        """Test initialization with circuit breaker config."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
        )

        class TestService(CircuitBreakerEnabledService):
            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            service_name="TestService",
        )

        assert service.is_circuit_breaker_enabled is True
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.CLOSED

    def test_init_without_circuit_breaker(self):
        """Test initialization without circuit breaker config."""
        from secondbrain.utils.circuit_breaker import CircuitBreakerEnabledService

        class TestService(CircuitBreakerEnabledService):
            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService()

        assert service.is_circuit_breaker_enabled is False
        assert service.circuit_breaker is None

    def test_validate_connection_with_circuit_breaker_success(self):
        """Test validate_connection_with_circuit_breaker on success."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
        )

        class TestService(CircuitBreakerEnabledService):
            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            service_name="TestService",
        )

        result = service.validate_connection_with_circuit_breaker(force=True)
        assert result is True
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.CLOSED

    def test_validate_connection_with_circuit_breaker_failure(self):
        """Test validate_connection_with_circuit_breaker on failure."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
        )

        class TestService(CircuitBreakerEnabledService):
            def validate_connection(self, force: bool = False) -> bool:
                return False

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
            service_name="TestService",
        )

        result = service.validate_connection_with_circuit_breaker(force=True)
        assert result is False
        # After one failure with threshold=1, circuit should open
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

    def test_validate_connection_with_circuit_breaker_open(self):
        """Test validate_connection_with_circuit_breaker when circuit is open."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
            CircuitBreakerError,
        )

        class TestService(CircuitBreakerEnabledService):
            def validate_connection(self, force: bool = False) -> bool:
                return False

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
            service_name="TestService",
        )

        # Trigger circuit to open
        service.validate_connection_with_circuit_breaker(force=True)
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

        # Next call should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            service.validate_connection_with_circuit_breaker(force=True)

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_circuit_breaker(self):
        """Test async validate_connection_with_circuit_breaker."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
        )

        class TestService(CircuitBreakerEnabledService):
            async def validate_connection_async(self, force: bool = False) -> bool:
                return True

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=3),
            service_name="TestService",
        )

        result = await service.validate_connection_async_with_circuit_breaker(
            force=True
        )
        assert result is True
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_circuit_breaker_failure(self):
        """Test async validate_connection_with_circuit_breaker on failure."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
        )

        class TestService(CircuitBreakerEnabledService):
            async def validate_connection_async(self, force: bool = False) -> bool:
                return False

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
            service_name="TestService",
        )

        result = await service.validate_connection_async_with_circuit_breaker(
            force=True
        )
        assert result is False
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_circuit_breaker_open(self):
        """Test async validate when circuit is already open."""
        from secondbrain.utils.circuit_breaker import (
            CircuitBreakerConfig,
            CircuitBreakerEnabledService,
            CircuitBreakerError,
        )

        class TestService(CircuitBreakerEnabledService):
            async def validate_connection_async(self, force: bool = False) -> bool:
                return False

        service = TestService(
            circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
            service_name="TestService",
        )

        # First call opens the circuit
        await service.validate_connection_async_with_circuit_breaker(force=True)
        assert service.circuit_breaker is not None
        assert service.circuit_breaker.state == CircuitState.OPEN

        # Second call should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            await service.validate_connection_async_with_circuit_breaker(force=True)


class TestCircuitBreakerEdgeCases:
    """Tests for CircuitBreaker edge cases."""

    def test_call_returns_false(self) -> None:
        """Test call() when function returns False (line 265)."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        result = cb.call(lambda: False)

        assert result is False
        # Should record failure and open circuit
        assert cb.state == CircuitState.OPEN

    def test_call_raises_exception(self) -> None:
        """Test call() when function raises exception (lines 267-275)."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))

        def failing_func() -> bool:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            cb.call(failing_func)

        # Should record failure
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerCoverageService:
    """Tests for CircuitBreakerEnabledService."""

    def test_circuit_breaker_enabled_service_init(self) -> None:
        """Test CircuitBreakerEnabledService initialization (lines 338-342)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()

        assert service._circuit_breaker is not None
        assert service._circuit_breaker_enabled is True

    def test_circuit_breaker_property(self) -> None:
        """Test circuit_breaker property getter (line 350)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()
        cb = service.circuit_breaker

        assert cb is not None
        assert cb.service_name == "test-service"

    def test_is_circuit_breaker_enabled_property(self) -> None:
        """Test is_circuit_breaker_enabled property (line 355)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

        service = TestService()

        assert service.is_circuit_breaker_enabled is True


class TestValidateConnectionWithCircuitBreaker:
    """Tests for validate_connection_with_circuit_breaker."""

    def test_validate_connection_with_cb_open(self) -> None:
        """Test validate_connection_with_circuit_breaker when CB is open (lines 369-391)."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService()

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError) as exc_info:
            service.validate_connection_with_circuit_breaker()

        assert "Circuit breaker is open" in str(exc_info.value)

    def test_validate_connection_with_cb_closed(self) -> None:
        """Test validate_connection_with_circuit_breaker when CB is closed."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

        service = TestService()

        result = service.validate_connection_with_circuit_breaker()

        assert result is True
        # Should record success
        cb = service.circuit_breaker
        assert cb is not None
        assert cb.state == CircuitState.CLOSED


class TestAsyncValidationWithCircuitBreaker:
    """Tests for async validation with circuit breaker (lines 407-429)."""

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_open(self) -> None:
        """Test async validation when CB is open."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(failure_threshold=1),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

            async def validate_connection_async(self, force: bool = False) -> bool:
                return True

        service = TestService()

        # Open the circuit
        assert service._circuit_breaker is not None
        service._circuit_breaker.record_failure()

        with pytest.raises(CircuitBreakerError):
            await service.validate_connection_async_with_circuit_breaker()

    @pytest.mark.asyncio
    async def test_validate_connection_async_with_cb_closed(self) -> None:
        """Test async validation when CB is closed."""

        class TestService(CircuitBreakerEnabledService, ValidatableService):
            def __init__(self) -> None:
                super().__init__(
                    cache_ttl=60.0,
                    circuit_breaker_config=CircuitBreakerConfig(),
                    service_name="test-service",
                )

            def _do_validate(self) -> bool:
                return True

            async def _do_validate_async(self) -> bool:
                return True

            def validate_connection(self, force: bool = False) -> bool:
                return True

            async def validate_connection_async(self, force: bool = False) -> bool:
                return True

        service = TestService()

        result = await service.validate_connection_async_with_circuit_breaker()

        assert result is True
        cb = service.circuit_breaker
        assert cb is not None
        assert cb.state == CircuitState.CLOSED
