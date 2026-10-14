"""Shared rate limiter for threading environments.

This module provides a rate limiter that can be shared across threads
using threading primitives for shared state.

Sharing scope: ``SharedRateLimiter`` synchronises its sliding window with
``threading.Lock``, so a shared instance is shared across *threads within
one process*. The process-wide instance handed out by
:func:`get_shared_rate_limiter` is created per process — when embedding
generation runs inside ``ProcessPoolExecutor`` workers, each worker process
naturally holds its own limiter instance (no cross-process shared state).
Rate limiting is opt-in via the ``rate_limit_enabled`` configuration
setting (default ``False``).
"""

from __future__ import annotations

import collections
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
        self._timestamps: collections.deque[float] = collections.deque()
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
                self._timestamps.popleft()

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
                self._timestamps.popleft()

            return max(0, self._max_requests - len(self._timestamps))


_shared_limiter: SharedRateLimiter | None = None
_shared_limiter_lock = threading.Lock()


def get_shared_rate_limiter(
    max_requests: int = 100, window_seconds: float = 60.0
) -> SharedRateLimiter:
    """Return the process-wide shared rate limiter, creating it on first use.

    The first call creates the limiter with the given parameters; every
    subsequent call in the same process returns that same instance, so all
    threads (and all embedding provider instances) share one sliding window.
    Parameters from the first call win — later calls with different values
    still return the existing instance.

    Each process has its own instance: under a process pool, every worker
    holds an independent limiter (thread-level sharing only).

    Args:
        max_requests: Maximum requests allowed in window (first call only).
        window_seconds: Time window in seconds (first call only).

    Returns
    -------
        The process-wide SharedRateLimiter instance.
    """
    global _shared_limiter
    if _shared_limiter is None:
        with _shared_limiter_lock:
            if _shared_limiter is None:
                _shared_limiter = SharedRateLimiter(
                    max_requests=max_requests, window_seconds=window_seconds
                )
    return _shared_limiter


def reset_shared_rate_limiter() -> None:
    """Drop the process-wide shared limiter so the next call creates a fresh one.

    Intended for tests and re-initialisation after configuration changes.
    """
    global _shared_limiter
    with _shared_limiter_lock:
        _shared_limiter = None
