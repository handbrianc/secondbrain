"""Circuit breaker pattern implementation for service resilience.

This module provides a production-ready circuit breaker with a 3-state machine:
CLOSED -> OPEN -> HALF_OPEN -> CLOSED

The circuit breaker pattern helps prevent cascading failures by failing fast
when a service is consistently unavailable, and gradually testing recovery.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerError",
    "CircuitState",
]


class CircuitState(Enum):
    """Circuit breaker states.

    CLOSED: Normal operation, requests are allowed
    OPEN: Circuit is tripped, requests fail fast
    HALF_OPEN: Testing recovery, limited requests allowed
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        failure_threshold: Number of consecutive failures before opening circuit (default: 5)
        success_threshold: Number of consecutive successes in half-open to close (default: 2)
        recovery_timeout: Seconds to wait before transitioning from open to half-open (default: 30.0)
        half_open_max_calls: Maximum test calls allowed in half-open state (default: 3)
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""

    def __init__(
        self, message: str = "Circuit breaker is open", service_name: str | None = None
    ) -> None:
        """Initialize circuit breaker error.

        Args:
            message: Error message.
            service_name: Optional service name for context.
        """
        super().__init__(message)
        self.service_name = service_name
        self.message = message if not service_name else f"{message} ({service_name})"


class CircuitBreaker:
    """Thread-safe circuit breaker implementation.

    State Machine:
        CLOSED -> OPEN: After failure_threshold consecutive failures
        OPEN -> HALF_OPEN: After recovery_timeout seconds
        HALF_OPEN -> CLOSED: After success_threshold consecutive successes
        HALF_OPEN -> OPEN: On any failure during half-open

    Thread Safety:
        All state transitions are protected by a lock to ensure
        thread-safe operation in concurrent environments.
    """

    def __init__(
        self,
        config: CircuitBreakerConfig | None = None,
        service_name: str | None = None,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration. Uses defaults if None.
            service_name: Optional service name for logging and error context.
        """
        self.config = config or CircuitBreakerConfig()
        self.service_name = service_name or "unnamed"

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._current_recovery_timeout: float = self.config.recovery_timeout
        self._backoff_multiplier: int = 1

        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, checking for timeout transition."""
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        with self._lock:
            return self._failure_count

    @property
    def success_count(self) -> int:
        """Get current success count."""
        with self._lock:
            return self._success_count

    def _check_state_transition(self) -> None:
        """Check and perform state transitions based on timeout.

        Must be called with lock held.
        """
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._current_recovery_timeout:
                logger.debug(
                    "Circuit breaker [%s]: OPEN -> HALF_OPEN (timeout elapsed: %.2fs)",
                    self.service_name,
                    elapsed,
                )
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._success_count = 0

    def is_allowed(self) -> bool:
        """Check if a request is allowed to proceed.

        Returns:
            True if request should proceed, False if circuit is open.
        """
        with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                return False

            if self._state == CircuitState.HALF_OPEN:
                return self._half_open_calls < self.config.half_open_max_calls

            # All states covered above; raise for mypy exhaustiveness
            raise AssertionError(f"Unhandled CircuitState: {self._state}")

    def record_success(self) -> None:
        """Record a successful call.

        State transitions:
            HALF_OPEN -> CLOSED: After success_threshold consecutive successes
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls += 1

                if self._success_count >= self.config.success_threshold:
                    logger.debug(
                        "Circuit breaker [%s]: HALF_OPEN -> CLOSED (successes: %d/%d)",
                        self.service_name,
                        self._success_count,
                        self.config.success_threshold,
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    self._half_open_calls = 0
                    # Reset backoff on successful recovery
                    self._backoff_multiplier = 1
                    self._current_recovery_timeout = self.config.recovery_timeout
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call.

        State transitions:
            CLOSED -> OPEN: After failure_threshold consecutive failures
            HALF_OPEN -> OPEN: On any failure
        """
        with self._lock:
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.CLOSED:
                self._failure_count += 1

                if self._failure_count >= self.config.failure_threshold:
                    logger.warning(
                        "Circuit breaker [%s]: CLOSED -> OPEN (failures: %d/%d)",
                        self.service_name,
                        self._failure_count,
                        self.config.failure_threshold,
                    )
                    self._state = CircuitState.OPEN
                    self._success_count = 0

            elif self._state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker [%s]: HALF_OPEN -> OPEN (failure during recovery)",
                    self.service_name,
                )
                self._state = CircuitState.OPEN
                self._success_count = 0
                self._half_open_calls = 0
                # Double the recovery timeout with exponential backoff (max 300s)
                self._backoff_multiplier *= 2
                self._current_recovery_timeout = min(
                    self.config.recovery_timeout * self._backoff_multiplier, 300.0
                )
                logger.debug(
                    "Circuit breaker [%s]: Recovery timeout increased to %.2fs (multiplier: %dx)",
                    self.service_name,
                    self._current_recovery_timeout,
                    self._backoff_multiplier,
                )

    def reset(self) -> None:
        """Reset circuit breaker to initial closed state."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.debug(
                    "Circuit breaker [%s]: Reset from %s to CLOSED",
                    self.service_name,
                    self._state.value,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0
            self._backoff_multiplier = 1
            self._current_recovery_timeout = self.config.recovery_timeout

    def call(self, func: Callable[[], bool]) -> bool:
        """Execute a function through the circuit breaker.

        Args:
            func: Function to execute, should return bool indicating success.

        Returns:
            Result of function execution.

        Raises:
            CircuitBreakerError: If circuit is open and request is not allowed.
        """
        if not self.is_allowed():
            raise CircuitBreakerError(
                "Circuit breaker is open, request not allowed",
                service_name=self.service_name,
            )

        try:
            result = func()
            if result:
                self.record_success()
            else:
                self.record_failure()
            return result
        except Exception as e:
            logger.debug(
                "Circuit breaker [%s]: Exception during call: %s: %s",
                self.service_name,
                type(e).__name__,
                e,
            )
            self.record_failure()
            raise

    def get_state(self) -> CircuitState:
        """Get the current circuit state.

        Spec-conformant accessor delegating to the :attr:`state` property.
        Applies timeout-based transitions (e.g. OPEN -> HALF_OPEN) before
        reporting, exactly like :attr:`state`.

        Returns
        -------
            The current :class:`CircuitState`.
        """
        return self.state

    def get_failure_count(self) -> int:
        """Get the current consecutive failure count.

        Spec-conformant accessor delegating to the :attr:`failure_count`
        property.

        Returns
        -------
            Number of consecutive failures recorded in the current state.
        """
        return self.failure_count

    def get_state_info(self) -> dict[str, Any]:
        """Get detailed state information for debugging and monitoring.

        Returns:
            Dictionary with current state details.
        """
        with self._lock:
            self._check_state_transition()
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "half_open_calls": self._half_open_calls,
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "current_recovery_timeout": self._current_recovery_timeout,
                "backoff_multiplier": self._backoff_multiplier,
                "half_open_max_calls": self.config.half_open_max_calls,
            }
