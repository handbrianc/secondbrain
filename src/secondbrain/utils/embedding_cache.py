"""Embedding cache module for reducing redundant Ollama API calls.

This module provides a thread-safe, in-memory cache for embeddings with
LRU eviction policy to optimize performance and reduce API costs.
"""

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class EmbeddingCache:
    """Thread-safe embedding cache with LRU eviction policy.

    Caches embeddings by SHA256 hash of the input text to avoid redundant
    Ollama API calls for duplicate texts.

    Attributes:
        max_size: Maximum number of cache entries before eviction.
        hits: Number of cache hits (read-only, for statistics).
        misses: Number of cache misses (read-only, for statistics).

    Example:
        >>> cache = EmbeddingCache(max_size=1000)
        >>> embedding = cache.get_or_create("Hello world", lambda x: [0.1, 0.2])
        >>> cache.hits
        0
        >>> cache.misses
        1
        >>> # Second call with same text uses cache
        >>> embedding = cache.get_or_create("Hello world", lambda x: [0.1, 0.2])
        >>> cache.hits
        1
        >>> cache.misses
        1
    """

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize the embedding cache.

        Args:
            max_size: Maximum number of cache entries. Defaults to 1000.
        """
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_size = max_size
        self._hits: int = 0
        self._misses: int = 0

    @property
    def hits(self) -> int:
        """Get the number of cache hits."""
        return self._hits

    @property
    def misses(self) -> int:
        """Get the number of cache misses."""
        return self._misses

    @property
    def size(self) -> int:
        """Get the current number of cache entries."""
        return len(self._cache)

    def _generate_key(self, text: str) -> str:
        """Generate a cache key from text using SHA256 hash.

        Args:
            text: Input text to hash.

        Returns:
            Hexadecimal SHA256 hash string.
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> list[float] | None:
        """Get embedding from cache if available.

        Args:
            text: Text to look up in cache.

        Returns:
            Cached embedding if found, None otherwise.
        """
        key = self._generate_key(text)

        with self._lock:
            if key in self._cache:
                self._hits += 1
                self._cache.move_to_end(key)
                return self._cache[key]

            self._misses += 1
            return None

    def set(self, text: str, embedding: list[float]) -> None:
        """Store an embedding in the cache.

        If the cache is at capacity, the least recently used entry is evicted.

        Args:
            text: Text to use as cache key.
            embedding: Embedding vector to store.
        """
        key = self._generate_key(text)

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = embedding
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)

                self._cache[key] = embedding

    def get_or_create(
        self, text: str, generate_fn: Callable[[str], list[float]]
    ) -> list[float]:
        """Get embedding from cache or generate and cache it.

        This is a convenience method that combines cache lookup and generation.

        Args:
            text: Text to get or generate embedding for.
            generate_fn: Function that generates embedding for the text.

        Returns:
            Embedding vector (from cache or newly generated).
        """
        cached = self.get(text)
        if cached is not None:
            return cached

        embedding = generate_fn(text)
        self.set(text, embedding)
        return embedding

    def clear(self) -> None:
        """Clear all cached embeddings and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics including hits, misses, size,
            and hit rate percentage.
        """
        total_accesses = self._hits + self._misses
        hit_rate = (self._hits / total_accesses * 100) if total_accesses > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_rate_percent": round(hit_rate, 2),
        }

    def __contains__(self, text: str) -> bool:
        """Check if text is in cache.

        Args:
            text: Text to check.

        Returns:
            True if text is cached, False otherwise.
        """
        key = self._generate_key(text)
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        """Get the number of cached entries.

        Returns:
            Number of entries in the cache.
        """
        with self._lock:
            return len(self._cache)
