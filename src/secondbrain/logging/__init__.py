"""Unified logging API for SecondBrain application.

This module provides a consolidated logging interface with:
- Structured JSON logging with correlation IDs
- Rich text logging for development
- Request ID management via contextvars
- Health status checking
- Trace ID integration for OpenTelemetry correlation
"""

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from typing import Any, TypedDict

from rich.console import Console
from rich.logging import RichHandler

from secondbrain.types import ChunkInfo, SearchResult

__all__ = [
    "CorrelationIdFilter",
    "HealthStatus",
    "JSONFormatter",
    "get_health_status",
    "get_logger",
    "get_request_id",
    "get_trace_context",
    "set_request_id",
    "set_trace_context",
    "setup_json_logging",
    "setup_logging",
    "setup_rich_logging",
    "setup_structured_logging",
]


class HealthStatus(TypedDict):
    """Typed dictionary for health status response."""

    status: str
    timestamp: str
    uptime: float | None
    services: dict[str, bool]
    check_duration_seconds: float


_request_id: ContextVar[str] = ContextVar("request_id", default="")
_trace_context: ContextVar[dict[str, str] | None] = ContextVar(
    "trace_context", default=None
)


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to log records for request tracing."""

    def __init__(self, name: str = ""):
        super().__init__(name)
        self.correlation_id = os.getenv("CORRELATION_ID", str(uuid.uuid4()))

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record."""
        record.correlation_id = self.correlation_id

        # Add trace context if available
        trace_ctx = _trace_context.get()
        if trace_ctx:
            record.trace_id = trace_ctx.get("trace_id", "unknown")
            record.span_id = trace_ctx.get("span_id", "unknown")

        return True


def set_trace_context(
    trace_id: str | None = None, span_id: str | None = None
) -> dict[str, str]:
    """Set trace context for current async context.

    Args:
        trace_id: OpenTelemetry trace ID
        span_id: OpenTelemetry span ID

    Returns:
        Trace context dictionary
    """
    context = {
        "trace_id": trace_id or "unknown",
        "span_id": span_id or "unknown",
    }
    _trace_context.set(context)
    return context


def get_trace_context() -> dict[str, str] | None:
    """Get current trace context.

    Returns:
        Trace context dictionary or None if not set
    """
    return _trace_context.get()


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns
    -------
        Current request ID string.
    """
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set or generate a request ID for the current context.

    Args:
        request_id: Request ID string. If None, generates a new UUID.

    Returns
    -------
        The request ID string that was set.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    _request_id.set(request_id)
    return request_id


def setup_logging(verbose: bool = False, json_format: bool = False) -> None:
    """Configure logging with the specified options.

    Args:
        verbose: Enable DEBUG level if True, WARNING (no logs) otherwise.
        json_format: Use JSON format if True, rich text otherwise.
    """
    level = logging.DEBUG if verbose else logging.WARNING

    # If handlers are already configured, just update the level
    if logging.root.handlers:
        for handler in logging.root.handlers:
            handler.setLevel(level)
        logging.root.setLevel(level)
        return

    if json_format:
        setup_json_logging(level)
    else:
        setup_rich_logging(level)


def setup_rich_logging(level: int) -> None:
    """Configure rich console logging.

    Args:
        level: Logging level constant (e.g., logging.INFO).
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True)],
    )


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "request_id": get_request_id() or "",
            "correlation_id": getattr(record, "correlation_id", "unknown"),
        }

        # Add trace context if available
        trace_ctx = get_trace_context()
        if trace_ctx:
            log_entry["trace_id"] = trace_ctx.get("trace_id", "unknown")
            log_entry["span_id"] = trace_ctx.get("span_id", "unknown")

        # Add exception info if present
        if record.exc_info:
            import traceback

            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": "".join(traceback.format_exception(*record.exc_info))
                if record.exc_info
                else None,
            }

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        return json.dumps(log_entry)


def setup_json_logging(level: int) -> None:
    """Configure JSON structured logging.

    Args:
        level: Logging level constant (e.g., logging.INFO).
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True)],
    )

    if logging.root.handlers:
        logging.root.handlers[0].setFormatter(JSONFormatter())


def setup_structured_logging() -> None:
    """Configure structured logging based on settings.

    Sets up either JSON or text logging format with correlation IDs.
    """
    from secondbrain.config.validator import get_settings

    settings = get_settings()
    log_level = getattr(logging, settings.log_level)
    log_format = settings.log_format

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    # Add correlation ID filter
    correlation_filter = CorrelationIdFilter()
    handler.addFilter(correlation_filter)

    # Set formatter based on settings
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "[%(correlation_id)s] %(asctime)s %(levelname)s "
                "[%(name)s:%(lineno)d] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger.addHandler(handler)


def check_services() -> dict[str, bool]:
    """Check availability of required services.

    Returns
    -------
        Dictionary with service names as keys and boolean availability status.
    """
    from secondbrain.storage import VectorStorage

    storage = VectorStorage()

    return {
        "mongodb": storage.validate_connection(),
    }


def get_health_status() -> HealthStatus:
    """Get health status of all services.

    Returns
    -------
        HealthStatus dictionary with status, timestamp, services, and check timing.
    """
    check_start = time.time()

    services = check_services()
    total_time = time.time() - check_start

    status = "healthy" if all(services.values()) else "degraded"

    return {
        "status": status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "uptime": None,
        "services": services,
        "check_duration_seconds": total_time,
    }


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance by name.

    Args:
        name: Logger name.

    Returns
    -------
        Configured Logger instance.
    """
    return logging.getLogger(name)
