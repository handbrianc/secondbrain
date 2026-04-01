"""Tests for rate limiting utilities."""

import time

from secondbrain.utils.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Test token bucket rate limiter functionality."""

    def test_init_default_values(self):
        """Test default initialization values."""
        limiter = TokenBucketRateLimiter(rate=10.0)
        assert limiter.rate == 10.0
        assert limiter.burst_size == 10
        assert limiter.available_tokens > 9.9

    def test_init_custom_values(self):
        """Test custom initialization values."""
        limiter = TokenBucketRateLimiter(rate=5.0, burst_size=20)
        assert limiter.rate == 5.0
        assert limiter.burst_size == 20
        assert limiter.available_tokens > 19.9

    def test_acquire_immediately_succeeds_with_burst(self):
        """Test that burst requests succeed immediately."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=5)

        start = time.monotonic()
        wait_time = limiter.acquire(tokens=3)
        elapsed = time.monotonic() - start

        assert wait_time == 0.0
        assert elapsed < 0.1  # Should be nearly instant
        assert limiter.available_tokens > 1.9  # 5 - 3 = 2

    def test_acquire_blocks_when_tokens_exhausted(self):
        """Test that acquire blocks when tokens are exhausted."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=5)

        # Exhaust all tokens
        limiter.acquire(tokens=5)
        assert limiter.available_tokens < 0.1

        # Next acquire should wait
        start = time.monotonic()
        wait_time = limiter.acquire(tokens=1)
        elapsed = time.monotonic() - start

        # Should wait ~0.1s for 1 token at 10/s rate
        assert wait_time > 0.05
        assert elapsed > 0.05

    def test_tokens_refill_over_time(self):
        """Test that tokens refill based on elapsed time."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=10)

        # Exhaust tokens
        limiter.acquire(tokens=10)

        # Wait for refill
        time.sleep(0.3)  # Should refill ~3 tokens at 10/s

        # Should have some tokens available now
        tokens = limiter.available_tokens
        assert 2.0 <= tokens <= 4.0  # Allow some variance

    def test_tokens_cannot_exceed_burst_size(self):
        """Test that token count cannot exceed burst size."""
        limiter = TokenBucketRateLimiter(rate=100.0, burst_size=5)

        # Wait longer than needed for full refill
        time.sleep(0.2)

        assert limiter.available_tokens <= 5.0

    def test_acquire_multiple_tokens(self):
        """Test acquiring multiple tokens at once."""
        limiter = TokenBucketRateLimiter(rate=10.0, burst_size=20)

        # Acquire 15 tokens
        wait_time = limiter.acquire(tokens=15)
        assert wait_time == 0.0
        assert limiter.available_tokens > 4.9

        # Acquire 3 more (should succeed immediately)
        wait_time = limiter.acquire(tokens=3)
        assert wait_time == 0.0
        assert limiter.available_tokens > 1.9

        # Acquire 5 more (should wait for 3 tokens)
        start = time.monotonic()
        wait_time = limiter.acquire(tokens=5)
        elapsed = time.monotonic() - start

        # Should wait ~0.3s for 3 tokens at 10/s
        assert wait_time > 0.2
        assert elapsed > 0.2

    def test_concurrent_access_thread_safe(self):
        """Test that rate limiter is thread-safe."""
        import threading

        limiter = TokenBucketRateLimiter(rate=100.0, burst_size=100)
        results = []

        def acquire_tokens():
            wait_time = limiter.acquire(tokens=1)
            results.append(wait_time)

        # Create multiple threads
        threads = [threading.Thread(target=acquire_tokens) for _ in range(50)]

        # Start all threads
        for t in threads:
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # All should succeed without errors
        assert len(results) == 50
        assert all(isinstance(r, float) for r in results)
