"""Context-manager injection helpers for the failure injector.

These build on the core state machine (``FailureInjectorCore``) and expose the
friendly ``inject_<failure>`` context managers plus async-context support.
"""

import logging
import random
import time
from contextlib import contextmanager
from typing import Any

from secondbrain.utils.failure_injector.core import FailureInjectorCore
from secondbrain.utils.failure_injector.types import FailureConfig, FailureType

logger = logging.getLogger(__name__)


class FailureContextMixin(FailureInjectorCore):
    """Provide ``inject_*`` context managers operating on core failure state."""

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
            actual_latency = latency_ms / 1000.0
            if jitter_ms > 0:
                actual_latency += random.uniform(0, jitter_ms / 1000.0)  # nosec B311
            time.sleep(actual_latency)
            yield
        finally:
            with self._lock:
                if f"latency_{config_id}" in self._active_failures:
                    del self._active_failures[f"latency_{config_id}"]
            logger.info("Latency injection ended")

    # Async context manager support
    async def __aenter__(self) -> Any:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        self.reset()
