"""Tests for RateLimiter class with both sync and async operations."""

import asyncio
import time
from unittest.mock import patch

import pytest

from secondbrain.embedding import RateLimiter


class TestRateLimiterSync:
    """Tests for synchronous rate limiting."""

    def test_initial_state(self) -> None:
        """Test initial rate limiter state."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)
        assert limiter.max_requests == 5
        assert limiter.window_seconds == 1.0

    def test_acquire_allows_within_limit(self) -> None:
        """Test that acquire allows requests within the limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)

        # Should not block for requests under the limit
        for _ in range(5):
            start = time.time()
            limiter.acquire()
            elapsed = time.time() - start
            assert elapsed < 0.1  # Should complete quickly

    def test_acquire_blocks_when_limit_exceeded(self) -> None:
        """Test that acquire blocks when limit is exceeded."""
        current_time = [0.0]

        def mock_time():
            return current_time[0]

        with (
            patch("secondbrain.embedding.time.sleep"),
            patch("secondbrain.embedding.time.time", side_effect=mock_time),
        ):
            limiter = RateLimiter(max_requests=2, window_seconds=0.5)
            limiter.acquire()
            limiter.acquire()
            current_time[0] = 0.6
            limiter.acquire()
            assert len(limiter._requests) >= 1

    def test_window_sliding(self) -> None:
        """Test that the sliding window works correctly."""
        with patch("secondbrain.embedding.time.sleep"):
            limiter = RateLimiter(max_requests=2, window_seconds=0.3)
            limiter.acquire()
            limiter.acquire()
            limiter.acquire()
            assert len(limiter._requests) >= 1


class TestRateLimiterAsync:
    """Tests for asynchronous rate limiting."""

    @pytest.mark.asyncio
    async def test_acquire_async_allows_within_limit(self) -> None:
        """Test that acquire_async allows requests within the limit."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)

        # Should not block for requests under the limit
        for _ in range(5):
            start = time.time()
            await limiter.acquire_async()
            elapsed = time.time() - start
            assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_acquire_async_blocks_when_limit_exceeded(self) -> None:
        """Test that acquire_async blocks when limit is exceeded."""
        with patch("secondbrain.embedding.time.sleep"):
            limiter = RateLimiter(max_requests=2, window_seconds=0.5)
            await limiter.acquire_async()
            await limiter.acquire_async()
            await limiter.acquire_async()
            assert len(limiter._requests) >= 1

    @pytest.mark.asyncio
    async def test_async_concurrent_access(self) -> None:
        """Test thread-safe async access from multiple coroutines."""
        limiter = RateLimiter(max_requests=10, window_seconds=1.0)
        request_times: list[float] = []

        async def make_request(request_id: int) -> None:
            start = time.time()
            await limiter.acquire_async()
            elapsed = time.time() - start
            request_times.append(elapsed)

        # Make 10 concurrent requests
        tasks = [make_request(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # All requests should complete quickly since we're under the limit
        for elapsed in request_times:
            assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_async_concurrent_with_limiting(self) -> None:
        """Test async concurrent access respects rate limits."""
        with patch("secondbrain.embedding.time.sleep"):
            limiter = RateLimiter(max_requests=2, window_seconds=0.3)
            request_count = 0

            async def make_request(request_id: int) -> None:
                nonlocal request_count
                await limiter.acquire_async()
                request_count += 1

            tasks = [make_request(i) for i in range(4)]
            await asyncio.gather(*tasks)
            assert request_count == 4


class TestRateLimiterEdgeCases:
    """Edge case tests for RateLimiter."""

    def test_zero_window(self) -> None:
        """Test rate limiter with zero window (no limiting)."""
        limiter = RateLimiter(max_requests=100, window_seconds=0.0)

        # Should not block even with many requests
        for _ in range(100):
            limiter.acquire()

    @pytest.mark.asyncio
    async def test_zero_window_async(self) -> None:
        """Test async rate limiter with zero window."""
        limiter = RateLimiter(max_requests=100, window_seconds=0.0)

        for _ in range(100):
            await limiter.acquire_async()

    def test_very_small_window(self) -> None:
        """Test rate limiter with very small window."""
        limiter = RateLimiter(max_requests=1, window_seconds=0.01)

        # First request
        limiter.acquire()

        # Second should block briefly
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        assert elapsed >= 0.005

    def test_large_max_requests(self) -> None:
        """Test rate limiter with large max requests."""
        limiter = RateLimiter(max_requests=1000, window_seconds=1.0)

        # Should allow many requests without blocking
        for _ in range(100):
            limiter.acquire()

    @pytest.mark.asyncio
    async def test_large_max_requests_async(self) -> None:
        """Test async rate limiter with large max requests."""
        limiter = RateLimiter(max_requests=1000, window_seconds=1.0)

        tasks = [limiter.acquire_async() for _ in range(100)]
        await asyncio.gather(*tasks)

    def test_request_timestamp_ordering(self) -> None:
        """Test that request timestamps are properly maintained."""
        with patch("secondbrain.embedding.time.sleep"):
            limiter = RateLimiter(max_requests=5, window_seconds=1.0)
            for _ in range(5):
                time.sleep(0.01)
                limiter.acquire()
            assert len(limiter._requests) == 5

    @pytest.mark.asyncio
    async def test_async_request_timestamp_ordering(self) -> None:
        """Test that async request timestamps are properly maintained."""
        with patch("secondbrain.embedding.time.sleep"):
            limiter = RateLimiter(max_requests=5, window_seconds=1.0)
            for _ in range(5):
                await asyncio.sleep(0.01)
                await limiter.acquire_async()
            assert len(limiter._requests) == 5
