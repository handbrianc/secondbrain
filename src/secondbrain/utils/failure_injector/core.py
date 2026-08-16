"""Core state management and classification for the failure injector.

Holds the singleton lifecycle, the active-failure registry, and the
``should_fail`` / ``raise_failure`` decision logic. Independent of the
specific injection context managers so those live in their own module.
"""

import logging
import threading
import time
from typing import Any, Self

from secondbrain.utils.failure_injector.types import (
    FailureConfig,
    FailureType,
    InjectedConnectionError,
    InjectedFailureError,
    InjectedTimeoutError,
)

logger = logging.getLogger(__name__)


class FailureInjectorCore:
    """Singleton state and failure-decision logic for failure injection.

    Attributes:
        _instance: The global FailureInjector instance (subclass overrides type).
        _lock: Reentrant lock guarding the active-failure registry.
    """

    _instance: "Self | None" = None
    _lock = (
        threading.RLock()
    )  # RLock for reentrant locking (reset can be called within locked context)

    def __init__(self) -> None:
        """Initialize failure injector."""
        self._active_failures: dict[str, FailureConfig] = {}
        self._failure_count = 0
        self._start_time: float | None = None
        self._cleanup_callbacks: list[Any] = []

    @classmethod
    def get_instance(cls) -> Self:
        """Get singleton instance of failure injector.

        Returns:
            Global FailureInjector instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for test cleanup)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.reset()
                cls._instance = None

    def inject(
        self,
        failure_type: FailureType,
        duration: float | None = None,
        delay: float = 0.0,
        timeout_value: float = 30.0,
        error_message: str | None = None,
        probability: float = 1.0,
        repeat_count: int | None = None,
    ) -> None:
        """Inject a failure of the specified type.

        Args:
            failure_type: Type of failure to inject.
            duration: How long the failure should last (seconds). None for indefinite.
            delay: Delay before failure starts (seconds). Default: 0.
            timeout_value: Timeout value for timeout failures. Default: 30.0.
            error_message: Custom error message. Default: None.
            probability: Probability of failure (0.0-1.0). Default: 1.0.
            repeat_count: Number of times to repeat. None for unlimited.
        """
        config = FailureConfig(
            failure_type=failure_type,
            duration=duration,
            delay=delay,
            timeout_value=timeout_value,
            error_message=error_message,
            probability=probability,
            repeat_count=repeat_count,
        )

        failure_key = f"{failure_type.value}_{id(config)}"
        with self._lock:
            self._active_failures[failure_key] = config

        logger.info(
            "Failure injection started: type=%s, duration=%s, delay=%s",
            failure_type.value,
            duration,
            delay,
        )

        if duration is not None and delay == 0:
            self._schedule_cleanup(failure_key, duration)

    def reset(self) -> None:
        """Reset all active failures and cleanup state."""
        with self._lock:
            for callback in self._cleanup_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.warning("Cleanup callback failed: %s", e)

            self._active_failures.clear()
            self._cleanup_callbacks.clear()
            self._failure_count = 0
            self._start_time = None

            logger.info("Failure injector reset, all failures cleared")

    def is_failure_active(self, failure_type: FailureType) -> bool:
        """Check if a failure of the specified type is currently active.

        Args:
            failure_type: Type of failure to check.

        Returns:
            True if failure is active, False otherwise.
        """
        with self._lock:
            for config in self._active_failures.values():
                if config.failure_type == failure_type:
                    # Check if duration has expired
                    if config.duration is not None:
                        # For delayed failures, check if we're within the window
                        pass
                    return True
            return False

    def _schedule_cleanup(self, failure_key: str, duration: float) -> None:
        """Schedule automatic cleanup after duration.

        Args:
            failure_key: Key of the failure to clean up.
            duration: Duration in seconds.
        """

        def cleanup() -> None:
            with self._lock:
                if failure_key in self._active_failures:
                    del self._active_failures[failure_key]
                    logger.info("Failure cleanup: %s", failure_key)
                if timer in self._cleanup_callbacks:
                    self._cleanup_callbacks.remove(timer)

        timer = threading.Timer(duration, cleanup)
        timer.daemon = True
        self._cleanup_callbacks.append(timer)
        timer.start()

    def should_fail(self, failure_type: FailureType) -> bool:
        """Determine if current operation should fail based on active failures.

        Args:
            failure_type: Type of failure to check.

        Returns:
            True if operation should fail, False otherwise.
        """
        with self._lock:
            for config in self._active_failures.values():
                if config.failure_type == failure_type:
                    import random

                    # nosec B311: probability gate for chaos injection — RNG is
                    # intentionally non-cryptographic (only needs to be random,
                    # not secure).
                    if random.random() > config.probability:  # nosec B311
                        return False

                    return (
                        config.repeat_count is None
                        or self._failure_count < config.repeat_count
                    )

            return False

    def raise_failure(
        self, failure_type: FailureType, error_message: str | None = None
    ) -> None:
        """Raise the appropriate exception for the failure type.

        Args:
            failure_type: Type of failure to raise.
            error_message: Optional custom error message.

        Raises:
            InjectedTimeoutError: For timeout failures.
            InjectedConnectionError: For connection errors.
            InjectedFailureError: For general failures.
        """
        # Find any active config for this failure type
        config: FailureConfig | None = None
        with self._lock:
            for _key, cfg in self._active_failures.items():
                if cfg.failure_type == failure_type:
                    config = cfg
                    break
            self._failure_count += 1

        if failure_type == FailureType.TIMEOUT:
            timeout_value = config.timeout_value if config else 30.0
            msg = error_message or f"Injected timeout after {timeout_value}s"
            raise InjectedTimeoutError(msg, timeout_value)
        elif failure_type == FailureType.CONNECTION_ERROR:
            if error_message is not None:
                msg = error_message
            elif config is not None and config.error_message is not None:
                msg = config.error_message
            else:
                msg = "Injected connection error"
            raise InjectedConnectionError(msg)
        elif failure_type == FailureType.GENERAL_FAILURE:
            if error_message is not None:
                msg = error_message
            elif config is not None and config.error_message is not None:
                msg = config.error_message
            else:
                msg = "Injected general failure"
            raise InjectedFailureError(msg)
        elif failure_type == FailureType.SLOW_RESPONSE:
            # Slow response is handled differently - it delays instead of raising
            timeout_value = config.timeout_value if config else 30.0
            msg = error_message or f"Injected slow response ({timeout_value}s delay)"
            time.sleep(timeout_value)
            raise InjectedFailureError(msg)
        else:
            msg = error_message or f"Injected {failure_type.value}"
            raise InjectedFailureError(msg)
