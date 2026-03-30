"""Enhanced observability with metrics and tracing.

This module provides observability features for SecondBrain:
- Performance metrics collection (custom and OpenTelemetry)
- Enhanced OpenTelemetry tracing
- Re-exports logging utilities from secondbrain.logging for backward compatibility
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from typing import Any

# Re-export logging utilities for backward compatibility
from secondbrain.logging import (
    CorrelationIdFilter,
    JSONFormatter,
    get_logger,
    get_request_id,
    get_trace_context,
    set_request_id,
    set_trace_context,
    setup_structured_logging,
)

__all__ = [
    "CorrelationIdFilter",
    "JSONFormatter",
    "MetricsCollector",
    "get_logger",
    "get_request_id",
    "get_trace_context",
    "log_operation_complete",
    "log_operation_start",
    "metrics",
    "set_request_id",
    "set_trace_context",
    "setup_structured_logging",
    "trace_span",
]


class MetricsCollector:
    """Collect and track performance metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self._metrics: dict[str, list[float]] = {}
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}

    def record(self, metric_name: str, value: float) -> None:
        """Record a metric value.

        Args:
            metric_name: Name of the metric
            value: Value to record
        """
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        self._metrics[metric_name].append(value)

    def increment(self, counter_name: str, amount: int = 1) -> None:
        """Increment a counter.

        Args:
            counter_name: Name of the counter
            amount: Amount to increment by
        """
        if counter_name not in self._counters:
            self._counters[counter_name] = 0
        self._counters[counter_name] += amount

    def set_gauge(self, gauge_name: str, value: float) -> None:
        """Set a gauge value.

        Args:
            gauge_name: Name of the gauge
            value: Value to set
        """
        self._gauges[gauge_name] = value

    def get_stats(self, metric_name: str) -> dict[str, float] | None:
        """Get statistics for a metric.

        Args:
            metric_name: Name of the metric

        Returns:
            Dictionary with count, min, max, mean, or None if not found
        """
        if metric_name not in self._metrics or not self._metrics[metric_name]:
            return None

        values = self._metrics[metric_name]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "sum": sum(values),
        }

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all collected metrics.

        Returns:
            Dictionary with all metrics, counters, and gauges
        """
        return {
            "histograms": {
                name: self.get_stats(name)
                for name in self._metrics
                if self.get_stats(name)
            },
            "counters": self._counters.copy(),
            "gauges": self._gauges.copy(),
        }


# Global metrics collector instance
metrics = MetricsCollector()


@contextmanager
def trace_span(operation_name: str, **attributes: Any):
    """Context manager for tracing operations with OpenTelemetry.

    Args:
        operation_name: Name of the operation being traced
        **attributes: Additional attributes to add to the span

    Yields:
        Span context for adding more attributes
    """
    from secondbrain.utils.tracing import get_tracer, is_tracing_enabled

    if not is_tracing_enabled():
        # No-op context manager when tracing is disabled
        yield None
        return

    tracer = get_tracer()

    with tracer.start_as_current_span(operation_name) as span:
        # Add standard attributes
        span.set_attribute("operation.name", operation_name)
        span.set_attribute("correlation_id", os.getenv("CORRELATION_ID", "unknown"))

        # Add custom attributes
        for key, value in attributes.items():
            span.set_attribute(key, str(value))

        try:
            yield span
            span.set_status("OK")
        except Exception as e:
            span.set_status("ERROR")
            span.record_exception(e)
            raise


def log_operation_start(operation: str, **context: Any) -> str:
    """Log the start of an operation.

    Args:
        operation: Name of the operation
        **context: Additional context information

    Returns:
        Correlation ID for this operation
    """
    correlation_id = str(uuid.uuid4())
    os.environ["CORRELATION_ID"] = correlation_id

    logger = logging.getLogger(__name__)
    logger.info(
        f"Operation started: {operation}",
        extra={
            "extra_fields": {
                "operation": operation,
                "correlation_id": correlation_id,
                **context,
            }
        },
    )

    return correlation_id


def log_operation_complete(
    operation: str, duration: float, success: bool, **context: Any
) -> None:
    """Log the completion of an operation.

    Args:
        operation: Name of the operation
        duration: Operation duration in seconds
        success: Whether the operation succeeded
        **context: Additional context information
    """
    logger = logging.getLogger(__name__)

    level = logging.INFO if success else logging.ERROR
    status = "completed" if success else "failed"

    logger.log(
        level,
        f"Operation {status}: {operation} (duration: {duration:.3f}s)",
        extra={
            "extra_fields": {
                "operation": operation,
                "duration_seconds": duration,
                "success": success,
                "correlation_id": os.getenv("CORRELATION_ID", "unknown"),
                **context,
            }
        },
    )

    # Record metrics
    metrics.record(f"operation.{operation}.duration", duration)
    metrics.increment(f"operation.{operation}.{'success' if success else 'failure'}")


logger = logging.getLogger(__name__)
