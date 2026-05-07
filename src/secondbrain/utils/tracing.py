"""OpenTelemetry tracing utilities for distributed tracing.

This module provides tracing setup and helpers for instrumenting
the secondbrain application with OpenTelemetry distributed tracing.

Note: OpenTelemetry is an optional dependency. If not installed, tracing will
be disabled and all tracing functions will be no-ops.

Usage:
    # Enable tracing via environment variable
    export SECONDBRAIN_TRACING_ENABLED=true

    # Setup tracing (call once at application startup)
    from secondbrain.utils.tracing import setup_tracing, get_tracer

    setup_tracing(service_name="secondbrain", service_version="0.1.0")
    tracer = get_tracer()

    # Use tracer to create spans
    with tracer.start_as_current_span("operation_name") as span:
        span.set_attribute("key", "value")
        # ... operation ...
"""

from __future__ import annotations

import contextvars
import logging
import os
import re
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# Check if OpenTelemetry is available
try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource as OTelResource  # noqa: F401
    from opentelemetry.sdk.trace import (
        TracerProvider as OTelTracerProvider,  # noqa: F401
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter,  # noqa: F401
    )
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,  # noqa: F401
        ConsoleSpanExporter,  # noqa: F401
    )

    try:
        from opentelemetry.instrumentation.pymongo import PymongoInstrumentor

        PYMONGO_INSTRUMENTOR_AVAILABLE = True
    except ImportError:
        PYMONGO_INSTRUMENTOR_AVAILABLE = False

    OTTEL_AVAILABLE = True
except ImportError:
    OTTEL_AVAILABLE = False
    otel_metrics = None
    otel_trace = None
    otel_trace = None

# Global tracer and state
_tracer: Any = None
_tracing_enabled: bool = False

# Global meter and metrics
_meter: Any = None
_metrics_enabled: bool = False

_pymongo_instrumentor: Any = None

# Metrics counters
_operations_counter: Any = None
_duration_histogram: Any = None
_errors_counter: Any = None

# Trace context propagation
# W3C traceparent format: 00-trace_id-span_id-flags
# trace_id: 32 hex chars (128-bit)
# span_id: 16 hex chars (64-bit)
# flags: 2 hex chars (01 = sampled)
_TRACEPARENT_PATTERN = re.compile(r"^00-([a-f0-9]{32})-([a-f0-9]{16})-([a-f0-9]{2})$")

# Context var for trace context storage
_trace_context_var: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("trace_context", default=None)
)


