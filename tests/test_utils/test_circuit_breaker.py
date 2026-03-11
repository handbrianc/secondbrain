"""Tests for CircuitBreaker and EmbeddingCache pattern implementations."""

import time
from unittest.mock import MagicMock

import pytest

from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitState,
)
from secondbrain.utils.embedding_cache import EmbeddingCache


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


class TestEmbeddingCache:
    """Tests for EmbeddingCache functionality."""

    def test_cache_hit_returns_cached_embedding(self) -> None:
        """Test that cache hit returns cached embedding."""
        cache = EmbeddingCache(max_size=10)
        text = "test text"
        embedding = [0.1, 0.2, 0.3]

        # First call - cache miss
        result = cache.get(text)
        assert result is None
        assert cache.misses == 1

        # Set the embedding
        cache.set(text, embedding)

        # Second call - cache hit
        result = cache.get(text)
        assert result == embedding
        assert cache.hits == 1

    def test_cache_miss_returns_none(self) -> None:
        """Test that cache miss returns None."""
        cache = EmbeddingCache(max_size=10)
        result = cache.get("nonexistent")

        assert result is None
        assert cache.misses == 1

    def test_set_updates_cache(self) -> None:
        """Test that set stores embedding in cache."""
        cache = EmbeddingCache(max_size=10)
        text = "test"
        embedding = [0.5, 0.6]

        cache.set(text, embedding)

        assert text in cache
        assert cache.size == 1

    def test_cache_eviction_on_max_size(self) -> None:
        """Test that LRU eviction occurs when cache is full."""
        cache = EmbeddingCache(max_size=3)

        # Fill cache
        cache.set("key1", [1.0])
        cache.set("key2", [2.0])
        cache.set("key3", [3.0])

        assert cache.size == 3

        # Add new key should evict least recently used (key1)
        cache.set("key4", [4.0])

        assert "key1" not in cache
        assert "key4" in cache
        assert cache.size == 3

    def test_lru_updates_on_access(self) -> None:
        """Test that accessing a key updates its LRU position."""
        cache = EmbeddingCache(max_size=2)

        cache.set("key1", [1.0])
        cache.set("key2", [2.0])

        # Access key1 to make it most recently used
        cache.get("key1")

        # Add new key should evict key2 (now LRU)
        cache.set("key3", [3.0])

        assert "key1" in cache
        assert "key2" not in cache
        assert "key3" in cache

    def test_get_or_create_returns_cached_if_available(self) -> None:
        """Test get_or_create returns cached embedding if available."""
        cache = EmbeddingCache(max_size=10)
        text = "test"
        embedding = [0.1, 0.2]

        cache.set(text, embedding)
        generate_fn = MagicMock(return_value=[9.9, 9.9])

        result = cache.get_or_create(text, generate_fn)

        assert result == embedding
        generate_fn.assert_not_called()

    def test_get_or_create_calls_generator_on_miss(self) -> None:
        """Test get_or_create calls generator on cache miss."""
        cache = EmbeddingCache(max_size=10)
        text = "test"
        embedding = [0.1, 0.2]

        generate_fn = MagicMock(return_value=embedding)

        result = cache.get_or_create(text, generate_fn)

        assert result == embedding
        generate_fn.assert_called_once_with(text)
        assert text in cache

    async def test_get_or_create_async_returns_cached(self) -> None:
        """Test async get_or_create returns cached embedding."""
        cache = EmbeddingCache(max_size=10)
        text = "test"
        embedding = [0.1, 0.2]

        cache.set(text, embedding)
        generate_fn = MagicMock()

        result = await cache.get_or_create_async(text, generate_fn)

        assert result == embedding
        generate_fn.assert_not_called()

    async def test_get_or_create_async_calls_generator(self) -> None:
        """Test async get_or_create calls async generator."""
        cache = EmbeddingCache(max_size=10)
        text = "test"
        embedding = [0.1, 0.2]

        async def async_gen(t: str) -> list[float]:
            return embedding

        result = await cache.get_or_create_async(text, async_gen)

        assert result == embedding
        assert text in cache

    def test_clear_resets_cache_and_stats(self) -> None:
        """Test that clear resets cache and statistics."""
        cache = EmbeddingCache(max_size=10)

        cache.set("key1", [1.0])
        cache.get("key1")  # Create a hit
        cache.get("nonexistent")  # Create a miss

        assert cache.size == 1
        assert cache.hits == 1
        assert cache.misses == 1

        cache.clear()

        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        assert "key1" not in cache

    def test_get_stats_returns_hit_rate(self) -> None:
        """Test that get_stats calculates hit rate correctly."""
        cache = EmbeddingCache(max_size=10)

        cache.set("key1", [1.0])
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == pytest.approx(66.67, rel=0.1)

    def test_get_stats_empty_cache(self) -> None:
        """Test get_stats with empty cache."""
        cache = EmbeddingCache(max_size=10)

        stats = cache.get_stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate_percent"] == 0.0

    def test_contains_returns_correct_result(self) -> None:
        """Test __contains__ returns correct result."""
        cache = EmbeddingCache(max_size=10)

        cache.set("key1", [1.0])

        assert "key1" in cache
        assert "key2" not in cache

    def test_len_returns_cache_size(self) -> None:
        """Test __len__ returns cache size."""
        cache = EmbeddingCache(max_size=10)

        assert len(cache) == 0

        cache.set("key1", [1.0])
        cache.set("key2", [2.0])

        assert len(cache) == 2

    def test_update_existing_key(self) -> None:
        """Test that updating existing key doesn't increase size."""
        cache = EmbeddingCache(max_size=10)

        cache.set("key1", [1.0])
        cache.set("key1", [2.0])  # Update

        assert cache.size == 1
        assert cache.get("key1") == [2.0]

    def test_max_size_zero(self) -> None:
        """Test cache with max_size=0."""
        cache = EmbeddingCache(max_size=0)

        # With max_size=0, set should not store anything
        cache.set("key1", [1.0])

        # Cache should remain empty
        assert cache.size == 0
        assert "key1" not in cache
        assert cache.get("key1") is None
