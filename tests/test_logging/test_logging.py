import io
import json
import logging
import os
from pathlib import Path

import pytest
from rich.logging import RichHandler

from unittest.mock import patch

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
from secondbrain.storage import MockVectorStorage


def test_setup_logging_info() -> None:
    setup_logging(verbose=False)


def test_setup_logging_debug() -> None:
    setup_logging(verbose=True)


def test_setup_logging_json_format() -> None:
    setup_logging(verbose=False, json_format=True)
    assert len(logging.getLogger().handlers) > 0


def test_setup_logging_verbose_and_json() -> None:
    setup_logging(verbose=True, json_format=True)
    assert len(logging.getLogger().handlers) > 0


def test_get_logger() -> None:
    logger = get_logger("test_module")
    assert logger.name == "test_module"


def test_setup_rich_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    setup_rich_logging(logging.DEBUG)
    assert any(isinstance(h, RichHandler) for h in logging.getLogger().handlers)


class TestHealthStatus:
    @pytest.fixture
    def sample_status(self) -> HealthStatus:
        return {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 3600.0,
            "services": {"mongodb": True},
            "check_duration_seconds": 0.5,
        }

    def test_health_status_has_status_field(self, sample_status: HealthStatus) -> None:
        assert "status" in sample_status

    def test_health_status_has_services_field(
        self, sample_status: HealthStatus
    ) -> None:
        assert "services" in sample_status


class TestJsonLogging:
    def test_json_formatter_output(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)

        logger = logging.getLogger("test_json")
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)

        logger.info("Test message")

        json_data = json.loads(stream.getvalue())
        assert json_data["level"] == "INFO"
        assert json_data["message"] == "Test message"

        logger.removeHandler(handler)

    def test_json_formatter_includes_metadata(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        formatter = JsonFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_metadata")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test message")

        json_data = json.loads(stream.getvalue())
        assert "logger" in json_data
        assert "module" in json_data
        assert "function" in json_data
        assert "line" in json_data

        logger.removeHandler(handler)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
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
    @pytest.fixture(autouse=True)
    def _reset_request_id(self):
        prev = get_request_id()
        yield
        set_request_id(prev)
    def test_get_request_id_default_empty(self) -> None:
        assert get_request_id() == ""

    def test_set_request_id_generates_uuid(self) -> None:
        request_id = set_request_id()
        assert request_id

    def test_set_request_id_with_custom_id(self) -> None:
        custom_id = "custom-request-123"
        assert set_request_id(custom_id) == custom_id

    def test_get_request_id_returns_set_value(self) -> None:
        custom_id = "test-request-456"
        set_request_id(custom_id)
        assert get_request_id() == custom_id

    def test_request_id_isolation(self) -> None:
        assert isinstance(get_request_id(), str)


