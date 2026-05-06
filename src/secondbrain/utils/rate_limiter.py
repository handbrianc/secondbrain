"""Shared rate limiter for multiprocessing environments.

This module provides a rate limiter that can be shared across ProcessPoolExecutor
workers using multiprocessing.Manager() for shared state.
"""

from __future__ import annotations

import time
from multiprocessing.managers import BaseManager, SyncManager
from typing import Any


class SharedRateLimiter:
    """Rate limiter with shared state across multiprocessing workers.

    Uses multiprocessing.Manager() to create shared state that can be
    accessed by multiple processes. Implements a token bucket algorithm
    for rate limiting.

    Attributes
    ----------
    max_requests : int
        Maximum number of requests allowed in the time window.
    window_seconds : float
        Time window in seconds for rate limiting.
    """

    def __init__(
        self,
        manager: SyncManager,
        max_requests: int = 100,
        window_seconds: float = 60.0,
    ) -> None:
        """Initialize shared rate limiter.

        Args:
            manager: Multiprocessing Manager instance for shared state.
            max_requests: Maximum requests allowed in window.
            window_seconds: Time window in seconds.
        """
        self._manager = manager
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps = manager.list()
        self._lock = manager.Lock()

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
_manager: BaseManager | None = None


def get_shared_rate_limiter(
    max_requests: int = 100, window_seconds: float = 60.0
) -> SharedRateLimiter:
    """Get or create the shared rate limiter singleton.

    Creates a Manager and SharedRateLimiter on first call, then
    returns the same instance on subsequent calls.

    Args:
        max_requests: Maximum requests allowed in window.
        window_seconds: Time window in seconds.

    Returns
    -------
        SharedRateLimiter instance.
    """
    global _shared_rate_limiter, _manager

    if _shared_rate_limiter is None:
        # Create a manager for shared state
        _manager = SyncManager()
        _manager.start()
        _shared_rate_limiter = SharedRateLimiter(
            _manager, max_requests=max_requests, window_seconds=window_seconds
        )

    return _shared_rate_limiter


def shutdown_shared_rate_limiter() -> None:
    """Shutdown the shared rate limiter and manager.

    Call this when the application exits to clean up resources.
    """
    global _shared_rate_limiter, _manager

    if _manager is not None:
        _manager.shutdown()
        _manager = None

    _shared_rate_limiter = None
