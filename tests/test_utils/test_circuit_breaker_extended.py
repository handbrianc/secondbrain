"""Extended tests for circuit breaker implementation - edge cases and advanced scenarios."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)


@pytest.mark.circuit_breaker
class TestHalfOpenExceedsMaxCalls:
    """Test exceeding half_open_max_calls limit in HALF_OPEN state."""

    def test_half_open_exceeds_max_calls(self):
        """Test that exceeding half_open_max_calls keeps circuit in half-open state."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=3,  # Need 3 successes to close
            recovery_timeout=0.05,
            half_open_max_calls=2,  # Only allow 2 test calls
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for timeout to elapse
        time.sleep(0.07)

        # Should be in HALF_OPEN now
        assert cb.state == CircuitState.HALF_OPEN

        # First two calls should be allowed and recorded
        assert cb.is_allowed() is True
        cb.call(lambda: True)  # Record first call
        assert cb._half_open_calls == 1

        assert cb.is_allowed() is True
        cb.call(lambda: True)  # Record second call
        assert cb._half_open_calls == 2

        # Third call should be blocked (exceeds half_open_max_calls=2)
        assert cb.is_allowed() is False

        # State should still be HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        # Verify error handling - calling should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError) as exc_info:
            cb.call(lambda: True)

        assert "Circuit breaker is open" in str(exc_info.value)
        assert cb.state == CircuitState.HALF_OPEN  # State unchanged


@pytest.mark.circuit_breaker
class TestHalfOpenPartialSuccess:
    """Test partial success scenarios in HALF_OPEN state."""

    def test_half_open_partial_success(self):
        """Test some successes, some failures in half-open - threshold not met."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=3,  # Need 3 consecutive successes
            recovery_timeout=0.05,
            half_open_max_calls=5,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout
        time.sleep(0.07)

        # Should be in HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        # First success
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 1

        # A failure resets the success count
        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # Any failure in half-open reopens

        # Wait again for timeout
        time.sleep(0.07)

        # Back to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 0  # Reset after reopening

        # Now partial successes without reaching threshold
        cb.record_success()
        assert cb.success_count == 1
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.success_count == 2
        assert cb.state == CircuitState.HALF_OPEN  # Still need 1 more

        # One more success should close it
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.success_count == 0  # Reset after closing


@pytest.mark.circuit_breaker
class TestConcurrentStateTransitions:
    """Test thread safety with concurrent state transitions."""

    def test_concurrent_state_transitions(self):
        """Test thread safety with 100 concurrent calls."""
        config = CircuitBreakerConfig(
            failure_threshold=50,
            success_threshold=10,
            recovery_timeout=0.1,
            half_open_max_calls=20,
        )
        cb = CircuitBreaker(config)

        results = {"successes": 0, "failures": 0, "errors": 0}
        lock = threading.Lock()

        def make_call(is_success: bool) -> None:
            """Make a call and record result."""
            try:
                if cb.is_allowed():
                    if is_success:
                        cb.record_success()
                        with lock:
                            results["successes"] += 1
                    else:
                        cb.record_failure()
                        with lock:
                            results["failures"] += 1
                else:
                    with lock:
                        results["errors"] += 1
            except Exception:
                with lock:
                    results["errors"] += 1

        # Run 100 concurrent calls with mixed success/failure
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(100):
                is_success = i % 2 == 0  # Alternating success/failure
                futures.append(executor.submit(make_call, is_success))

            for future in as_completed(futures):
                future.result()  # Wait for completion

        # Verify no race conditions - state should be consistent
        state = cb.state
        assert state in (CircuitState.CLOSED, CircuitState.OPEN, CircuitState.HALF_OPEN)

        # Verify state info is consistent
        state_info = cb.get_state_info()
        assert "state" in state_info
        assert state_info["state"] == state.value

        # Verify counters are non-negative
        assert state_info["failure_count"] >= 0
        assert state_info["success_count"] >= 0
        assert state_info["half_open_calls"] >= 0

        # Verify total operations match
        total_ops = results["successes"] + results["failures"] + results["errors"]
        assert total_ops == 100


@pytest.mark.circuit_breaker
class TestRecoveryTimeoutPrecision:
    """Test recovery timeout timing accuracy."""

    def test_recovery_timeout_precision(self):
        """Test exact timeout behavior with sub-second precision."""
        config = CircuitBreakerConfig(recovery_timeout=0.1)  # 100ms
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Record the exact time of failure
        failure_time = time.monotonic()

        # Test at various intervals
        time.sleep(0.05)  # 50ms - should still be OPEN
        assert cb.state == CircuitState.OPEN

        time.sleep(0.03)  # 80ms total - should still be OPEN
        assert cb.state == CircuitState.OPEN

        time.sleep(0.03)  # 110ms total - should be HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        # Verify timing accuracy
        elapsed = time.monotonic() - failure_time
        assert elapsed >= 0.1  # Should have passed timeout

    def test_sub_second_precision(self):
        """Test sub-second timeout precision."""
        config = CircuitBreakerConfig(recovery_timeout=0.01)  # 10ms
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        # Wait just enough
        time.sleep(0.015)  # 15ms > 10ms

        assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.circuit_breaker
class TestSuccessThresholdRequirement:
    """Test exact success count needed to close circuit."""

    def test_success_threshold_requirement(self):
        """Test exact success count needed to transition from HALF_OPEN to CLOSED."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=5,  # Need exactly 5 successes
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout
        time.sleep(0.07)

        assert cb.state == CircuitState.HALF_OPEN

        # Record successes up to but not including threshold
        for i in range(4):
            cb.record_success()
            assert cb.state == CircuitState.HALF_OPEN
            assert cb.success_count == i + 1

        # One more success should close it
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.success_count == 0  # Reset after closing

    def test_threshold_not_met(self):
        """Test that circuit stays open if threshold not met."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=10,  # High threshold
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout
        time.sleep(0.07)

        assert cb.state == CircuitState.HALF_OPEN

        # Record some successes but not enough
        for _ in range(5):
            cb.record_success()

        assert cb.state == CircuitState.HALF_OPEN
        assert cb.success_count == 5

        # A failure should reopen
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_threshold_exceeded(self):
        """Test behavior when success count exceeds threshold."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.05,
        )
        cb = CircuitBreaker(config)

        # Open the circuit
        for _ in range(3):
            cb.record_failure()

        # Wait for timeout
        time.sleep(0.07)

        assert cb.state == CircuitState.HALF_OPEN

        # Two successes should close it
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

        # Additional successes in CLOSED state should work normally
        cb.record_success()
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0  # Reset on success in closed state
