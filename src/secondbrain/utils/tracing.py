"""OpenTelemetry tracing utilities."""
# mypy: disable-error-code=attr-defined

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

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry import trace as otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

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

_tracer: Any = None
_tracing_enabled: bool = False
_meter: Any = None
_metrics_enabled: bool = False
_pymongo_instrumentor: Any = None
_operations_counter: Any = None
_duration_histogram: Any = None
_errors_counter: Any = None

_TRACEPARENT_PATTERN = re.compile(r"^00-([a-f0-9]{32})-([a-f0-9]{16})-([a-f0-9]{2})$")
_trace_context_var: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar("trace_context", default=None)
)


def extract_trace_context(headers: dict[str, str]) -> dict[str, str]:
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    traceparent = normalized_headers.get("traceparent", "")

    if not traceparent:
        return {}

    match = _TRACEPARENT_PATTERN.match(traceparent.strip())
    if not match:
        logger.debug("Invalid traceparent format: %s", traceparent)
        return {}

    trace_id, span_id, flags = match.groups()

    if trace_id == "0" * 32 or span_id == "0" * 16:
        logger.debug("Invalid trace_id or span_id (all zeros)")
        return {}

    return {"trace_id": trace_id, "span_id": span_id, "flags": flags}


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    result = headers.copy()
    current_context = get_current_trace_context()

    if current_context:
        trace_id = current_context.get("trace_id")
        span_id = current_context.get("span_id")
        flags = current_context.get("flags", "01")
    else:
        trace_id = uuid.uuid4().hex.zfill(32)
        span_id = uuid.uuid4().hex[:16]
        flags = "01"

    result["traceparent"] = f"00-{trace_id}-{span_id}-{flags}"

    if current_context and "tracestate" in current_context:
        result["tracestate"] = current_context["tracestate"]

    return result


def get_current_trace_context() -> dict[str, str] | None:
    return _trace_context_var.get()


@contextmanager
def set_trace_context(
    trace_id: str, span_id: str, flags: str = "01", tracestate: str | None = None
) -> Generator[None, None, None]:
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
    global _tracing_enabled
    if not _tracing_enabled:
        _tracing_enabled = (
            os.getenv("SECONDBRAIN_TRACING_ENABLED", "false").lower() == "true"
        )
    return _tracing_enabled


def is_metrics_enabled() -> bool:
    global _metrics_enabled
    if not _metrics_enabled:
        _metrics_enabled = os.getenv("OTEL_METRICS_ENABLED", "true").lower() == "true"
    return _metrics_enabled


def setup_tracing(
    service_name: str = "secondbrain",
    service_version: str = "0.1.0",
    environment: str = "development",
) -> None:
    global _tracer, _tracing_enabled, _meter, _metrics_enabled
    global _operations_counter, _duration_histogram, _errors_counter

    # Validate sampling rate BEFORE checking OTel availability
    # This ensures validation happens regardless of whether OTel is installed
    sampling_rate_str = os.getenv("SECONDBRAIN_OTEL_SAMPLING_RATE", "1.0")
    try:
        sampling_rate = max(0.0, min(1.0, float(sampling_rate_str)))
    except ValueError:
        logger.warning(
            "Invalid SECONDBRAIN_OTEL_SAMPLING_RATE: %s, using default 1.0",
            sampling_rate_str,
        )
        sampling_rate = 1.0

    if not OTTEL_AVAILABLE:
        logger.warning("OpenTelemetry not installed, tracing disabled")
        return

    if not is_tracing_enabled():
        logger.debug("Tracing not enabled (SECONDBRAIN_TRACING_ENABLED not set)")
        return

    try:
        from opentelemetry.sdk.resources import Resource as OTelResource
        from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        otlp_endpoint = os.getenv(
            "SECONDBRAIN_OTEL_EXPORTER_ENDPOINT", "http://localhost:4317"
        )

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
                "OpenTelemetry OTLP exporter configured for endpoint: %s", otlp_endpoint
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

        if otel_trace is not None:
            otel_trace.set_tracer_provider(tracer_provider)
            _tracer = otel_trace.get_tracer(service_name, service_version)

        if is_metrics_enabled():
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                ConsoleMetricExporter,
                PeriodicExportingMetricReader,
            )

            reader = PeriodicExportingMetricReader(ConsoleMetricExporter())
            meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
            otel_metrics.set_meter_provider(meter_provider)
            _meter = otel_metrics.get_meter(service_name, service_version)

            _operations_counter = _meter.create_counter("secondbrain_operations")
            _duration_histogram = _meter.create_histogram(
                "secondbrain_operation_duration_ms"
            )
            _errors_counter = _meter.create_counter("secondbrain_errors")

            _metrics_enabled = True
            logger.info(
                "OpenTelemetry metrics enabled for %s v%s",
                service_name,
                service_version,
            )

        _tracing_enabled = True
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
            "OpenTelemetry Pymongo instrumentation not available: %s. Install with: pip install opentelemetry-instrumentation-pymongo",
            e,
        )
    except Exception as e:
        logger.warning("Failed to setup OpenTelemetry: %s", e)


def get_tracer() -> Any:
    global _tracer

    if not OTTEL_AVAILABLE:
        return _NoOpTracer()

    if _tracer is None and is_tracing_enabled():
        setup_tracing()

    if _tracer is None:
        return _NoOpTracer()

    return _tracer


def get_meter() -> Any:
    global _meter

    if not OTTEL_AVAILABLE or not otel_metrics:
        return _NoOpMeter()

    if _meter is None and is_metrics_enabled():
        pass

    if _meter is None:
        return _NoOpMeter()

    return _meter


def record_operation(
    operation_name: str, duration_ms: float, success: bool = True
) -> None:
    if not _metrics_enabled or not _meter:
        return

    try:
        if _operations_counter:
            _operations_counter.add(1, {"operation": operation_name})
        if _duration_histogram:
            _duration_histogram.record(duration_ms, {"operation": operation_name})
        if not success and _errors_counter:
            _errors_counter.add(
                1, {"operation": operation_name, "error_type": "failure"}
            )
    except Exception:
        pass


@contextmanager
def trace_operation(operation_name: str) -> Generator[Any, None, None]:
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
        if OTTEL_AVAILABLE:
            span.record_exception(e)
            span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR), str(e))
        raise
    finally:
        duration_ms = (time.monotonic() - start_time) * 1000
        record_operation(operation_name, duration_ms, success)


def trace_decorator(
    operation_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
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
    def start_as_current_span(self, name: str, *args: Any, **kwargs: Any) -> Any:
        return _NoOpSpan()

    def __getattr__(self, name: str) -> Any:
        return lambda *args, **kwargs: None


def shutdown_tracing() -> None:
    global _tracer, _tracing_enabled

    if not OTTEL_AVAILABLE:
        return

    if _tracer is not None:
        if otel_trace is None:
            return
        try:
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
        pass

    def set_status(self, status: Any, description: str | None = None) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        pass


class _NoOpMeter:
    def create_counter(self, *args: Any, **kwargs: Any) -> Any:
        return _NoOpCounter()

    def create_histogram(self, *args: Any, **kwargs: Any) -> Any:
        return _NoOpHistogram()

    def __getattr__(self, name: str) -> Any:
        return lambda *args, **kwargs: None


class _NoOpCounter:
    def add(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoOpHistogram:
    def record(self, *args: Any, **kwargs: Any) -> None:
        pass
