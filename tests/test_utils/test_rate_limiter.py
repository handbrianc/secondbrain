"""Tests for SharedRateLimiter."""

import time

import pytest

from secondbrain.utils.rate_limiter import SharedRateLimiter


@pytest.fixture(autouse=True, scope="module")
def _fast_rate_limiter_time():
    """Accelerate rate-limiter tests by advancing time virtually.

    Shares the same time-mocking approach as _fast_circuit_breaker_time.
    Patch time.sleep to accumulate virtual time; time.monotonic returns
    the virtual base.  Eliminates ~750ms of artificial time.sleep calls.
    """
    _orig_sleep = time.sleep
    _orig_monotonic = time.monotonic

    _lazy_base: float | None = None

    def _fast_monotonic() -> float:
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        return _lazy_base  # type: ignore[return-value]

    def _fast_sleep(seconds: float) -> None:
        if seconds <= 0:
            return
        nonlocal _lazy_base
        if _lazy_base is None:
            _lazy_base = _orig_monotonic()
        _lazy_base += seconds + 1e-6

    time.sleep = _fast_sleep  # type: ignore[method-assign]
    time.monotonic = _fast_monotonic  # type: ignore[method-assign]
    yield
    time.sleep = _orig_sleep  # type: ignore[method-assign]
    time.monotonic = _orig_monotonic


