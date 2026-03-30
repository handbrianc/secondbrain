"""OpenTelemetry metrics API integration for SecondBrain.

This module provides a unified metrics interface that supports both:
- OpenTelemetry metrics API (when available)
- Custom MetricsCollector fallback (for offline/dev mode)

Standard metrics defined:
- document.ingested (Counter): Number of documents ingested
- search.query.duration (Histogram): Duration of search queries
- embedding.cache.hit_rate (Gauge): Embedding cache hit rate
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Check if OpenTelemetry metrics API is available
try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )

    OTTEL_METRICS_AVAILABLE = True
except ImportError:
    OTTEL_METRICS_AVAILABLE = False
    otel_metrics = None  # type: ignore

# Global state
_meter: Any = None
_metrics_initialized: bool = False


def is_metrics_enabled() -> bool:
    """Check if OpenTelemetry metrics is enabled.

    Returns:
        True if OTEL_METRICS_ENABLED env var is set to "true" and OTel is available.
    """
    if not OTTEL_METRICS_AVAILABLE:
        return False
    return __import__("os").getenv("OTEL_METRICS_ENABLED", "false").lower() == "true"


def setup_metrics(service_name: str = "secondbrain") -> None:
    """Set up OpenTelemetry metrics.

    Args:
        service_name: Name of the service for metrics.

    Note:
        If OpenTelemetry is not installed or metrics not enabled, this is a no-op.
    """
    global _meter, _metrics_initialized

    if not OTTEL_METRICS_AVAILABLE:
        logger.debug("OpenTelemetry metrics not available")
        return

    if not is_metrics_enabled():
        logger.debug("OpenTelemetry metrics not enabled")
        return

    if _metrics_initialized:
        return

    try:
        # Create meter provider
        resource = otel_metrics.Resource.create(
            {
                "service.name": service_name,
            }
        )

        # Add console exporter for development
        exporter = ConsoleMetricExporter()
        reader = PeriodicExportingMetricReader(exporter)
        provider = MeterProvider(resource=resource, metric_readers=[reader])

        # Set as global provider
        otel_metrics.set_meter_provider(provider)

        # Get meter
        _meter = otel_metrics.get_meter(service_name)
        _metrics_initialized = True

        logger.info("OpenTelemetry metrics enabled for %s", service_name)

    except Exception as e:
        logger.warning("Failed to setup OpenTelemetry metrics: %s", e)


class OTelMetricsCollector:
    """OpenTelemetry metrics collector wrapper.

    Provides Counter, Histogram, and Gauge primitives via OTel API.
    Falls back gracefully when OTel is unavailable.
    """

    def __init__(self):
        """Initialize OTel metrics collector."""
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._gauges: dict[str, Any] = {}
        self._setup_standard_metrics()

    def _setup_standard_metrics(self) -> None:
        """Set up standard SecondBrain metrics."""
        if not OTTEL_METRICS_AVAILABLE or not is_metrics_enabled():
            return

        # Counter: document.ingested
        self._counters["document.ingested"] = self._create_counter(
            "document.ingested",
            "Number of documents ingested",
            "1",
        )

        # Histogram: search.query.duration
        self._histograms["search.query.duration"] = self._create_histogram(
            "search.query.duration",
            "Duration of search queries in seconds",
            "s",
        )

        # Gauge: embedding.cache.hit_rate
        self._gauges["embedding.cache.hit_rate"] = self._create_gauge(
            "embedding.cache.hit_rate",
            "Embedding cache hit rate",
            "1",
        )

    def _create_counter(self, name: str, description: str, unit: str = "1") -> Any:
        """Create or get a counter metric."""
        if name in self._counters:
            return self._counters[name]

        if _meter is None:
            return _NoOpCounter()

        counter = _meter.create_counter(name, unit=unit, description=description)
        self._counters[name] = counter
        return counter

    def _create_histogram(self, name: str, description: str, unit: str = "1") -> Any:
        """Create or get a histogram metric."""
        if name in self._histograms:
            return self._histograms[name]

        if _meter is None:
            return _NoOpHistogram()

        histogram = _meter.create_histogram(name, unit=unit, description=description)
        self._histograms[name] = histogram
        return histogram

    def _create_gauge(self, name: str, description: str, unit: str = "1") -> Any:
        """Create or get a gauge metric."""
        if name in self._gauges:
            return self._gauges[name]

        if _meter is None:
            return _NoOpGauge()

        gauge = _meter.create_observable_gauge(name, unit=unit, description=description)
        self._gauges[name] = gauge
        return gauge

    def increment_counter(self, name: str, amount: int = 1, **attributes: Any) -> None:
        """Increment a counter.

        Args:
            name: Counter name
            amount: Amount to increment by
            **attributes: Optional attributes
        """
        if name in self._counters:
            self._counters[name].add(amount, attributes)

    def record_histogram(self, name: str, value: float, **attributes: Any) -> None:
        """Record a histogram value.

        Args:
            name: Histogram name
            value: Value to record
            **attributes: Optional attributes
        """
        if name in self._histograms:
            self._histograms[name].record(value, attributes)

    def set_gauge(self, name: str, value: float, **attributes: Any) -> None:
        """Set a gauge value.

        Args:
            name: Gauge name
            value: Value to set
            **attributes: Optional attributes
        """
        # For observable gauges, we use callbacks
        # This is a simplified implementation
        if name in self._gauges:
            # Note: Full gauge implementation requires callback registration
            pass


# Standard metrics instance
otel_metrics_collector: OTelMetricsCollector | None = None

if OTTEL_METRICS_AVAILABLE:
    otel_metrics_collector = OTelMetricsCollector()


__all__ = [
    "MetricsCollector",  # Lazily imported via __getattr__
    "OTelMetricsCollector",
    "is_metrics_enabled",
    "metrics",  # Lazily imported via __getattr__
    "otel_metrics_collector",
    "setup_metrics",
]


# Backward compatibility: lazy import to avoid circular dependency
def __getattr__(name: str):
    """Lazy import for backward compatibility."""
    if name in ("MetricsCollector", "metrics"):
        from secondbrain.utils.observability import (  # noqa: I001
            MetricsCollector as _MC,  # noqa: N814
            metrics as _m,
        )

        return _MC if name == "MetricsCollector" else _m
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# No-op implementations for when OTel is unavailable
class _NoOpCounter:
    """No-op counter when OTel unavailable."""

    def add(self, amount: int, attributes: dict[str, Any] | None = None) -> None:
        """No-op add."""
        pass


class _NoOpHistogram:
    """No-op histogram when OTel unavailable."""

    def record(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        """No-op record."""
        pass


class _NoOpGauge:
    """No-op gauge when OTel unavailable."""

    def set(self, value: float, attributes: dict[str, Any] | None = None) -> None:
        """No-op set."""
        pass
