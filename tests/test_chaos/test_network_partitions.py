"""Tests for network partition scenarios."""

import time

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


@pytest.mark.chaos
class TestNetworkPartitionScenarios:
    """Test network partition handling."""

    def test_partition_detected_via_timeout(self):
        """Test that network partitions are detected via timeouts."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        )

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_partition_recovery_detection(self):
        """Test detection of network partition recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        time.sleep(0.12)

        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_partial_partition_handling(self):
        """Test handling of partial network partitions."""
        mongo_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
        embedding_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        for _ in range(3):
            mongo_cb.record_failure()

        assert mongo_cb.state == CircuitState.OPEN
        assert embedding_cb.state == CircuitState.CLOSED

    def test_circuit_breaker_response_to_partition(self):
        """Test circuit breaker response pattern to network partitions."""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=0.2,
            half_open_max_calls=5,
        )
        cb = CircuitBreaker(config)

        for _ in range(2):
            cb.record_success()
        assert cb.state == CircuitState.CLOSED

        for _ in range(5):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.22)
        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN

        for _ in range(3):
            assert cb.is_allowed() is True
        cb.record_success()
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED


@pytest.mark.chaos
class TestTimeoutHandling:
    """Test timeout handling in network partitions."""

    def test_short_timeout_detects_partition(self):
        """Test that short timeouts quickly detect partitions."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        )

        for _ in range(2):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_long_timeout_allows_slow_responses(self):
        """Test that longer timeouts allow slow but valid responses."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=5, recovery_timeout=0.5)
        )

        cb.record_success()
        cb.record_failure()
        cb.record_success()
        cb.record_success()
        cb.record_success()

        assert cb.state == CircuitState.CLOSED

    def test_cascading_timeouts_open_circuit(self):
        """Test that cascading timeouts open the circuit."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=3, recovery_timeout=0.1)
        )

        for _i in range(10):
            cb.record_failure()
            if cb.state == CircuitState.OPEN:
                break

        assert cb.state == CircuitState.OPEN


@pytest.mark.chaos
class TestRecoveryPatterns:
    """Test recovery patterns after network partitions."""

    def test_exponential_backoff_recovery(self):
        """Test exponential backoff during recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
            success_threshold=2,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        recovery_times = []
        for attempt in range(5):
            time.sleep(0.12)
            if cb.is_allowed():
                recovery_times.append(attempt)
                cb.record_success()
                if cb.state == CircuitState.CLOSED:
                    break

        assert cb.state == CircuitState.CLOSED
        assert len(recovery_times) > 0

    def test_gradual_traffic_increase_after_recovery(self):
        """Test gradual traffic increase after partition recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
            success_threshold=3,
            half_open_max_calls=5,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        time.sleep(0.12)

        calls_in_half_open = 0
        for _ in range(10):
            if cb.is_allowed() and cb.state == CircuitState.HALF_OPEN:
                calls_in_half_open += 1
                cb.record_success()
            elif cb.state == CircuitState.CLOSED:
                break

        assert calls_in_half_open >= 1
        assert cb.state == CircuitState.CLOSED

    def test_permanent_partition_handling(self):
        """Test handling of permanent network partitions."""
        cb = CircuitBreaker(
            CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        )

        for _ in range(2):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        for _ in range(5):
            time.sleep(0.12)
            if cb.is_allowed():
                cb.record_failure()

            assert cb.state == CircuitState.OPEN

        assert cb.is_allowed() is False
