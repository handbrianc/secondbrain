import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str | None = None) -> str:
    if request_id is None:
        request_id = str(uuid.uuid4())
    _request_id.set(request_id)
    return request_id


def setup_logging(verbose: bool = False, json_format: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO

    if json_format:
        setup_json_logging(level)
    else:
        setup_rich_logging(level)


def setup_rich_logging(level: int) -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=Console(stderr=True), rich_tracebacks=True)],
    )


def setup_json_logging(level: int) -> None:
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


def get_health_status() -> dict[str, Any]:
    """Get health status of all services.

    Returns:
        Health status dictionary.
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
    return logging.getLogger(name)
