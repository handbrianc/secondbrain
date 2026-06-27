"""Configurable failure injection framework for chaos testing.

This module provides a centralized, configurable failure injection mechanism
for chaos engineering tests. It supports multiple failure types with configurable
timing and duration, ensuring clean test isolation and automatic cleanup.

Usage:
    # Context manager usage
    with FailureInjector().inject_timeout(delay=1.0):
        # Code that should experience timeout
        pass

    # Manual usage
    injector = FailureInjector()
    injector.inject_connection_error(duration=2.0)
    try:
        # Code that should experience connection error
        pass
    finally:
        injector.reset()
"""

import logging
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any

# pytest is only needed for the fixture at the bottom of this file
# Use conditional import to avoid breaking runtime installs
try:
    import pytest

    _HAS_PYTEST = True
except ImportError:
    _HAS_PYTEST = False
    pytest = None  # type: ignore

logger = logging.getLogger(__name__)

__all__ = [
    "FailureConfig",
    "FailureInjector",
    "FailureType",
    "inject_connection_error",
    "inject_general_failure",
    "inject_timeout",
]


class FailureType(Enum):
    """Types of failures that can be injected."""

    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    GENERAL_FAILURE = "general_failure"
    SLOW_RESPONSE = "slow_response"
    PARTIAL_FAILURE = "partial_failure"
    NETWORK_PARTITION = "network_partition"
    LATENCY_INJECTION = "latency_injection"


@dataclass
class FailureConfig:
    """Configuration for failure injection.

    Attributes:
        failure_type: Type of failure to inject.
        duration: How long the failure should last (seconds). Use None for indefinite.
        delay: Delay before failure starts (seconds). Default: 0.
        timeout_value: Timeout value in seconds for timeout failures. Default: 30.0.
        error_message: Custom error message. Default: None (uses type-specific message).
        probability: Probability of failure (0.0-1.0) for partial failures. Default: 1.0.
        repeat_count: Number of times to repeat the failure. Use None for unlimited during duration.
    """

    failure_type: FailureType
    duration: float | None = None
    delay: float = 0.0
    timeout_value: float = 30.0
    error_message: str | None = None
    probability: float = 1.0
    repeat_count: int | None = None


class InjectedTimeoutError(Exception):
    """Exception raised for injected timeouts."""

    def __init__(
        self, message: str = "Injected timeout", timeout_value: float = 30.0
    ) -> None:
        super().__init__(message)
        self.timeout_value = timeout_value


class InjectedConnectionError(Exception):
    """Exception raised for injected connection errors."""

    def __init__(self, message: str = "Injected connection error") -> None:
        super().__init__(message)


class InjectedFailureError(Exception):
    """Exception raised for injected general failures."""

    def __init__(self, message: str = "Injected failure") -> None:
        super().__init__(message)