class TestSharedRateLimiterInit:
    """Test SharedRateLimiter initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        limiter = SharedRateLimiter(max_requests=100, window_seconds=60.0)

        assert limiter.max_requests == 100
        assert limiter.window_seconds == 60.0
        assert len(limiter._timestamps) == 0

    def test_init_with_custom_values(self):
        """Test initialization with custom rate limit parameters."""
        limiter = SharedRateLimiter(max_requests=50, window_seconds=30.0)

        assert limiter.max_requests == 50
        assert limiter.window_seconds == 30.0

    def test_init_creates_shared_state(self):
        """Test that initialization creates shared list and lock."""
        limiter = SharedRateLimiter(max_requests=100, window_seconds=60.0)

        # Verify timestamps is a list
        assert hasattr(limiter._timestamps, 'append')
        assert hasattr(limiter._timestamps, 'pop')
        assert hasattr(limiter._lock, 'acquire')
        assert hasattr(limiter._lock, 'release')


class TestSharedRateLimiterAcquire:
    """Test SharedRateLimiter.acquire() method."""

    def test_acquire_allows_requests_under_limit(self):
        """Test that acquire allows requests when under the limit."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        # Should allow 5 requests
        for i in range(5):
            assert limiter.acquire() is True

        # 6th request should be denied
        assert limiter.acquire() is False

    def test_acquire_rejects_over_limit(self):
        """Test that acquire rejects requests when over the limit."""
        limiter = SharedRateLimiter(max_requests=3, window_seconds=60.0)

        # Fill the limit
        for _ in range(3):
            limiter.acquire()

        # All subsequent requests should fail
        assert limiter.acquire() is False
        assert limiter.acquire() is False

    def test_acquire_allows_after_window_expires(self):
        """Test that acquire allows requests after time window expires."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Use up the limit
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        assert limiter.acquire() is False

        # Wait for window to expire
        time.sleep(0.15)

        # Should be able to acquire again
        assert limiter.acquire() is True

    def test_acquire_cleans_old_timestamps(self):
        """Test that acquire removes timestamps outside the window."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Make 2 requests
        limiter.acquire()
        limiter.acquire()

        # Wait for window to expire
        time.sleep(0.15)

        # Make 2 more requests - should clean old timestamps
        assert limiter.acquire() is True
        assert limiter.acquire() is True

        # Should still be at limit
        assert limiter.acquire() is False

    def test_acquire_is_thread_safe(self):
        """Test that acquire handles concurrent access correctly."""
        import threading

        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)

        results = []
        lock = threading.Lock()

        def make_request():
            result = limiter.acquire()
            with lock:
                results.append(result)

        # Create 20 concurrent requests
        threads = [threading.Thread(target=make_request) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Exactly 10 should succeed
        assert sum(results) == 10
        assert results.count(False) == 10


class TestSharedRateLimiterWaitAndAcquire:
    """Test SharedRateLimiter.wait_and_acquire() method."""

    def test_wait_and_acquire_immediate_success(self):
        """Test wait_and_acquire when slot is immediately available."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        # Should succeed immediately
        assert limiter.wait_and_acquire(timeout=1.0) is True

    def test_wait_and_acquire_waits_for_slot(self):
        """Test wait_and_acquire waits for slot to become available."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.2)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()

        # Should wait and then succeed
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=1.0)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.15  # Should have waited for window

    def test_wait_and_acquire_respects_timeout(self):
        """Test wait_and_acquire returns False on timeout."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=10.0)

        # Use the limit
        limiter.acquire()

        # Should timeout after 0.2 seconds
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=0.2)
        elapsed = time.monotonic() - start

        assert result is False
        assert elapsed >= 0.15
        assert elapsed < 0.5

    def test_wait_and_acquire_with_no_timeout(self):
        """Test wait_and_acquire waits indefinitely without timeout."""
        limiter = SharedRateLimiter(max_requests=2, window_seconds=0.1)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()

        # Should eventually succeed (with short timeout for test)
        start = time.monotonic()
        result = limiter.wait_and_acquire(timeout=0.5)
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed >= 0.05


class TestSharedRateLimiterGetRemaining:
    """Test SharedRateLimiter.get_remaining() method."""

    def test_get_remaining_starts_at_max(self):
        """Test that get_remaining returns max_requests initially."""
        limiter = SharedRateLimiter(max_requests=10, window_seconds=60.0)

        assert limiter.get_remaining() == 10

    def test_get_remaining_decreases_with_requests(self):
        """Test that get_remaining decreases after each acquire."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=60.0)

        assert limiter.get_remaining() == 5
        limiter.acquire()
        assert limiter.get_remaining() == 4
        limiter.acquire()
        assert limiter.get_remaining() == 3

    def test_get_remaining_respects_window(self):
        """Test that get_remaining increases after window expires."""
        limiter = SharedRateLimiter(max_requests=3, window_seconds=0.1)

        # Use up the limit
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for window to expire
        time.sleep(0.15)

        # Should be reset
        assert limiter.get_remaining() == 3

    def test_get_remaining_never_negative(self):
        """Test that get_remaining never returns negative value."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)

        limiter.acquire()
        # Multiple acquires should not affect remaining
        limiter.acquire()
        limiter.acquire()

        assert limiter.get_remaining() >= 0


class TestRateLimiterEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_max_requests(self):
        """Test rate limiter with max_requests=0."""
        limiter = SharedRateLimiter(max_requests=0, window_seconds=60.0)

        # Should never allow requests
        assert limiter.acquire() is False
        assert limiter.acquire() is False
        assert limiter.get_remaining() == 0

    def test_very_short_window(self):
        """Test rate limiter with very short time window."""
        limiter = SharedRateLimiter(max_requests=5, window_seconds=0.1)

        # Should allow requests initially
        for _ in range(5):
            assert limiter.acquire() is True

        # Should block after limit
        assert limiter.acquire() is False

        # Should reset after window expires (use 2x window for safety)
        time.sleep(0.25)
        assert limiter.acquire() is True

    def test_very_large_max_requests(self):
        """Test rate limiter with very large max_requests."""
        limiter = SharedRateLimiter(max_requests=10000, window_seconds=60.0)

        # Should allow many requests
        for _ in range(1000):
            assert limiter.acquire() is True

        assert limiter.get_remaining() == 9000

    def test_exact_limit_boundary(self):
        """Test behavior exactly at the limit boundary."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=60.0)

        # First request should succeed
        assert limiter.acquire() is True
        assert limiter.get_remaining() == 0

        # Second should fail
        assert limiter.acquire() is False
        assert limiter.get_remaining() == 0

        # Third should also fail
        assert limiter.acquire() is False

    def test_wait_and_acquire_empty_timestamps(self):
        """Test wait_and_acquire when timestamps list is empty (edge case)."""
        limiter = SharedRateLimiter(max_requests=1, window_seconds=0.1)

        # First acquire succeeds
        assert limiter.acquire() is True

        # Wait for window to expire so timestamps are cleaned
        time.sleep(0.15)

        # Now wait_and_acquire should work with empty timestamps path
        result = limiter.wait_and_acquire(timeout=0.5)
        assert result is True
