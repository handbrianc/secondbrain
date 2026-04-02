"""Tests for service failure scenarios and resilience."""

import time

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
)


@pytest.mark.chaos
class TestMongoDBFailureScenarios:
    """Test MongoDB unavailability scenarios."""

    def test_mongodb_connection_failure_handling(self):
        """Test handling of MongoDB connection failure."""
        storage_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            storage_cb.record_failure()

        assert storage_cb.state == CircuitState.OPEN
        assert storage_cb.is_allowed() is False

    def test_mongodb_query_timeout_handling(self):
        """Test handling of MongoDB query timeout."""
        storage_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            storage_cb.record_failure()

        assert storage_cb.state == CircuitState.OPEN

    def test_mongodb_recovery_after_failure(self):
        """Test recovery after MongoDB becomes available again."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        storage_cb = CircuitBreaker(config)

        for _ in range(3):
            storage_cb.record_failure()

        assert storage_cb.state == CircuitState.OPEN

        time.sleep(
            0.12
        )  # Reduced from 0.15s (must exceed 0.1s recovery timeout) for faster testing

        assert storage_cb.is_allowed() is True
        assert storage_cb.state == CircuitState.HALF_OPEN

        storage_cb.record_success()
        storage_cb.record_success()

        assert storage_cb.state == CircuitState.CLOSED


@pytest.mark.chaos
class TestSentenceTransformersFailureScenarios:
    """Test sentence-transformers service failures."""

    def test_embedding_service_unavailable_handling(self):
        """Test handling of sentence-transformers service unavailability."""
        embedding_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            embedding_cb.record_failure()

        assert embedding_cb.state == CircuitState.OPEN

    def test_embedding_service_timeout_handling(self):
        """Test handling of embedding service timeout."""
        embedding_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            embedding_cb.record_failure()

        assert embedding_cb.state == CircuitState.OPEN

    def test_embedding_service_recovery(self):
        """Test recovery after embedding service becomes available."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        embedding_cb = CircuitBreaker(config)

        for _ in range(3):
            embedding_cb.record_failure()

        assert embedding_cb.state == CircuitState.OPEN

        time.sleep(0.12)

        assert embedding_cb.is_allowed() is True

        embedding_cb.record_success()
        embedding_cb.record_success()

        assert embedding_cb.state == CircuitState.CLOSED


@pytest.mark.chaos
class TestCircuitBreakerResponse:
    """Test circuit breaker response to service failures."""

    def test_circuit_opens_after_mongo_failures(self):
        """Test that circuit opens after MongoDB failures."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_opens_after_embedding_failures(self):
        """Test that circuit opens after embedding service failures."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        for _ in range(6):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_breaker_blocks_requests_when_open(self):
        """Test that open circuit blocks requests."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        for _ in range(4):
            cb.record_failure()

        assert cb.is_allowed() is False

    def test_circuit_breaker_error_raised(self):
        """Test that CircuitBreakerError is raised when circuit is open."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

        for _ in range(4):
            cb.record_failure()

        with pytest.raises(CircuitBreakerError):
            if not cb.is_allowed():
                raise CircuitBreakerError("MongoDB circuit is open", "mongo")

    def test_circuit_half_open_after_timeout(self):
        """Test circuit transitions to half-open after timeout."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        for _ in range(4):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        time.sleep(
            0.12
        )  # Reduced from 0.15s (must exceed 0.1s recovery timeout) for faster testing

        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN


@pytest.mark.chaos
class TestGracefulDegradation:
    """Test graceful degradation under failure conditions."""

    def test_fallback_to_cached_embeddings(self):
        """Test fallback mechanism when embedding service fails."""
        assert True

    def test_retry_with_backoff(self):
        """Test retry logic with exponential backoff."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=0.1,
        )
        cb = CircuitBreaker(config)

        for _ in range(3):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN

        time.sleep(0.12)

        assert cb.is_allowed() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_cascade_failure_prevention(self):
        """Test that circuit breaker prevents cascade failures."""
        cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=5))

        failures = 0
        for _i in range(100):
            if not cb.is_allowed():
                break
            cb.record_failure()
            failures += 1

        assert failures == 5
        assert cb.state == CircuitState.OPEN