def extract_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Extract W3C trace context from HTTP headers.

    Parses the traceparent header (and optionally tracestate) to extract
    trace ID and span ID for distributed tracing.

    Args:
        headers: Dictionary of HTTP headers (case-insensitive).

    Returns
    -------
        Dictionary with 'trace_id', 'span_id', and 'flags' keys if valid
        traceparent found, otherwise empty dict.

    Example:
        headers = {"traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"}
        context = extract_trace_context(headers)
        # {'trace_id': '4bf92f3577b34da6a3ce929d0e0e4736',
        #  'span_id': '00f067aa0ba902b7', 'flags': '01'}
    """
    # Normalize header keys to lowercase
    normalized_headers = {k.lower(): v for k, v in headers.items()}

    traceparent = normalized_headers.get("traceparent", "")

    if not traceparent:
        return {}

    match = _TRACEPARENT_PATTERN.match(traceparent.strip())
    if not match:
        logger.debug("Invalid traceparent format: %s", traceparent)
        return {}

    trace_id, span_id, flags = match.groups()

    # Validate trace_id and span_id are not all zeros
    if trace_id == "0" * 32 or span_id == "0" * 16:
        logger.debug("Invalid trace_id or span_id (all zeros)")
        return {}

    return {"trace_id": trace_id, "span_id": span_id, "flags": flags}


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """Inject W3C trace context into HTTP headers.

    Adds traceparent (and optionally tracestate) headers to propagate
    trace context across service boundaries.

    Args:
        headers: Dictionary of HTTP headers to add trace context to.

    Returns
    -------
        Updated headers dictionary with traceparent injected.

    Example:
        headers = {}
        headers = inject_trace_context(headers)
        # headers now contains traceparent header
    """
    result = headers.copy()

    # Get current trace context if available
    current_context = get_current_trace_context()

    if current_context:
        trace_id = current_context.get("trace_id")
        span_id = current_context.get("span_id")
        flags = current_context.get("flags", "01")
    else:
        # Generate new trace context if none exists
        trace_id = uuid.uuid4().hex.zfill(32)
        span_id = uuid.uuid4().hex[:16]
        flags = "01"  # Sampled

    # Format traceparent: version-trace_id-span_id-flags
    traceparent = f"00-{trace_id}-{span_id}-{flags}"
    result["traceparent"] = traceparent

    # Add tracestate if available
    if current_context and "tracestate" in current_context:
        result["tracestate"] = current_context["tracestate"]

    return result


def get_current_trace_context() -> dict[str, str] | None:
    """Get the current trace context from async context.

    Returns the trace ID, span ID, and flags from the current async context.

    Returns
    -------
        Dictionary with 'trace_id', 'span_id', 'flags' (and optionally 'tracestate')
        if trace context is set, None otherwise.

    Example:
        context = get_current_trace_context()
        if context:
            print(f"Current trace: {context['trace_id']}")
    """
    return _trace_context_var.get()


@contextmanager
def set_trace_context(
    trace_id: str, span_id: str, flags: str = "01", tracestate: str | None = None
) -> Generator[None, None, None]:
    """Set trace context for the current async context.

    Context manager that sets trace context for the duration of the context,
    then restores the previous context on exit.

    Args:
        trace_id: 32-character hex trace ID.
        span_id: 16-character hex span ID.
        flags: Trace flags (e.g., "01" for sampled).
        tracestate: Optional tracestate header value.

    Yields
    ------
        None

    Example:
        with set_trace_context(trace_id, span_id):
            # Trace context is active here
            pass
    """
    # Validate inputs
    if len(trace_id) != 32 or not all(
        c in "0123456789abcdef" for c in trace_id.lower()
    ):
        raise ValueError("Invalid trace_id: must be 32 hex characters")
    if len(span_id) != 16 or not all(c in "0123456789abcdef" for c in span_id.lower()):
        raise ValueError("Invalid span_id: must be 16 hex characters")
    if len(flags) != 2 or not all(c in "0123456789abcdef" for c in flags.lower()):
        raise ValueError("Invalid flags: must be 2 hex characters")

    context = {
        "trace_id": trace_id.lower(),
        "span_id": span_id.lower(),
        "flags": flags.lower(),
    }
    if tracestate:
        context["tracestate"] = tracestate

    token = _trace_context_var.set(context)
    try:
        yield
    finally:
        _trace_context_var.reset(token)


def is_tracing_enabled() -> bool:
    """Check if tracing is enabled via environment variable.

    Returns
    -------
        True if SECONDBRAIN_TRACING_ENABLED is set to "true" (case-insensitive).
    """
    global _tracing_enabled
    if not _tracing_enabled:
        _tracing_enabled = os.getenv("SECONDBRAIN_TRACING_ENABLED", "false").lower() == "true"
    return _tracing_enabled


def is_metrics_enabled() -> bool:
    """Check if metrics is enabled via environment variable.

    Returns
    -------
        True if OTEL_METRICS_ENABLED is set to "true" (case-insensitive).
    """
    global _metrics_enabled
    if not _metrics_enabled:
        _metrics_enabled = os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true"
    return _metrics_enabled


def setup_tracing(
    service_name: str = "secondbrain",
    service_version: str = "0.1.0",
    environment: str = "development",
) -> None:
    """Set up OpenTelemetry tracing and metrics.

    Must be called once at application startup before any tracing occurs.

    Args:
        service_name: Name of the service for tracing.
        service_version: Version of the service.
        environment: Deployment environment (development, staging, production).

    Returns
    -------
        None

    Note:
        If OpenTelemetry is not installed, this function is a no-op.
    """
    global _tracer, _tracing_enabled, _meter, _metrics_enabled
    global _operations_counter, _duration_histogram, _errors_counter

    if not OTTEL_AVAILABLE:
        logger.warning("OpenTelemetry not installed, tracing disabled")
        return

    if not is_tracing_enabled():
        logger.debug("Tracing not enabled (SECONDBRAIN_TRACING_ENABLED not set)")
        return

    try:
        from opentelemetry.sdk.resources import Resource as OTelResource
        from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        otlp_endpoint = os.getenv(
            "SECONDBRAIN_OTEL_EXPORTER_ENDPOINT", "http://localhost:4317"
        )
        sampling_rate_str = os.getenv("SECONDBRAIN_OTEL_SAMPLING_RATE", "1.0")
        try:
            sampling_rate = float(sampling_rate_str)
            sampling_rate = max(0.0, min(1.0, sampling_rate))
        except ValueError:
            logger.warning(
                "Invalid SECONDBRAIN_OTEL_SAMPLING_RATE: %s, using default 1.0",
                sampling_rate_str,
            )
            sampling_rate = 1.0

        sampler = TraceIdRatioBased(sampling_rate)

        resource = OTelResource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
            }
        )

        tracer_provider = OTelTracerProvider(resource=resource, sampler=sampler)

        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(
                "OpenTelemetry OTLP exporter configured for endpoint: %s",
                otlp_endpoint,
            )
        except Exception as e:
            logger.warning(
                "Failed to configure OTLP exporter (%s), falling back to console exporter: %s",
                e,
                otlp_endpoint,
            )
            tracer_provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )

        # Set as global tracer provider
        if otel_trace is not None:
            otel_trace.set_tracer_provider(tracer_provider)

            # Get tracer
            _tracer = otel_trace.get_tracer(service_name, service_version)

        # Setup metrics if enabled
        if otel_metrics is not None and is_metrics_enabled():
            metric_reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
            meter_provider = MeterProvider(
                resource=resource, metric_readers=[metric_reader]
            )
            otel_metrics.set_meter_provider(meter_provider)

            # Get meter and create metrics
            _meter = otel_metrics.get_meter(service_name, service_version)
            _metrics_enabled = True

            # Create metrics
            _operations_counter = _meter.create_counter(
                name="secondbrain.operations.count",
                description="Count of operations",
                unit="1",
            )
            _duration_histogram = _meter.create_histogram(
                name="secondbrain.operations.duration",
                description="Operation duration",
                unit="ms",
            )
            _errors_counter = _meter.create_counter(
                name="secondbrain.errors.count",
                description="Count of errors",
                unit="1",
            )

        logger.info(
            "OpenTelemetry tracing and metrics enabled for %s v%s",
            service_name,
            service_version,
        )

        if PYMONGO_INSTRUMENTOR_AVAILABLE:
            try:
                global _pymongo_instrumentor
                _pymongo_instrumentor = PymongoInstrumentor()
                _pymongo_instrumentor.instrument()
                logger.info("Pymongo auto-instrumentation enabled")
            except Exception as e:
                logger.warning("Failed to setup Pymongo instrumentation: %s", e)

    except ImportError as e:
        logger.warning(
            "OpenTelemetry Pymongo instrumentation not available: %s. "
            "Install with: pip install opentelemetry-instrumentation-pymongo",
            e,
        )
    except Exception as e:
        logger.warning("Failed to setup OpenTelemetry: %s", e)


def get_tracer() -> Any:
    """Get the global tracer instance.

    Returns
    -------
        Tracer instance if tracing is enabled and initialized,
        otherwise a mock tracer that does nothing.

    Note:
        Returns a no-op tracer if OpenTelemetry is not available or not initialized.
    """
    global _tracer

    if not OTTEL_AVAILABLE:
        return _NoOpTracer()

    if _tracer is None and is_tracing_enabled():
        setup_tracing()

    if _tracer is None:
        return _NoOpTracer()

    return _tracer


def get_meter() -> Any:
    """Get the global meter instance.

    Returns
    -------
        Meter instance if metrics is enabled and initialized,
        otherwise a mock meter that does nothing.
    """
    global _meter

    if not OTTEL_AVAILABLE or not otel_metrics:
        return _NoOpMeter()

    if _meter is None and is_metrics_enabled():
        # Metrics will be set up when tracing is set up
        pass

    if _meter is None:
        return _NoOpMeter()

    return _meter


def record_operation(
    operation_name: str, duration_ms: float, success: bool = True
) -> None:
    """Record an operation with metrics.

    Args:
        operation_name: Name of the operation.
        duration_ms: Duration in milliseconds.
        success: Whether the operation was successful.
    """
    if not _metrics_enabled or not _meter:
        return

    try:
        # Record operation count
        if _operations_counter:
            _operations_counter.add(1, {"operation": operation_name})

        # Record duration
        if _duration_histogram:
            _duration_histogram.record(duration_ms, {"operation": operation_name})

        # Record errors if failed
        if not success and _errors_counter:
            _errors_counter.add(
                1, {"operation": operation_name, "error_type": "failure"}
            )
    except Exception:
        pass  # Don't let metrics errors affect the operation


@contextmanager
def trace_operation(operation_name: str) -> Generator[Any, None, None]:
    """Context manager for tracing an operation.

    Args:
        operation_name: Name of the operation to trace.

    Yields
    ------
        Span object if tracing is enabled, None otherwise.

    Example:
        with trace_operation("process_document"):
            # ... operation ...
            pass
    """
    if not OTTEL_AVAILABLE or not is_tracing_enabled():
        yield None
        return

    import time

    tracer = get_tracer()
    start_time = time.monotonic()
    success = True
    try:
        with tracer.start_as_current_span(operation_name) as span:
            yield span
    except Exception as e:
        success = False
        # Record exception on the original span
        if OTTEL_AVAILABLE:
            span.record_exception(e)
            span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR), str(e))
        raise
    finally:
        # Record metrics
        duration_ms = (time.monotonic() - start_time) * 1000
        record_operation(operation_name, duration_ms, success)


def trace_decorator(
    operation_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Trace a function with OpenTelemetry spans.

    Args:
        operation_name: Name of the operation to trace.

    Returns
    -------
        Decorated function with tracing.

    Example:
        @trace_decorator("save_document")
        def save_document(doc):
            # ... save logic ...
            pass
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not OTTEL_AVAILABLE or not is_tracing_enabled():
                return func(*args, **kwargs)

            with trace_operation(operation_name) as span:
                if span:
                    span.set_attribute("function.name", func.__name__)
                return func(*args, **kwargs)

        return wrapper

    return decorator


class _NoOpTracer:
    """No-op tracer when OpenTelemetry is not available."""

    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Start a no-op span."""
        return _NoOpSpan()

    def __getattr__(self, name: str) -> Any:
        """Return no-op methods for any attribute access."""
        return lambda *args, **kwargs: None


