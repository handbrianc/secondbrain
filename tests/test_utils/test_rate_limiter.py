"""Tests for RateLimiter class with both sync and async operations."""

import asyncio
import time

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
        limiter = RateLimiter(max_requests=2, window_seconds=0.5)

        # Exhaust the limit
        limiter.acquire()
        limiter.acquire()

        # Next request should block
        start = time.time()
        limiter.acquire()
        elapsed = time.time() - start

        # Should have waited for at least some time
        assert elapsed >= 0.4

    def test_window_sliding(self) -> None:
        """Test that the sliding window works correctly."""
        limiter = RateLimiter(max_requests=2, window_seconds=0.3)

        # Make 2 requests
        limiter.acquire()
        limiter.acquire()

        # Should block now
        start = time.time()
        time.sleep(0.35)  # Wait for window to slide
        limiter.acquire()
        elapsed = time.time() - start

        # Should not block much since window has slid (allow some tolerance)
        assert elapsed < 0.5


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
        limiter = RateLimiter(max_requests=2, window_seconds=0.5)

        # Exhaust the limit
        await limiter.acquire_async()
        await limiter.acquire_async()

        # Next request should block
        start = time.time()
        await limiter.acquire_async()
        elapsed = time.time() - start

        # Should have waited for at least some time
        assert elapsed >= 0.4

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
        limiter = RateLimiter(max_requests=2, window_seconds=0.3)
        request_timestamps: list[float] = []

        async def make_request(request_id: int) -> None:
            await limiter.acquire_async()
            request_timestamps.append(time.time())

        # Make 4 concurrent requests
        start = time.time()
        tasks = [make_request(i) for i in range(4)]
        await asyncio.gather(*tasks)
        total_time = time.time() - start

        # With 2 requests per 0.3s, 4 requests should take at least 0.3s
        assert total_time >= 0.25


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
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)

        # Make several requests
        for _ in range(5):
            limiter.acquire()
            time.sleep(0.01)

        # All requests should be tracked
        assert len(limiter._requests) == 5

    @pytest.mark.asyncio
    async def test_async_request_timestamp_ordering(self) -> None:
        """Test that async request timestamps are properly maintained."""
        limiter = RateLimiter(max_requests=5, window_seconds=1.0)

        for _ in range(5):
            await limiter.acquire_async()
            await asyncio.sleep(0.01)

        assert len(limiter._requests) == 5
