"""Connection utilities for service availability checks."""

from collections.abc import Callable
from time import time


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
