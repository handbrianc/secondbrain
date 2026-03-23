"""Comprehensive tests for embedding cache implementation."""

import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.utils.embedding_cache import EmbeddingCache


@pytest.mark.embedding_cache
class TestEmbeddingCacheBasic:
    """Test basic embedding cache functionality."""

    def test_cache_hit_exact_match(self):
        """Test exact text match returns cached embedding."""
        cache = EmbeddingCache(max_size=100)
        test_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Set embedding for text
        cache.set("Hello world", test_embedding)

        # Get should return cached embedding
        result = cache.get("Hello world")
        assert result == test_embedding
        assert cache.hits == 1
        assert cache.misses == 0

    def test_cache_miss_new_text(self):
        """Test new text not in cache returns None."""
        cache = EmbeddingCache(max_size=100)

        # Get non-existent text
        result = cache.get("new text never cached")
        assert result is None
        assert cache.hits == 0
        assert cache.misses == 1

    def test_cache_set_embedding(self):
        """Test storing embedding in cache."""
        cache = EmbeddingCache(max_size=100)
        test_embedding = [0.5, 0.6, 0.7, 0.8]

        # Set embedding
        cache.set("test text", test_embedding)

        # Verify it's cached
        assert cache.get("test text") == test_embedding
        assert cache.size == 1

    def test_cache_get_nonexistent(self):
        """Test getting non-existent key."""
        cache = EmbeddingCache(max_size=100)

        # Get non-existent key
        result = cache.get("nonexistent key")
        assert result is None
        assert cache.misses == 1


@pytest.mark.embedding_cache
class TestEmbeddingCacheBatchOperations:
    """Test batch operations on embedding cache."""

    def test_cache_batch_get(self):
        """Test batch cache lookup."""
        cache = EmbeddingCache(max_size=100)

        # Pre-populate cache
        cache.set("text1", [1.0, 1.0])
        cache.set("text2", [2.0, 2.0])

        # Get multiple texts
        results = {}
        for text in ["text1", "text2", "text3"]:
            results[text] = cache.get(text)

        assert results["text1"] == [1.0, 1.0]
        assert results["text2"] == [2.0, 2.0]
        assert results["text3"] is None

        # 2 hits, 1 miss
        assert cache.hits == 2
        assert cache.misses == 1

    def test_cache_batch_set(self):
        """Test batch cache storage."""
        cache = EmbeddingCache(max_size=100)

        # Set multiple embeddings
        batch_data = {
            "batch1": [0.1, 0.2],
            "batch2": [0.3, 0.4],
            "batch3": [0.5, 0.6],
        }

        for text, embedding in batch_data.items():
            cache.set(text, embedding)

        # Verify all are cached
        assert cache.size == 3
        for text, embedding in batch_data.items():
            assert cache.get(text) == embedding


@pytest.mark.embedding_cache
class TestEmbeddingCacheLRU:
    """Test LRU eviction policy."""

    def test_cache_size_limit(self):
        """Test max size enforcement with LRU eviction."""
        cache = EmbeddingCache(max_size=3)

        # Add 3 items
        cache.set("item1", [1.0])
        cache.set("item2", [2.0])
        cache.set("item3", [3.0])

        assert cache.size == 3

        # Add 4th item - should evict item1 (least recently used)
        cache.set("item4", [4.0])

        assert cache.size == 3
        assert cache.get("item1") is None  # Evicted
        assert cache.get("item2") == [2.0]
        assert cache.get("item3") == [3.0]
        assert cache.get("item4") == [4.0]

        # Access item2 to make it recently used
        cache.get("item2")

        # Add 5th item - should evict item3 (now LRU)
        cache.set("item5", [5.0])

        assert cache.get("item2") == [2.0]  # Still there (recently accessed)
        assert cache.get("item3") is None  # Evicted
        assert cache.get("item4") == [4.0]
        assert cache.get("item5") == [5.0]

    def test_cache_update_existing_key(self):
        """Test updating existing key moves it to end."""
        cache = EmbeddingCache(max_size=2)

        cache.set("key1", [1.0])
        cache.set("key2", [2.0])

        # Update key1 (should move to end)
        cache.set("key1", [1.5])

        # Add new key - should evict key2 (LRU)
        cache.set("key3", [3.0])

        assert cache.get("key1") == [1.5]  # Updated and still there
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == [3.0]


@pytest.mark.embedding_cache
class TestEmbeddingCacheGetOrCreate:
    """Test get_or_create convenience method."""

    def test_get_or_create_cache_hit(self):
        """Test get_or_create returns cached value on hit."""
        cache = EmbeddingCache(max_size=100)
        test_embedding = [0.1, 0.2, 0.3]

        # Pre-populate cache
        cache.set("cached text", test_embedding)

        # Generate function should not be called
        generate_fn = MagicMock(return_value=[9.9, 9.9])

        result = cache.get_or_create("cached text", generate_fn)

        assert result == test_embedding
        assert generate_fn.call_count == 0
        assert cache.hits == 1

    def test_get_or_create_cache_miss(self):
        """Test get_or_create generates and caches on miss."""
        cache = EmbeddingCache(max_size=100)

        # Generate function
        def generate_fn(text: str) -> list[float]:
            return [float(ord(c)) for c in text[:3]]

        result = cache.get_or_create("new text", generate_fn)

        assert result == [110.0, 101.0, 119.0]  # 'new'
        assert cache.get("new text") == result
        assert cache.misses == 1


