import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import TypedDict

from rich.console import Console
from rich.logging import RichHandler

from secondbrain.types import ChunkInfo, SearchResult

__all__ = [
    "HealthStatus",
    "get_health_status",
    "get_logger",
    "get_request_id",
    "set_request_id",
    "setup_json_logging",
    "setup_logging",
    "setup_rich_logging",
]


class HealthStatus(TypedDict):
    """Typed dictionary for health status response."""

    status: str
    timestamp: str
    uptime: float | None
    services: dict[str, bool]
    check_duration_seconds: float


_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Get the current request ID from context.

    Returns:
        Current request ID string.
    """
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set or generate a request ID for the current context.

    Args:
        request_id: Request ID string. If None, generates a new UUID.

    Returns:
        The request ID string that was set.
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    _request_id.set(request_id)
    return request_id


def setup_logging(verbose: bool = False, json_format: bool = False) -> None:
    """Configure logging with the specified options.

    Args:
        verbose: Enable DEBUG level if True, INFO otherwise.
        json_format: Use JSON format if True, rich text otherwise.
    """
    level = logging.DEBUG if verbose else logging.INFO

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


def setup_json_logging(level: int) -> None:
    """Configure JSON structured logging.

    Args:
        level: Logging level constant (e.g., logging.INFO).
    """

    class JSONFormatter(logging.Formatter):
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
            }
            return json.dumps(log_entry)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True)],
    )

    if logging.root.handlers:
        logging.root.handlers[0].setFormatter(JSONFormatter())


def check_services() -> dict[str, bool]:
    """Check availability of required services.

    Returns:
        Dictionary with service names as keys and boolean availability status.
    """
    from secondbrain.embedding import EmbeddingGenerator
    from secondbrain.storage import VectorStorage

    embedding_gen = EmbeddingGenerator()
    storage = VectorStorage()

    return {
        "ollama": embedding_gen.validate_connection(),
        "mongodb": storage.validate_connection(),
    }


def get_health_status() -> HealthStatus:
    """Get health status of all services.

    Returns:
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

    Returns:
        Configured Logger instance.
    """
    return logging.getLogger(name)
