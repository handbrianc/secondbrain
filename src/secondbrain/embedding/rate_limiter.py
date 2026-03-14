"""Rate limiter for API requests.

Implements sliding window rate limiting with configurable max requests
and time window. Provides both synchronous and asynchronous interfaces.
"""

import asyncio
import time
from collections import deque
from threading import Lock

from secondbrain.config import get_config


class RateLimiter:
    """Rate limiter for API requests.

    Implements sliding window rate limiting with configurable max requests
    and time window. Provides both synchronous and asynchronous interfaces.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float | None = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window. If None, uses config.
            window_seconds: Time window in seconds. If None, uses config.
        """
        config = get_config()
        self.max_requests: int = (
            max_requests if max_requests is not None else config.rate_limit_max_requests
        )
        self.window_seconds: float = (
            window_seconds
            if window_seconds is not None
            else config.rate_limit_window_seconds
        )
        self._lock = Lock()
        self._async_lock = asyncio.Lock()
        self._requests: deque[float] = deque()

    def acquire(self) -> None:
        """Acquire rate limit token, blocking if necessary."""
        current_time = time.time()

        with self._lock:
            cutoff = current_time - self.window_seconds
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()

            while len(self._requests) >= self.max_requests:
                oldest = self._requests[0]
                sleep_time = self.window_seconds - (current_time - oldest)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                current_time = time.time()
                cutoff = current_time - self.window_seconds
                while self._requests and self._requests[0] < cutoff:
                    self._requests.popleft()

            self._requests.append(current_time)

    async def acquire_async(self) -> None:
        """Acquire rate limit token asynchronously, awaiting if necessary.

        Uses asyncio.Lock for thread-safe async operations.
        """
        current_time = time.time()

        async with self._async_lock:
            cutoff = current_time - self.window_seconds
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()

            while len(self._requests) >= self.max_requests:
                oldest = self._requests[0]
                sleep_time = self.window_seconds - (current_time - oldest)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                current_time = time.time()
                cutoff = current_time - self.window_seconds
                while self._requests and self._requests[0] < cutoff:
                    self._requests.popleft()

            self._requests.append(current_time)
