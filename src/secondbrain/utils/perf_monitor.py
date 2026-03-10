"""Performance monitoring utilities for secondbrain."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class PerfMetrics:
    """Thread-safe performance metrics collector."""

    def __init__(self) -> None:
        self._metrics: dict[str, list[float]] = {}
        self._lock = Lock()

    def record(self, name: str, duration: float) -> None:
        """Record a duration for a metric."""
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = []
            self._metrics[name].append(duration)

    def get_stats(self, name: str) -> dict[str, Any] | None:
        """Get statistics for a metric."""
        with self._lock:
            if name not in self._metrics or not self._metrics[name]:
                return None

            durations = self._metrics[name]
            return {
                "count": len(durations),
                "total_seconds": sum(durations),
                "avg_seconds": sum(durations) / len(durations),
                "min_seconds": min(durations),
                "max_seconds": max(durations),
            }

    def reset(self, name: str | None = None) -> None:
        """Reset metrics for a name or all metrics."""
        with self._lock:
            if name:
                self._metrics[name] = []
            else:
                self._metrics.clear()


# Global metrics instance
metrics = PerfMetrics()


def timing(metric_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to track function execution time.

    Args:
        metric_name: Name of the metric to record.

    Returns:
        Decorated function that records execution time.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                metrics.record(metric_name, duration)
                logger.debug(f"{metric_name}: {duration:.3f}s")

        return wrapper

    return decorator


def async_timing(
    metric_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to track async function execution time.

    Args:
        metric_name: Name of the metric to record.

    Returns:
        Decorated async function that records execution time.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                metrics.record(metric_name, duration)
                logger.debug(f"{metric_name}: {duration:.3f}s")

        return wrapper

    return decorator