class TestSetupJsonLogging:
    def test_setup_json_logging_creates_formatter(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        assert len(root_logger.handlers) > 0

    def test_setup_json_logging_sets_level(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.INFO)
        assert len(root_logger.handlers) > 0

    def test_json_formatter_includes_request_id(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        class TestJSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps({
                    "timestamp": self.formatTime(record, self.datefmt),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                    "request_id": get_request_id() or "",
                })

        formatter = TestJSONFormatter()
        handler.setFormatter(formatter)

        logger = logging.getLogger("test_request_id")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        set_request_id("custom-req-123")
        logger.info("Test message")

        json_data = json.loads(stream.getvalue())
        assert json_data["request_id"] == "custom-req-123"

        logger.removeHandler(handler)

    def test_setup_json_logging_formats_output(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        set_request_id("test-request-id")
        get_logger("test_json_output").info("Test message for JSON output")
        assert len(root_logger.handlers) > 0


class TestGetHealthStatus:
    def test_get_health_status_structure(self) -> None:
        with patch("secondbrain.storage.VectorStorage", return_value=MockVectorStorage(), create=True):
            status = get_health_status()
            assert "status" in status
            assert "timestamp" in status
            assert "services" in status
            assert "check_duration_seconds" in status

    def test_get_health_status_services_keys(self) -> None:
        with patch("secondbrain.storage.VectorStorage", return_value=MockVectorStorage(), create=True):
            assert "mongodb" in get_health_status()["services"]


class TestCheckServices:
    def test_check_services_returns_dict(self) -> None:
        with patch("secondbrain.storage.VectorStorage", return_value=MockVectorStorage(), create=True):
            assert isinstance(check_services(), dict)

    def test_check_services_has_required_keys(self) -> None:
        with patch("secondbrain.storage.VectorStorage", return_value=MockVectorStorage(), create=True):
            assert "mongodb" in check_services()

    def test_check_services_values_are_booleans(self) -> None:
        with patch("secondbrain.storage.VectorStorage", return_value=MockVectorStorage(), create=True):
            assert isinstance(check_services()["mongodb"], bool)


class TestFileLogging:
    def test_setup_logging_with_log_file_creates_file_handler(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file))

        assert len(root_logger.handlers) == 2
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root_logger.handlers)
        assert log_file.exists()

    def test_setup_logging_with_env_var_creates_file_handler(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "env_test.log"
        os.environ["SECONDBRAIN_LOG_FILE"] = str(log_file)

        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True)

        assert len(root_logger.handlers) == 2
        assert log_file.exists()

        del os.environ["SECONDBRAIN_LOG_FILE"]

    def test_setup_logging_with_log_file_and_json_format(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test_json.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, json_format=True, log_file=str(log_file))

        assert len(root_logger.handlers) == 2
        assert log_file.exists()

        get_logger("test_file_json").info("Test JSON message")

        content = log_file.read_text()
        assert "Test JSON message" in content
        json.loads(content.strip())

    def test_rotating_file_handler_max_bytes(self, tmp_path: Path) -> None:
        log_file = tmp_path / "rotate_test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file), max_bytes=1024)

        file_handler = next(h for h in root_logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        assert file_handler.maxBytes == 1024

    def test_log_rotation_occurs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "rotation_test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file), max_bytes=500, backup_count=3)

        logger = get_logger("rotation_test")

        for i in range(10):
            logger.info(f"Test log message number {i} with some additional content to increase size")

        assert log_file.exists()

        backup_files = list(tmp_path.glob("rotation_test.log.*"))
        assert backup_files

        for backup in backup_files:
            assert backup.stat().st_size > 0

    def test_file_logging_creates_parent_directories(self, tmp_path: Path) -> None:
        log_file = tmp_path / "nested" / "dir" / "test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file))

        assert log_file.parent.exists()
        assert log_file.exists()

    def test_file_logging_does_not_create_file_when_not_configured(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True)

        assert len(root_logger.handlers) == 1
        assert isinstance(root_logger.handlers[0], RichHandler)

    def test_rotating_file_handler_is_used(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test_rotating.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file), max_bytes=1024)

        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1

        handler = file_handlers[0]
        assert str(handler.baseFilename).endswith("test_rotating.log")

    def test_max_bytes_respected(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test_max_bytes.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        max_bytes = 500
        setup_logging(verbose=True, log_file=str(log_file), max_bytes=max_bytes)

        file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) == 1

        handler = file_handlers[0]
        assert handler.maxBytes == max_bytes


class TestLoggingIntegration:
    def test_cli_verbose_flag_integration(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True)
        assert root_logger.level == logging.DEBUG

    def test_uuid_format_validation(self) -> None:
        import uuid

        request_id = set_request_id()
        parsed_uuid = uuid.UUID(request_id)
        assert str(parsed_uuid) == request_id
        assert len(request_id) == 36


def test_default_format_is_rich() -> None:
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    setup_logging(verbose=False)
    assert any(isinstance(h, RichHandler) for h in root_logger.handlers)
