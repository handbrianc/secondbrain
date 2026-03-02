"""Tests for logging module."""

import io
import json
import logging

import pytest

from secondbrain.logging import HealthStatus, setup_logging


def test_setup_logging_info() -> None:
    """Test setup logging with INFO level."""
    setup_logging(verbose=False)


def test_setup_logging_debug() -> None:
    """Test setup logging with DEBUG level."""
    setup_logging(verbose=True)


def test_get_logger() -> None:
    """Test getting a logger instance."""
    logger = logging.getLogger("test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test"


class TestHealthStatus:
    """Tests for health status TypedDict."""

    @pytest.fixture
    def sample_status(self) -> HealthStatus:
        """Sample health status dictionary."""
        return {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"ollama": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }

    def test_health_status_has_status_field(self, sample_status: HealthStatus) -> None:
        """Test health status dict has status field."""
        assert "status" in sample_status

    def test_health_status_has_services_field(
        self, sample_status: HealthStatus
    ) -> None:
        """Test health status dict has services field."""
        assert "services" in sample_status


class TestJsonLogging:
    """Tests for JSON logging format."""

    def test_json_formatter_output(self) -> None:
        """Test JSON formatter produces valid JSON."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)

        logger = logging.getLogger("test_json")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("Test message")

        output = stream.getvalue()
        # Should be valid JSON
        json_data = json.loads(output)
        assert json_data["level"] == "INFO"
        assert json_data["message"] == "Test message"

        logger.removeHandler(handler)

    def test_json_formatter_includes_metadata(self) -> None:
        """Test JSON formatter includes metadata fields."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        formatter = JsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_metadata")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test message")

        output = stream.getvalue()
        json_data = json.loads(output)
        assert "logger" in json_data
        assert "module" in json_data
        assert "function" in json_data
        assert "line" in json_data

        logger.removeHandler(handler)


class JsonFormatter(logging.Formatter):
    """JSON formatter for logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        return json.dumps(log_entry)