@pytest.mark.embedding_cache
class TestEmbeddingCacheAsync:
    """Test async embedding cache functionality."""

    @pytest.mark.asyncio
    async def test_get_or_create_async_cache_hit(self):
        """Test async get_or_create returns cached value on hit."""
        cache = EmbeddingCache(max_size=100)
        test_embedding = [0.5, 0.6, 0.7]

        # Pre-populate cache
        cache.set("async cached", test_embedding)

        # Async generate function
        async_gen = AsyncMock(return_value=[8.8, 8.8])

        result = await cache.get_or_create_async("async cached", async_gen)

        assert result == test_embedding
        assert async_gen.call_count == 0
        assert cache.hits == 1

    @pytest.mark.asyncio
    async def test_get_or_create_async_cache_miss(self):
        """Test async get_or_create generates and caches on miss."""
        cache = EmbeddingCache(max_size=100)

        # Async generate function
        async def async_generate(text: str) -> list[float]:
            await asyncio.sleep(0)  # Simulate async work
            return [1.0, 2.0, 3.0]

        result = await cache.get_or_create_async("async new", async_generate)

        assert result == [1.0, 2.0, 3.0]
        assert cache.get("async new") == result
        assert cache.misses == 1


@pytest.mark.embedding_cache
class TestEmbeddingCacheClear:
    """Test cache clearing functionality."""

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = EmbeddingCache(max_size=100)

        # Populate cache
        cache.set("text1", [1.0])
        cache.set("text2", [2.0])
        _ = cache.get("text1")  # Create a hit

        # Verify populated
        assert cache.size == 2
        assert cache.hits == 1
        assert cache.misses == 0

        # Clear cache
        cache.clear()

        # Verify cleared
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.get("text1") is None
        assert cache.get("text2") is None


@pytest.mark.embedding_cache
class TestEmbeddingCacheStats:
    """Test cache statistics."""

    def test_cache_stats(self):
        """Test cache statistics (hits, misses, size)."""
        cache = EmbeddingCache(max_size=100)

        # Initial stats
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["hit_rate_percent"] == 0.0

        # Create some hits and misses
        cache.set("text1", [1.0])
        cache.set("text2", [2.0])

        _ = cache.get("text1")  # Hit
        _ = cache.get("text1")  # Hit
        _ = cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["hit_rate_percent"] == pytest.approx(66.67, rel=0.1)

    def test_cache_stats_after_clear(self):
        """Test stats are reset after clear."""
        cache = EmbeddingCache(max_size=100)

        cache.set("text", [1.0])
        _ = cache.get("text")
        cache.clear()

        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate_percent"] == 0.0


@pytest.mark.embedding_cache
class TestEmbeddingCacheEdgeCases:
    """Test edge cases and special scenarios."""

    def test_cache_zero_max_size(self):
        """Test cache with max_size=0 doesn't store anything."""
        cache = EmbeddingCache(max_size=0)

        cache.set("text", [1.0])
        assert cache.get("text") is None
        assert cache.size == 0

    def test_cache_contains_operator(self):
        """Test __contains__ operator."""
        cache = EmbeddingCache(max_size=100)

        assert "text1" not in cache

        cache.set("text1", [1.0])
        assert "text1" in cache
        assert "text2" not in cache

    def test_cache_len_operator(self):
        """Test __len__ operator."""
        cache = EmbeddingCache(max_size=100)

        assert len(cache) == 0

        cache.set("text1", [1.0])
        cache.set("text2", [2.0])
        assert len(cache) == 2

        cache.clear()
        assert len(cache) == 0

    def test_cache_hash_consistency(self):
        """Test that same text always produces same hash key."""
        cache = EmbeddingCache(max_size=100)

        # Set and get same text multiple times
        for _ in range(5):
            cache.set("consistent text", [1.0, 2.0])
            assert cache.get("consistent text") == [1.0, 2.0]

    def test_cache_update_same_key(self):
        """Test updating same key replaces embedding."""
        cache = EmbeddingCache(max_size=100)

        cache.set("key", [1.0, 2.0])
        cache.set("key", [3.0, 4.0])  # Update

        assert cache.get("key") == [3.0, 4.0]
        assert cache.size == 1  # Still only one entry


@pytest.mark.embedding_cache
class TestEmbeddingCacheThreadSafety:
    """Test thread safety of embedding cache."""

    def test_concurrent_get_set(self):
        """Test concurrent get and set operations."""
        cache = EmbeddingCache(max_size=1000)
        errors = []

        def writer():
            try:
                for i in range(100):
                    cache.set(f"text_{i}", [float(i)])
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for i in range(100):
                    cache.get(f"text_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t1 = threading.Thread(target=writer)
            t2 = threading.Thread(target=reader)
            threads.extend([t1, t2])

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

    def test_concurrent_get_or_create(self):
        """Test concurrent get_or_create operations."""
        cache = EmbeddingCache(max_size=1000)
        call_count = {"count": 0}
        lock = threading.Lock()

        def generate_fn(text: str) -> list[float]:
            with lock:
                call_count["count"] += 1
            return [float(call_count["count"])]

        def worker():
            for i in range(50):
                cache.get_or_create(f"concurrent_{i}", generate_fn)

        threads = [threading.Thread(target=worker) for _ in range(4)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All threads should complete without errors
        assert cache.size > 0
