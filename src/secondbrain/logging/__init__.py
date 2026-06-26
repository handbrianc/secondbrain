"""Logging utilities for SecondBrain application."""

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TypedDict

from rich.console import Console
from rich.logging import RichHandler

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


def setup_logging(
    verbose: bool = False,
    json_format: bool = False,
    log_file: str | None = None,
    max_bytes: int | None = None,
    backup_count: int = 5,
) -> None:
    """Configure logging with the specified options.

    Args:
        verbose: Enable DEBUG level if True, WARNING (no logs) otherwise.
        json_format: Use JSON format if True, rich text otherwise.
        log_file: Path to log file. If None, reads from SECONDBRAIN_LOG_FILE env var.
        max_bytes: Max log file size before rotation. If None, reads from
            SECONDBRAIN_LOG_MAX_BYTES env var (default 10MB).
        backup_count: Number of backup files to keep. If None, reads from
            SECONDBRAIN_LOG_BACKUP_COUNT env var (default 5).
    """
    level = logging.DEBUG if verbose else logging.WARNING

    # Suppress verbose third-party library logs
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)

    # If handlers are already configured, just update the level
    if logging.root.handlers:
        for handler in logging.root.handlers:
            handler.setLevel(level)
        logging.root.setLevel(level)
        return

    if log_file is None:
        log_file = os.environ.get("SECONDBRAIN_LOG_FILE")

    if max_bytes is None:
        max_bytes_env = os.environ.get("SECONDBRAIN_LOG_MAX_BYTES")
        max_bytes = int(max_bytes_env) if max_bytes_env else 10 * 1024 * 1024

    if backup_count == 5:
        backup_count_env = os.environ.get("SECONDBRAIN_LOG_BACKUP_COUNT")
        backup_count = int(backup_count_env) if backup_count_env else 5

    # Auto-detect JSON format from env var if not explicitly passed
    if not json_format:
        log_format_env = os.environ.get("SECONDBRAIN_LOG_FORMAT", "").lower()
        json_format = log_format_env in ("json", "true", "1", "yes")

    if json_format:
        setup_json_logging(level, log_file, max_bytes, backup_count)
    else:
        setup_rich_logging(level, log_file, max_bytes, backup_count)


def setup_rich_logging(
    level: int,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure rich console logging with optional file handler.

    Args:
        level: Logging level constant (e.g., logging.INFO).
        log_file: Path to log file. If set, adds RotatingFileHandler.
        max_bytes: Max log file size before rotation (default 10MB).
        backup_count: Number of backup files to keep (default 5).
    """
    handlers: list[logging.Handler] = [
        RichHandler(console=Console(stderr=True), rich_tracebacks=True)
    ]

    # Add file handler if log file is specified
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
    )


def setup_json_logging(
    level: int,
    log_file: str | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Configure JSON structured logging with optional file handler.

    Args:
        level: Logging level constant (e.g., logging.INFO).
        log_file: Path to log file. If set, adds RotatingFileHandler.
        max_bytes: Max log file size before rotation (default 10MB).
        backup_count: Number of backup files to keep (default 5).
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

    handlers: list[logging.Handler] = [RichHandler()]

    # Add file handler if log file is specified
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JSONFormatter())
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=handlers,
    )

    if logging.root.handlers:
        logging.root.handlers[0].setFormatter(JSONFormatter())


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
