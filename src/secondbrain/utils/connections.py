"""Connection utilities for service availability checks."""

import logging
import threading
import time
from abc import abstractmethod
from collections.abc import Callable
from time import monotonic

from secondbrain.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

__all__ = [
    "RateLimitedRetry",
    "ServiceUnavailableError",
    "ValidatableService",
    "ensure_service_available",
]


def ensure_service_available(service_name: str, validator: Callable[[], bool]) -> None:
    """Ensure a service is available, raise if not.

    Args:
        service_name: Name of the service to check.
        validator: Callable that returns True if service is available.

    Raises
    ------
        ServiceUnavailableError: If service is not available.
    """
    if not validator():
        raise ServiceUnavailableError(service_name)


class RateLimitedRetry:
    """Retry wrapper with exponential backoff and rate limiting.

    This class provides controlled retry behavior with exponential backoff,
    maximum retry limits, and rate limiting to avoid overwhelming services.

    Use this to wrap validation calls that may transiently fail:
        retry = RateLimitedRetry(max_retries=3, base_delay=0.5, max_delay=5.0)
        is_valid = retry.call(validator_function)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 5.0,
        exponential_base: float = 2.0,
    ) -> None:
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts.
            base_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            exponential_base: Base for exponential backoff calculation.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self._lock = threading.Lock()
        self._retry_count = 0
        self._last_retry_time = 0.0

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns
        -------
            Delay in seconds.
        """
        delay = min(
            self.base_delay * (self.exponential_base**attempt),
            self.max_delay,
        )
        # Add small jitter to prevent thundering herd
        return delay * (0.9 + 0.2 * (attempt % 5))  # 19% jitter

    def _can_retry(self) -> bool:
        """Check if another retry is allowed.

        Returns
        -------
            True if retry allowed, False otherwise.
        """
        with self._lock:
            if self._retry_count >= self.max_retries:
                return False
            self._retry_count += 1
            return True

    def _wait_before_retry(self) -> None:
        """Wait before next retry with rate limiting."""
        current_time = monotonic()
        elapsed = current_time - self._last_retry_time

        if elapsed < self.base_delay:
            time.sleep(self.base_delay - elapsed)

        self._last_retry_time = monotonic()

    def call(self, func: Callable[[], bool]) -> bool:
        """Call function with retry and rate limiting.

        Args:
            func: Function to call, should return bool.

        Returns
        -------
            Result of function call, False if all retries exhausted.
        """
        if not self._can_retry():
            return func()

        last_result = False
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                last_result = func()
                if last_result:
                    return True
            except Exception as e:
                logger.debug(f"Attempt {attempt + 1} failed: {e}")
                last_error = e

            if not self._can_retry():
                break

            self._wait_before_retry()

        if last_error:
            logger.debug(f"All retries exhausted: {last_error}")

        return last_result

    def reset(self) -> None:
        """Reset retry count."""
        with self._lock:
            self._retry_count = 0


class ValidatableService:
    """Base class for services requiring connection validation with caching.

    This class provides thread-safe connection validation with TTL-based caching
    to reduce repeated network calls. Subclasses must implement _do_validate()
    to perform the actual service-specific validation.
    """

    def __init__(self, cache_ttl: float = 60.0) -> None:
        """Initialize the validatable service.

        Args:
            cache_ttl: Time-to-live for connection cache in seconds.
        """
        self._connection_cache_ttl = cache_ttl
        self._connection_valid: bool | None = None
        self._connection_checked_at = 0.0
        self._lock = threading.Lock()

    def validate_connection(self, force: bool = False) -> bool:
        """Check if service is available with caching.

        Args:
            force: If True, bypass cache and check connection.

        Returns
        -------
            True if service is available, False otherwise.
        """
        current_time = monotonic()

        with self._lock:
            if (
                not force
                and self._connection_valid is not None
                and current_time - self._connection_checked_at
                < self._connection_cache_ttl
            ):
                return self._connection_valid

        try:
            self._connection_valid = self._do_validate()
        except Exception as e:
            logger.debug(f"Validation failed: {e}")
            self._connection_valid = False

        with self._lock:
            self._connection_checked_at = current_time

        return self._connection_valid

    def invalidate_connection_cache(self) -> None:
        """Clear cached connection state."""
        with self._lock:
            self._connection_valid = None
            self._connection_checked_at = 0.0

    def on_service_recovery(self) -> None:
        """Handle service recovery - clear cached connection state."""
        self.invalidate_connection_cache()

    @abstractmethod
    def _do_validate(self) -> bool:
        """Override in subclass to perform actual validation.

        Returns
        -------
            True if service is available.
        """
        raise NotImplementedError

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Check if service is available with caching (async version).

        Args:
            force: If True, bypass cache and check connection.

        Returns
        -------
            True if service is available, False otherwise.
        """
        current_time = monotonic()

        with self._lock:
            if (
                not force
                and self._connection_valid is not None
                and current_time - self._connection_checked_at
                < self._connection_cache_ttl
            ):
                return self._connection_valid

        try:
            self._connection_valid = await self._do_validate_async()
        except Exception as e:
            logger.debug(f"Async validation failed: {e}")
            self._connection_valid = False

        with self._lock:
            self._connection_checked_at = current_time

        return self._connection_valid

    async def _do_validate_async(self) -> bool:
        """Async version of validation to be overridden in subclass.

        Default implementation calls synchronous _do_validate() wrapped in
        asyncio.to_thread to avoid blocking the event loop.

        Returns
        -------
            True if service is available.
        """
        import asyncio

        return await asyncio.to_thread(self._do_validate)


class ServiceValidator:
    """Validator for service availability with caching.

    This class provides service availability checking with TTL-based caching.
    """

    _cache_ttl: float
    _last_check: float
    _is_valid: bool | None
    _validator: Callable[[], bool] | None

    def __init__(self, cache_ttl: float = 60.0) -> None:
        """Initialize the service validator.

        Args:
            cache_ttl: Time-to-live for connection cache in seconds.
        """
        self._cache_ttl = cache_ttl
        self._last_check = 0.0
        self._is_valid = None
        self._validator = None

    def configure(self, validator: Callable[[], bool]) -> None:
        """Configure the validator callback.

        Args:
            validator: Callable that returns True if service is available.
        """
        self._validator = validator
        self.invalidate()

    def is_available(self, force: bool = False) -> bool:
        """Check if service is available.

        Args:
            force: If True, bypass cache and check connection.

        Returns
        -------
            True if service is available.
        """
        if self._validator is None:
            raise RuntimeError("Validator not configured - call configure() first")

        if force or self._is_valid is None:
            self._is_valid = self._validator()
            self._last_check = monotonic()
            return self._is_valid

        if monotonic() - self._last_check < self._cache_ttl:
            return self._is_valid

        self._is_valid = self._validator()
        self._last_check = monotonic()
        return self._is_valid

    def invalidate(self) -> None:
        """Clear cached connection state."""
        self._is_valid = None
        self._last_check = 0.0

    def on_recovery(self) -> None:
        """Handle service recovery - clear cached state."""
        self.invalidate()