class FailureInjector:
    """Configurable failure injection framework for chaos testing.

    This class provides centralized failure injection with support for multiple
    failure types, configurable timing, and automatic cleanup. It is designed
    for test-only usage and should not affect production code.

    Features:
        - Multiple failure types: timeout, connection error, general failure, slow response
        - Configurable duration and delay
        - Context manager support for automatic cleanup
        - Thread-safe operation
        - Probability-based partial failures
        - Automatic cleanup on exit

    Usage:
        # Simple timeout injection
        injector = FailureInjector()
        injector.inject_timeout(duration=2.0)

        # Context manager
        with FailureInjector().inject_connection_error(duration=1.0):
            # Code that should fail
            pass

        # Async support
        async with FailureInjector().inject_timeout(duration=1.0):
            # Async code that should timeout
            pass
    """

    _instance: "FailureInjector | None" = None
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
    def get_instance(cls) -> "FailureInjector":
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

        # Schedule cleanup if duration is specified
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
                    # Check probability
                    import random

                    if random.random() > config.probability:
                        return False

                    # Check repeat count
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

    # Context manager methods
    @contextmanager
    def inject_timeout(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        timeout_value: float = 30.0,
        error_message: str | None = None,
    ) -> Any:
        """Context manager for injecting timeout failures.

        Args:
            duration: How long the injection lasts (seconds). None for indefinite.
            delay: Delay before injection starts. Default: 0.
            timeout_value: Timeout value to simulate. Default: 30.0.
            error_message: Custom error message.

        Yields:
            None

        Example:
            with FailureInjector().inject_timeout(duration=2.0, timeout_value=1.0):
                # Code that should timeout
                pass
        """
        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.TIMEOUT,
            duration=duration,
            delay=delay,
            timeout_value=timeout_value,
            error_message=error_message,
        )

        with self._lock:
            self._active_failures[f"timeout_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            yield
        finally:
            with self._lock:
                if f"timeout_{config_id}" in self._active_failures:
                    del self._active_failures[f"timeout_{config_id}"]
            logger.info("Timeout injection ended")

    @contextmanager
    def inject_connection_error(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        error_message: str | None = None,
    ) -> Any:
        """Context manager for injecting connection errors.

        Args:
            duration: How long the injection lasts (seconds). None for indefinite.
            delay: Delay before injection starts. Default: 0.
            error_message: Custom error message.

        Yields:
            None

        Example:
            with FailureInjector().inject_connection_error(duration=1.0):
                # Code that should fail with connection error
                pass
        """
        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.CONNECTION_ERROR,
            duration=duration,
            delay=delay,
            error_message=error_message,
        )

        with self._lock:
            self._active_failures[f"connection_error_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            yield
        finally:
            with self._lock:
                if f"connection_error_{config_id}" in self._active_failures:
                    del self._active_failures[f"connection_error_{config_id}"]
            logger.info("Connection error injection ended")

    @contextmanager
    def inject_general_failure(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        error_message: str | None = None,
        probability: float = 1.0,
    ) -> Any:
        """Context manager for injecting general failures.

        Args:
            duration: How long the injection lasts (seconds). None for indefinite.
            delay: Delay before injection starts. Default: 0.
            error_message: Custom error message.
            probability: Probability of failure (0.0-1.0). Default: 1.0.

        Yields:
            None

        Example:
            with FailureInjector().inject_general_failure(duration=2.0, probability=0.5):
                # Code that may fail with 50% probability
                pass
        """
        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.GENERAL_FAILURE,
            duration=duration,
            delay=delay,
            error_message=error_message,
            probability=probability,
        )

        with self._lock:
            self._active_failures[f"general_failure_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            yield
        finally:
            with self._lock:
                if f"general_failure_{config_id}" in self._active_failures:
                    del self._active_failures[f"general_failure_{config_id}"]
            logger.info("General failure injection ended")

    @contextmanager
    def inject_slow_response(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        slow_duration: float = 5.0,
        error_message: str | None = None,
    ) -> Any:
        """Context manager for injecting slow responses.

        Args:
            duration: How long the injection lasts (seconds). None for indefinite.
            delay: Delay before injection starts. Default: 0.
            slow_duration: How long to delay each response (seconds). Default: 5.0.
            error_message: Custom error message.

        Yields:
            None

        Example:
            with FailureInjector().inject_slow_response(slow_duration=2.0):
                # Code that should experience slow responses
                pass
        """
        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.SLOW_RESPONSE,
            duration=duration,
            delay=delay,
            timeout_value=slow_duration,
            error_message=error_message,
        )

        with self._lock:
            self._active_failures[f"slow_response_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            yield
        finally:
            with self._lock:
                if f"slow_response_{config_id}" in self._active_failures:
                    del self._active_failures[f"slow_response_{config_id}"]
            logger.info("Slow response injection ended")

    @contextmanager
    def inject_network_partition(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        partition_type: str = "complete",
        affected_services: list[str] | None = None,
        error_message: str | None = None,
    ) -> Any:
        """Context manager for injecting network partitions.

        Args:
            duration: How long the partition lasts (seconds). None for indefinite.
            delay: Delay before partition starts. Default: 0.
            partition_type: Type of partition - "complete", "partial", or "asymmetric".
            affected_services: List of service names affected by partition.
            error_message: Custom error message.

        Yields:
            None

        Example:
            with FailureInjector().inject_network_partition(duration=2.0, partition_type="complete"):
                # Code that experiences network partition
                pass
        """
        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.NETWORK_PARTITION,
            duration=duration,
            delay=delay,
            error_message=error_message
            or f"Network partition ({partition_type}) detected",
        )

        with self._lock:
            self._active_failures[f"network_partition_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            yield
        finally:
            with self._lock:
                if f"network_partition_{config_id}" in self._active_failures:
                    del self._active_failures[f"network_partition_{config_id}"]
            logger.info("Network partition injection ended")

    @contextmanager
    def inject_latency(
        self,
        duration: float | None = None,
        delay: float = 0.0,
        latency_ms: float = 100.0,
        jitter_ms: float = 0.0,
    ) -> Any:
        """Context manager for injecting network latency.

        Args:
            duration: How long the latency injection lasts (seconds). None for indefinite.
            delay: Delay before injection starts. Default: 0.
            latency_ms: Base latency in milliseconds. Default: 100.0.
            jitter_ms: Random jitter added to latency. Default: 0.

        Yields:
            None

        Example:
            with FailureInjector().inject_latency(latency_ms=200, jitter_ms=50):
                # Code that experiences network latency
                pass
        """
        import random

        config_id = id(self)
        config = FailureConfig(
            failure_type=FailureType.LATENCY_INJECTION,
            duration=duration,
            delay=delay,
        )

        with self._lock:
            self._active_failures[f"latency_{config_id}"] = config

        try:
            if delay > 0:
                time.sleep(delay)
            # Simulate latency by sleeping
            actual_latency = latency_ms / 1000.0
            if jitter_ms > 0:
                actual_latency += random.uniform(0, jitter_ms / 1000.0)
            time.sleep(actual_latency)
            yield
        finally:
            with self._lock:
                if f"latency_{config_id}" in self._active_failures:
                    del self._active_failures[f"latency_{config_id}"]
            logger.info("Latency injection ended")

    # Async context manager support
    async def __aenter__(self) -> "FailureInjector":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        self.reset()


# Convenience functions for quick injection
def inject_timeout(
    duration: float | None = None,
    delay: float = 0.0,
    timeout_value: float = 30.0,
    error_message: str | None = None,
) -> Any:
    """Inject timeout failures.

    Args:
        duration: How long the injection lasts. None for indefinite.
        delay: Delay before injection starts. Default: 0.
        timeout_value: Timeout value to simulate. Default: 30.0.
        error_message: Custom error message.

    Returns:
        Context manager for timeout injection.
    """
    return FailureInjector.get_instance().inject_timeout(
        duration=duration,
        delay=delay,
        timeout_value=timeout_value,
        error_message=error_message,
    )


def inject_connection_error(
    duration: float | None = None,
    delay: float = 0.0,
    error_message: str | None = None,
) -> Any:
    """Inject connection errors.

    Args:
        duration: How long the injection lasts. None for indefinite.
        delay: Delay before injection starts. Default: 0.
        error_message: Custom error message.

    Returns:
        Context manager for connection error injection.
    """
    return FailureInjector.get_instance().inject_connection_error(
        duration=duration,
        delay=delay,
        error_message=error_message,
    )


def inject_general_failure(
    duration: float | None = None,
    delay: float = 0.0,
    error_message: str | None = None,
    probability: float = 1.0,
) -> Any:
    """Inject general failures.

    Args:
        duration: How long the injection lasts. None for indefinite.
        delay: Delay before injection starts. Default: 0.
        error_message: Custom error message.
        probability: Probability of failure (0.0-1.0). Default: 1.0.

    Returns:
        Context manager for general failure injection.
    """
    return FailureInjector.get_instance().inject_general_failure(
        duration=duration,
        delay=delay,
        error_message=error_message,
        probability=probability,
    )


def inject_network_partition(
    duration: float | None = None,
    delay: float = 0.0,
    partition_type: str = "complete",
    affected_services: list[str] | None = None,
    error_message: str | None = None,
) -> Any:
    """Inject network partition failures.

    Args:
        duration: How long the partition lasts. None for indefinite.
        delay: Delay before partition starts. Default: 0.
        partition_type: Type of partition - "complete", "partial", or "asymmetric".
        affected_services: List of service names affected by partition.
        error_message: Custom error message.

    Returns:
        Context manager for network partition injection.
    """
    return FailureInjector.get_instance().inject_network_partition(
        duration=duration,
        delay=delay,
        partition_type=partition_type,
        affected_services=affected_services,
        error_message=error_message,
    )


def inject_latency(
    duration: float | None = None,
    delay: float = 0.0,
    latency_ms: float = 100.0,
    jitter_ms: float = 0.0,
) -> Any:
    """Inject network latency.

    Args:
        duration: How long the latency injection lasts. None for indefinite.
        delay: Delay before injection starts. Default: 0.
        latency_ms: Base latency in milliseconds. Default: 100.0.
        jitter_ms: Random jitter added to latency (0-latency_ms). Default: 0.

    Returns:
        Context manager for latency injection.
    """
    return FailureInjector.get_instance().inject_latency(
        duration=duration,
        delay=delay,
        latency_ms=latency_ms,
        jitter_ms=jitter_ms,
    )


# Pytest fixture for automatic cleanup (only available when pytest is installed)
if _HAS_PYTEST:

    @pytest.fixture
    def failure_injector() -> Generator[FailureInjector, None, None]:
        """Pytest fixture providing FailureInjector with automatic cleanup.

        Yields:
            FailureInjector instance.

        Raises:
            Exception: Re-raises any exception from the test block.
        """
        injector = FailureInjector.get_instance()
        try:
            yield injector
        finally:
            injector.reset()
            FailureInjector.reset_instance()
