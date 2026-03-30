"""Rate limiting utilities for API calls and embedding generation."""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Token bucket rate limiter for controlling request rates.

    This limiter allows burst requests up to the bucket capacity, then
    enforces a steady rate by requiring tokens to be acquired before
    each request. Tokens refill at the specified rate.
    """

    def __init__(
        self,
        rate: float,
        burst_size: int = 10,
    ):
        """Initialize rate limiter.

        Args:
            rate: Requests per second.
            burst_size: Maximum burst size (bucket capacity).
        """
        self.rate = rate
        self.burst_size = burst_size
        self._tokens = float(burst_size)
        self._last_update = time.monotonic()
        self._lock = Lock()

    def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire.

        Returns:
            Time waited in seconds.
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update

            self._tokens = min(self.burst_size, self._tokens + elapsed * self.rate)
            self._last_update = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            needed = tokens - self._tokens
            wait_time = needed / self.rate

            logger.debug(
                "Rate limiting: waiting %.3fs for %.1f tokens (rate: %.1f/s)",
                wait_time,
                tokens,
                self.rate,
            )

            time.sleep(wait_time)

            self._tokens = 0.0
            return wait_time

    @property
    def available_tokens(self) -> float:
        """Get current available tokens."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            return min(self.burst_size, self._tokens + elapsed * self.rate)
