"""Module-level convenience entry points and the pytest fixture."""

from collections.abc import Generator
from typing import Any

from secondbrain.utils.failure_injector.injector import FailureInjector

# pytest is only needed for the fixture at the bottom of this file
# Use conditional import to avoid breaking runtime installs
try:
    import pytest

    _HAS_PYTEST = True
except ImportError:
    _HAS_PYTEST = False
    pytest = None  # type: ignore

failure_injector: Any = None


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
    def failure_injector() -> Generator[FailureInjector]:
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
