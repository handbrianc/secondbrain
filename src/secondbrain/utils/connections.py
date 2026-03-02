"""Connection utilities for service availability checks."""

import threading
from abc import abstractmethod
from collections.abc import Callable
from time import monotonic, time


class ServiceUnavailableError(Exception):
    service_name: str

    def __init__(self, service_name: str, message: str | None = None) -> None:
        super().__init__(message or f"{service_name} is unavailable")
        self.service_name = service_name


def ensure_service_available(service_name: str, validator: Callable[[], bool]) -> None:
    """Ensure a service is available, raise if not.

    Args:
        service_name: Name of the service to check.
        validator: Callable that returns True if service is available.

    Raises:
        ServiceUnavailableError: If service is not available.
    """
    if not validator():
        raise ServiceUnavailableError(service_name)


class ValidatableService:
    """Base class for services requiring connection validation with caching.

    This class provides thread-safe connection validation with TTL-based caching
    to reduce repeated network calls. Subclasses must implement _do_validate()
    to perform the actual service-specific validation.

    Example:
        ```python
        class MyService(ValidatableService):
            def __init__(self, url: str, cache_ttl: float = 60.0) -> None:
                super().__init__(cache_ttl)
                self.url = url

            def _do_validate(self) -> bool:
                # Perform actual validation
                response = requests.get(self.url, timeout=5)
                return response.status_code == 200
        ```
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

        Returns:
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
        except Exception:
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

        Returns:
            True if service is available.
        """
        raise NotImplementedError

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Check if service is available with caching (async version).

        Args:
            force: If True, bypass cache and check connection.

        Returns:
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
        except Exception:
            self._connection_valid = False

        with self._lock:
            self._connection_checked_at = current_time

        return self._connection_valid

    async def _do_validate_async(self) -> bool:
        """Async version of validation to be overridden in subclass.

        Default implementation calls synchronous _do_validate() wrapped in
        asyncio.to_thread to avoid blocking.

        Returns:
            True if service is available.
        """
        import asyncio

        return await asyncio.to_thread(self._do_validate)


class ServiceValidator:
    service_name: str
    _cache_ttl: float
    _last_check: float
    _is_valid: bool | None
    _validator: Callable[[], bool] | None

    def __init__(self, cache_ttl: float = 60.0) -> None:
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

        Returns:
            True if service is available.
        """
        if self._validator is None:
            raise RuntimeError("Validator not configured - call configure() first")

        if force or self._is_valid is None:
            self._is_valid = self._validator()
            self._last_check = time()
            return self._is_valid

        if time() - self._last_check < self._cache_ttl:
            return self._is_valid

        self._is_valid = self._validator()
        self._last_check = time()
        return self._is_valid

    def invalidate(self) -> None:
        """Clear cached connection state."""
        self._is_valid = None
        self._last_check = 0.0

    def on_recovery(self) -> None:
        """Handle service recovery - clear cached state."""
        self.invalidate()
