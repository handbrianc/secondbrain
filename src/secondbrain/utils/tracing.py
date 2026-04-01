"""OpenTelemetry tracing utilities for distributed tracing.

This module provides tracing setup and helpers for instrumenting
the secondbrain application with OpenTelemetry distributed tracing.

Features:
- OTLP exporter configuration for production deployment
- Async context propagation for httpx/aiohttp
- Correlation ID to trace context linking
- Predefined span hierarchy for operations

Usage:
    # Enable tracing via environment variable
    export OTEL_TRACING_ENABLED=true

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

import logging
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "SPAN_HIERARCHY",
    "async_trace_decorator",
    "get_span_name",
    "get_trace_context",
    "get_tracer",
    "is_tracing_enabled",
    "set_trace_context",
    "setup_otlp_exporter",
    "setup_tracing",
    "shutdown_tracing",
    "trace_decorator",
    "trace_operation",
]

# Check if OpenTelemetry is available
try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource as OTelResource  # noqa: F401
    from opentelemetry.sdk.trace import (
        TracerProvider as OTelTracerProvider,  # noqa: F401
    )
    from opentelemetry.sdk.trace.export import (  # noqa: F401
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )

    OTTEL_AVAILABLE = True
except ImportError:
    OTTEL_AVAILABLE = False
    otel_trace = None

# Global tracer and state
_tracer: Any = None
_tracing_enabled: bool = False

# Async context for trace propagation
_trace_context_var: ContextVar[dict[str, Any] | None] = ContextVar(
    "trace_context", default=None
)

# Span hierarchy definitions
SPAN_HIERARCHY = {
    "ingest": {
        "document.parse": "ingest.document.parse",
        "document.embed": "ingest.document.embed",
        "document.store": "ingest.document.store",
    },
    "search": {
        "query.retrieval": "search.query.retrieval",
        "query.rerank": "search.query.rerank",
    },
    "rag": {
        "pipeline.retrieve": "rag.pipeline.retrieve",
        "pipeline.generate": "rag.pipeline.generate",
    },
}


def is_tracing_enabled() -> bool:
    """Check if tracing is enabled via environment variable.

    Returns
    -------
        True if OTEL_TRACING_ENABLED is set to "true" (case-insensitive).
    """
    global _tracing_enabled
    if not _tracing_enabled:
        _tracing_enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() == "true"
    return _tracing_enabled


def setup_otlp_exporter(
    endpoint: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> Any:
    """Configure OTLP exporter for production deployment.

    Args:
        endpoint: OTLP collector endpoint. If None, reads from env var.
        headers: Optional headers for OTLP requests.
        timeout: Export timeout in seconds.

    Returns:
        OTLPSpanExporter if configured successfully, None otherwise.
    """
    if not OTTEL_AVAILABLE:
        return None

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
        headers_str = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
        headers = headers or {
            item.split("=")[0]: item.split("=")[1]
            for item in headers_str.split(",")
            if "=" in item
        }
        timeout = int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", timeout))

        return OTLPSpanExporter(endpoint=endpoint, headers=headers, timeout=timeout)

    except Exception as e:
        logger.warning("Failed to configure OTLP exporter: %s", e)
        return None


def setup_tracing(
    service_name: str = "secondbrain",
    service_version: str = "0.1.0",
    environment: str = "development",
) -> None:
    """Set up OpenTelemetry tracing.

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
    global _tracer, _tracing_enabled

    if not OTTEL_AVAILABLE:
        logger.warning("OpenTelemetry not installed, tracing disabled")
        return

    if not is_tracing_enabled():
        logger.debug("Tracing not enabled (OTEL_TRACING_ENABLED not set)")
        return

    try:
        # Create resource with service metadata
        from opentelemetry.sdk.resources import Resource as OTelResource
        from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        resource = OTelResource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment,
            }
        )

        # Create tracer provider
        tracer_provider = OTelTracerProvider(resource=resource)

        # Add console exporter for development
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        # Set as global tracer provider
        if otel_trace is not None:
            otel_trace.set_tracer_provider(tracer_provider)

            # Get tracer
            _tracer = otel_trace.get_tracer(service_name, service_version)

        logger.info(
            "OpenTelemetry tracing enabled for %s v%s", service_name, service_version
        )

    except Exception as e:
        logger.warning("Failed to setup OpenTelemetry tracing: %s", e)


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

    tracer = get_tracer()
    with tracer.start_as_current_span(operation_name) as span:
        yield span


async_trace_operation = trace_operation


def get_trace_context() -> dict[str, Any] | None:
    """Get current trace context for async propagation.

    Returns:
        Trace context dictionary with trace_id, span_id, and correlation_id.
    """
    return _trace_context_var.get()


def set_trace_context(
    trace_id: str | None = None,
    span_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Set trace context for current async context.

    Args:
        trace_id: OpenTelemetry trace ID
        span_id: OpenTelemetry span ID
        correlation_id: Correlation ID for log tracing

    Returns:
        Trace context dictionary
    """
    context = {
        "trace_id": trace_id or "unknown",
        "span_id": span_id or "unknown",
        "correlation_id": correlation_id or "unknown",
    }
    _trace_context_var.set(context)
    return context


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


def async_trace_decorator(
    operation_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Trace an async function with OpenTelemetry spans.

    Args:
        operation_name: Name of the operation to trace.

    Returns
    -------
        Decorated async function with tracing.

    Example:
        @async_trace_decorator("process_async")
        async def process_async(data):
            # ... async logic ...
            pass
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not OTTEL_AVAILABLE or not is_tracing_enabled():
                return await func(*args, **kwargs)

            with async_trace_operation(operation_name) as span:
                if span:
                    span.set_attribute("function.name", func.__name__)
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_span_name(category: str, action: str) -> str:
    """Get standardized span name from category and action.

    Args:
        category: Span category (e.g., 'ingest', 'search', 'rag')
        action: Action within category (e.g., 'document.parse', 'query.retrieval')

    Returns:
        Standardized span name following hierarchy convention.

    Example:
        >>> get_span_name("ingest", "document.parse")
        "ingest.document.parse"
    """
    hierarchy = SPAN_HIERARCHY.get(category, {})
    return hierarchy.get(action, f"{category}.{action}")


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
