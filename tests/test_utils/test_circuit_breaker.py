"""Tests for CircuitBreaker pattern implementation."""

import time
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)


class TestCircuitBreakerInitialState:
    """Tests for circuit breaker initial state."""

    def test_initial_state_is_closed(self) -> None:
        """Test that circuit starts in closed state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_initial_failure_count_is_zero(self) -> None:
        """Test initial failure count."""
        cb = CircuitBreaker()
        stats = cb.get_stats()
        assert stats["failure_count"] == 0

    def test_initial_success_count_is_zero(self) -> None:
        """Test initial success count."""
        cb = CircuitBreaker()
        stats = cb.get_stats()
        assert stats["success_count"] == 0


class TestCircuitBreakerSuccessPath:
    """Tests for successful call paths."""

    def test_successful_call_returns_result(self) -> None:
        """Test that successful calls return the function result."""
        cb = CircuitBreaker()
        func = MagicMock(return_value="success")

        result = cb.call(func, "arg1", kwarg="value")

        assert result == "success"
        func.assert_called_once_with("arg1", kwarg="value")

    def test_successful_call_resets_failure_count(self) -> None:
        """Test that success resets failure count in closed state."""
        cb = CircuitBreaker(failure_threshold=3)

        # Simulate some failures
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError("fail")))

        # One success should reset failures
        cb.call(MagicMock(return_value="success"))

        stats = cb.get_stats()
        assert stats["failure_count"] == 0

    def test_multiple_successful_calls_keep_circuit_closed(self) -> None:
        """Test that multiple successes keep circuit closed."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(10):
            cb.call(MagicMock(return_value="success"))

        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerFailurePath:
    """Tests for failure handling paths."""

    def test_failure_increments_count(self) -> None:
        """Test that failures increment the failure count."""
        cb = CircuitBreaker(failure_threshold=5)

        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        stats = cb.get_stats()
        assert stats["failure_count"] == 1

    def test_failures_below_threshold_keep_circuit_closed(self) -> None:
        """Test that failures below threshold don't open circuit."""
        cb = CircuitBreaker(failure_threshold=5)

        for _ in range(4):
            with pytest.raises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.CLOSED

    def test_failures_at_threshold_opens_circuit(self) -> None:
        """Test that failures at threshold opens the circuit."""
        cb = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            with pytest.raises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

    def test_open_circuit_raises_circuit_breaker_error(self) -> None:
        """Test that calling open circuit raises CircuitBreakerError."""
        cb = CircuitBreaker(failure_threshold=1)

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        # Next call should raise CircuitBreakerError
        with pytest.raises(CircuitBreakerError):
            cb.call(MagicMock(return_value="success"))


class TestCircuitBreakerRecoveryPath:
    """Tests for circuit breaker recovery (half-open state)."""

    def test_circuit_transitions_to_half_open_after_timeout(self) -> None:
        """Test automatic transition to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should transition to half-open
        assert cb.state == CircuitState.HALF_OPEN

    def test_successful_call_in_half_open_closes_circuit(self) -> None:
        """Test that success in half-open state closes the circuit."""
        # Use half_open_max_calls=1 so single success closes circuit
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=1
        )

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        # Wait for recovery
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Successful call should close circuit
        cb.call(MagicMock(return_value="success"))

        assert cb.state == CircuitState.CLOSED

        # Verify failure count is reset
        stats = cb.get_stats()
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0

    def test_half_open_limits_recovery_calls(self) -> None:
        """Test that half-open state limits the number of recovery calls."""
        cb = CircuitBreaker(
            failure_threshold=1, recovery_timeout=0.1, half_open_max_calls=2
        )

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        # Wait for recovery
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Make max recovery calls
        cb.call(MagicMock(return_value="success"))
        cb.call(MagicMock(return_value="success"))

        # Next call in half-open should still be allowed (within limit)
        stats = cb.get_stats()
        assert stats["half_open_calls"] == 2

    def test_failure_in_half_open_reopens_circuit(self) -> None:
        """Test that failure in half-open state reopens the circuit."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        # Wait for recovery
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Failure should reopen circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

    def test_full_recovery_sequence(self) -> None:
        """Test complete recovery sequence: closed -> open -> half-open -> closed."""
        cb = CircuitBreaker(
            failure_threshold=2, recovery_timeout=0.1, half_open_max_calls=2
        )

        # Start closed
        assert cb.state == CircuitState.CLOSED

        # Failures to open circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        # Successful recovery calls
        cb.call(MagicMock(return_value="success"))
        cb.call(MagicMock(return_value="success"))

        # Should be closed again
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerManualReset:
    """Tests for manual circuit reset."""

    def test_manual_reset_closes_circuit(self) -> None:
        """Test that manual reset closes the circuit."""
        cb = CircuitBreaker(failure_threshold=1)

        # Open the circuit
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        # Manual reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED

    def test_manual_reset_clears_counts(self) -> None:
        """Test that manual reset clears all counters."""
        cb = CircuitBreaker(failure_threshold=1)

        # Open the circuit with first failure
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        assert cb.state == CircuitState.OPEN

        # Add some success count by transitioning to half-open and succeeding
        time.sleep(0.15)  # Wait for half-open
        if cb.state == CircuitState.HALF_OPEN:
            cb.call(MagicMock(return_value="success"))

        # Reset
        cb.reset()

        stats = cb.get_stats()
        assert stats["failure_count"] == 0
        assert stats["success_count"] == 0
        assert stats["half_open_calls"] == 0


class TestCircuitBreakerThreadSafety:
    """Tests for thread safety of circuit breaker."""

    def test_concurrent_successes_are_thread_safe(self) -> None:
        """Test that concurrent successful calls are thread-safe."""
        import threading

        cb = CircuitBreaker(failure_threshold=100)
        results: list[str] = []
        lock = threading.Lock()

        def make_call() -> None:
            result = cb.call(lambda: "success")
            with lock:
                results.append(result)

        threads = [threading.Thread(target=make_call) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 50
        assert cb.state == CircuitState.CLOSED

    def test_concurrent_failures_are_thread_safe(self) -> None:
        """Test that concurrent failures are thread-safe."""
        import threading

        cb = CircuitBreaker(failure_threshold=10)
        errors: list[Exception] = []
        lock = threading.Lock()

        def make_failing_call() -> None:
            try:
                cb.call(MagicMock(side_effect=Exception("fail")))
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=make_failing_call) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Circuit should be open after enough failures
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerStatistics:
    """Tests for circuit breaker statistics."""

    def test_get_stats_returns_all_fields(self) -> None:
        """Test that get_stats returns all expected fields."""
        cb = CircuitBreaker()

        stats = cb.get_stats()

        assert "state" in stats
        assert "failure_count" in stats
        assert "success_count" in stats
        assert "last_failure_time" in stats
        assert "half_open_calls" in stats

    def test_stats_reflect_state_changes(self) -> None:
        """Test that statistics accurately reflect state changes."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        # Initial state
        stats = cb.get_stats()
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0

        # After failures
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        stats = cb.get_stats()
        assert stats["failure_count"] == 1

        # After opening
        with pytest.raises(RuntimeError):
            cb.call(MagicMock(side_effect=RuntimeError("fail")))

        stats = cb.get_stats()
        assert stats["state"] == "open"
        assert stats["last_failure_time"] is not None
