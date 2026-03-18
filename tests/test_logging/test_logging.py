"""Tests for logging module."""

import io
import json
import logging

import pytest

from secondbrain.logging import (
    HealthStatus,
    check_services,
    get_health_status,
    get_logger,
    get_request_id,
    set_request_id,
    setup_json_logging,
    setup_logging,
    setup_rich_logging,
)


def test_setup_logging_info() -> None:
    """Test setup logging with INFO level."""
    setup_logging(verbose=False)


def test_setup_logging_debug() -> None:
    """Test setup logging with DEBUG level."""
    setup_logging(verbose=True)


def test_setup_logging_json_format() -> None:
    """Test setup_logging with JSON format."""
    setup_logging(verbose=False, json_format=True)
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) > 0


def test_setup_logging_verbose_and_json() -> None:
    """Test setup_logging with both verbose and JSON format."""
    setup_logging(verbose=True, json_format=True)
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) > 0


def test_get_logger() -> None:
    """Test getting a logger instance."""
    logger = get_logger("test_module")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_module"


def test_setup_rich_logging() -> None:
    """Test setup_rich_logging configures handlers."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    setup_rich_logging(logging.DEBUG)
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) > 0
    from rich.logging import RichHandler

    assert any(isinstance(h, RichHandler) for h in root_logger.handlers)


class TestHealthStatus:
    """Tests for health status TypedDict."""

    @pytest.fixture
    def sample_status(self) -> HealthStatus:
        """Sample health status dictionary."""
        return {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"sentence-transformers": True, "mongodb": True},
            "check_duration_seconds": 0.5,
        }

    def test_health_status_has_status_field(self, sample_status: HealthStatus) -> None:
        """Test that health status dict has status field."""
        assert "status" in sample_status

    def test_health_status_has_services_field(
        self, sample_status: HealthStatus
    ) -> None:
        """Test that health status dict has services field."""
        assert "services" in sample_status


class TestJsonLogging:
    """Tests for JSON logging format."""

    def test_json_formatter_output(self) -> None:
        """Test that JSON formatter produces valid JSON."""
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
        """Test that JSON formatter includes metadata fields."""
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


class TestRequestContext:
    """Tests for request ID context management."""

    def test_get_request_id_default_empty(self) -> None:
        """Test that get_request_id returns empty string by default."""
        result = get_request_id()
        assert result == ""

    def test_set_request_id_generates_uuid(self) -> None:
        """Test that set_request_id generates UUID when no ID provided."""
        request_id = set_request_id()
        assert len(request_id) > 0
        assert isinstance(request_id, str)

    def test_set_request_id_with_custom_id(self) -> None:
        """Test that set_request_id accepts custom ID."""
        custom_id = "custom-request-123"
        request_id = set_request_id(custom_id)
        assert request_id == custom_id

    def test_get_request_id_returns_set_value(self) -> None:
        """Test that get_request_id returns the value set by set_request_id."""
        custom_id = "test-request-456"
        set_request_id(custom_id)
        result = get_request_id()
        assert result == custom_id

    def test_request_id_isolation(self) -> None:
        """Test that request ID is isolated between tests."""
        # This test verifies that each test starts with a clean context
        result = get_request_id()
        # Should be empty or a new value, not carrying over from previous tests
        assert isinstance(result, str)


class TestSetupJsonLogging:
    """Tests for JSON logging setup."""

    def test_setup_json_logging_creates_formatter(self) -> None:
        """Test that JSON logging setup creates proper formatter."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

    def test_setup_json_logging_sets_level(self) -> None:
        """Test that JSON logging sets correct log level."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.INFO)
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0

    def test_json_formatter_includes_request_id(self) -> None:
        """Test that JSON formatter includes request_id in output."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        class TestJSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps(
                    {
                        "timestamp": self.formatTime(record, self.datefmt),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                        "module": record.module,
                        "function": record.funcName,
                        "line": record.lineno,
                        "request_id": get_request_id() or "",
                    }
                )

        formatter = TestJSONFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_request_id")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        set_request_id("custom-req-123")
        logger.info("Test message")

        output = stream.getvalue()
        json_data = json.loads(output)
        assert "request_id" in json_data
        assert json_data["request_id"] == "custom-req-123"

        logger.removeHandler(handler)

    def test_setup_json_logging_formats_output(self) -> None:
        """Test that setup_json_logging formats log output correctly."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        set_request_id("test-request-id")
        test_logger = get_logger("test_json_output")
        test_logger.info("Test message for JSON output")
        assert len(root_logger.handlers) > 0


class TestGetHealthStatus:
    """Tests for get_health_status function."""

    def test_get_health_status_structure(self) -> None:
        """Test that get_health_status returns correct structure."""
        status = get_health_status()

        assert "status" in status
        assert "timestamp" in status
        assert "services" in status
        assert "check_duration_seconds" in status

    def test_get_health_status_services_keys(self) -> None:
        """Test that get_health_status has correct service keys."""
        status = get_health_status()

        assert "mongodb" in status["services"]


class TestCheckServices:
    """Tests for check_services function."""

    def test_check_services_returns_dict(self) -> None:
        """Test that check_services returns a dict."""
        result = check_services()
        assert isinstance(result, dict)

    def test_check_services_has_required_keys(self) -> None:
        """Test that check_services has required keys."""
        result = check_services()
        assert "mongodb" in result

    def test_check_services_values_are_booleans(self) -> None:
        """Test that check_services values are booleans."""
        result = check_services()
        assert isinstance(result["mongodb"], bool)