def shutdown_tracing() -> None:
    """Shut down OpenTelemetry tracing and release resources.

    Should be called at application shutdown to ensure all spans are flushed.

    Note:
        If OpenTelemetry is not available or not initialized, this function is a no-op.
    """
    global _tracer, _tracing_enabled

    if not OTTEL_AVAILABLE:
        return

    if _tracer is not None:
        if otel_trace is None:
            return
        try:
            # Shutdown the tracer provider to flush all spans
            from opentelemetry.sdk.trace import TracerProvider

            provider = otel_trace.get_tracer_provider()
            if isinstance(provider, TracerProvider):
                provider.shutdown()
                logger.info("OpenTelemetry tracing shutdown")
        except Exception as e:
            logger.warning("Error during OpenTelemetry shutdown: %s", e)

    _tracer = None
    _tracing_enabled = False


class _NoOpSpan:
    """No-op span when OpenTelemetry is not available."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op attribute setting."""
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        """No-op status setting."""
        pass

    def record_exception(self, exception: Exception) -> None:
        """No-op exception recording."""
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op event adding."""
        pass


class _NoOpMeter:
    """No-op meter when OpenTelemetry metrics is not available."""

    def create_counter(self, *args: Any, **kwargs: Any) -> Any:
        """No-op counter creation."""
        return _NoOpCounter()

    def create_histogram(self, *args: Any, **kwargs: Any) -> Any:
        """No-op histogram creation."""
        return _NoOpHistogram()

    def __getattr__(self, name: str) -> Any:
        """Return no-op methods for any attribute access."""
        return lambda *args, **kwargs: None


class _NoOpCounter:
    """No-op counter."""

    def add(self, *args: Any, **kwargs: Any) -> None:
        """No-op add."""
        pass


class _NoOpHistogram:
    """No-op histogram."""

    def record(self, *args: Any, **kwargs: Any) -> None:
        """No-op record."""
        pass
