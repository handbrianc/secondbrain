"""Shared rate limiter for threading environments.

This module provides a rate limiter that can be shared across threads
using threading primitives for shared state.
"""

from __future__ import annotations

import threading
import time


class SharedRateLimiter:
    """Rate limiter with shared state across threads.

    Uses threading.Lock() to create thread-safe shared state.
    Implements a token bucket algorithm for rate limiting.

    Attributes
    ----------
    max_requests : int
        Maximum number of requests allowed in the time window.
    window_seconds : float
        Time window in seconds for rate limiting.
    """

    def __init__(
        self,
        max_requests: int = 100,
        window_seconds: float = 60.0,
    ) -> None:
        """Initialize shared rate limiter.

        Args:
            max_requests: Maximum requests allowed in window.
            window_seconds: Time window in seconds.
        """
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a rate limit slot.

        Returns
        -------
            True if request is allowed, False if rate limited.
        """
        current_time = time.monotonic()
        window_start = current_time - self._window_seconds

        with self._lock:
            # Clean old timestamps
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.pop(0)

            # Check if under limit
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(current_time)
                return True

            return False

    def wait_and_acquire(self, timeout: float | None = None) -> bool:
        """Wait for a rate limit slot and acquire it.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever).

        Returns
        -------
            True if acquired, False if timeout.
        """
        start_time = time.monotonic()

        while True:
            if self.acquire():
                return True

            # Calculate wait time until oldest timestamp expires
            with self._lock:
                if self._timestamps:
                    oldest = self._timestamps[0]
                    wait_time = (oldest + self._window_seconds) - time.monotonic()
                    wait_time = max(0.1, wait_time)  # Wait at least 100ms
                else:
                    wait_time = 0.1

            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)

            time.sleep(wait_time)

    @property
    def max_requests(self) -> int:
        """Get maximum requests per window."""
        return self._max_requests

    @property
    def window_seconds(self) -> float:
        """Get time window in seconds."""
        return self._window_seconds

    def get_remaining(self) -> int:
        """Get remaining requests in current window.

        Returns
        -------
            Number of remaining requests.
        """
        current_time = time.monotonic()
        window_start = current_time - self._window_seconds

        with self._lock:
            # Clean old timestamps
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.pop(0)

            return max(0, self._max_requests - len(self._timestamps))


# Global singleton instance
_shared_rate_limiter: SharedRateLimiter | None = None


def get_shared_rate_limiter(
    max_requests: int = 100, window_seconds: float = 60.0
) -> SharedRateLimiter:
    """Get or create the shared rate limiter singleton.

    Creates a SharedRateLimiter on first call, then
    returns the same instance on subsequent calls.

    Args:
        max_requests: Maximum requests allowed in window.
        window_seconds: Time window in seconds.

    Returns
    -------
        SharedRateLimiter instance.
    """
    global _shared_rate_limiter

    if _shared_rate_limiter is None:
        _shared_rate_limiter = SharedRateLimiter(
            max_requests=max_requests, window_seconds=window_seconds
        )

    return _shared_rate_limiter


def shutdown_shared_rate_limiter() -> None:
    """Shutdown the shared rate limiter.

    Call this when the application exits to clean up resources.
    """
    global _shared_rate_limiter

    _shared_rate_limiter = None
