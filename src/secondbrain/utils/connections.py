"""Connection utilities for service availability checks."""

import logging
import threading
from abc import abstractmethod
from collections.abc import Callable
from time import monotonic

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)

# Optional trace context import
try:
    from secondbrain.utils.tracing import (
        get_current_trace_context,
        inject_trace_context,
    )

    TRACE_CONTEXT_AVAILABLE = True
except ImportError:
    TRACE_CONTEXT_AVAILABLE = False
    get_current_trace_context = None  # type: ignore
    inject_trace_context = None  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
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





class ValidatableService:
    """Base class for services requiring connection validation with caching.

    This class provides thread-safe connection validation with TTL-based caching
    to reduce repeated network calls. Subclasses must implement _do_validate()
    to perform the actual service-specific validation.

    Optional circuit breaker support can be enabled by providing a
    circuit_breaker_config parameter during initialization.
    """

    def __init__(
        self,
        cache_ttl: float = 60.0,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize the validatable service.

        Args:
            cache_ttl: Time-to-live for connection cache in seconds.
            circuit_breaker_config: Optional circuit breaker configuration.
                If provided, circuit breaker will be enabled for this service.
        """
        self._connection_cache_ttl = cache_ttl
        self._connection_valid: bool | None = None
        self._connection_checked_at = 0.0
        self._lock = threading.Lock()

        self._circuit_breaker: CircuitBreaker | None = None
        self._circuit_breaker_enabled = circuit_breaker_config is not None

        if self._circuit_breaker_enabled:
            self._circuit_breaker = CircuitBreaker(
                config=circuit_breaker_config,
                service_name=self.__class__.__name__,
            )

    @property
    def circuit_breaker(self) -> CircuitBreaker | None:
        """Get the circuit breaker instance (if enabled)."""
        return self._circuit_breaker

    @property
    def is_circuit_breaker_enabled(self) -> bool:
        """Check if circuit breaker is enabled for this service."""
        return self._circuit_breaker_enabled

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
            logger.debug("Validation failed: %s: %s", type(e).__name__, e)
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

    def validate_connection_with_circuit_breaker(self, force: bool = False) -> bool:
        """Validate connection with circuit breaker protection.

        Raises:
            CircuitBreakerError: If circuit breaker is open.
        """
        if (
            self._circuit_breaker_enabled
            and self._circuit_breaker is not None
            and not self._circuit_breaker.is_allowed()
        ):
            logger.warning(
                "Circuit breaker open for service %s, failing fast",
                self.__class__.__name__,
            )
            raise CircuitBreakerError(
                "Circuit breaker is open",
                service_name=self.__class__.__name__,
            )

        result = self.validate_connection(force=force)

        if self._circuit_breaker_enabled and self._circuit_breaker is not None:
            if result:
                self._circuit_breaker.record_success()
            else:
                self._circuit_breaker.record_failure()

        return result

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
            logger.debug("Async validation failed: %s: %s", type(e).__name__, e)
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

    async def validate_connection_async_with_circuit_breaker(
        self, force: bool = False
    ) -> bool:
        """Check if service is available with circuit breaker protection (async).

        Args:
            force: If True, bypass cache and check connection.

        Returns:
            True if service is available, False otherwise.

        Raises:
            CircuitBreakerError: If circuit breaker is open.
        """
        if (
            self._circuit_breaker_enabled
            and self._circuit_breaker is not None
            and not self._circuit_breaker.is_allowed()
        ):
            logger.warning(
                "Circuit breaker open for service %s, failing fast",
                self.__class__.__name__,
            )
            raise CircuitBreakerError(
                "Circuit breaker is open",
                service_name=self.__class__.__name__,
            )

        result = await self.validate_connection_async(force=force)

        if self._circuit_breaker_enabled and self._circuit_breaker is not None:
            if result:
                self._circuit_breaker.record_success()
            else:
                self._circuit_breaker.record_failure()

        return result



