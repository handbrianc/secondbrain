import asyncio
import io
import json
import logging
import os
import socket
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as get_package_version
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.logging import RichHandler

from secondbrain.logging import (
    HealthStatus,
    JSONFormatter,
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
            "services": {"qdrant": True},
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

        formatter = JSONFormatter()
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

        formatter = JSONFormatter()
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

    @pytest.mark.asyncio
    async def test_request_id_propagates_to_child_tasks(self) -> None:
        """request_id contextvar is visible inside gather/create_task children."""
        request_id = set_request_id("parent-req-789")
        observed: list[tuple[str, str]] = []

        async def child(tag: str) -> None:
            observed.append((tag, get_request_id()))

        await asyncio.gather(child("gather"), child("gather2"))
        task = asyncio.create_task(child("create_task"))
        await task

        assert observed == [
            ("gather", request_id),
            ("gather2", request_id),
            ("create_task", request_id),
        ]

    @pytest.mark.asyncio
    async def test_logs_in_child_tasks_carry_parent_request_id(self) -> None:
        """Log records emitted inside child tasks parse with the parent request_id."""
        request_id = set_request_id("parent-req-async-logs")
        streams: dict[str, io.StringIO] = {}

        def make_tagged_logger(tag: str) -> logging.Logger:
            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            handler.setFormatter(JSONFormatter())
            logger = logging.getLogger(f"test_async_req_{tag}")
            logger.handlers.clear()
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
            streams[tag] = stream
            return logger

        gather_logger = make_tagged_logger("gather")
        task_logger = make_tagged_logger("task")

        async def child(tag: str, logger: logging.Logger) -> None:
            logger.info("Message from %s", tag)

        await asyncio.gather(child("gather", gather_logger))
        await asyncio.create_task(child("task", task_logger))

        for tag in ("gather", "task"):
            json_data = json.loads(streams[tag].getvalue())
            assert json_data["request_id"] == request_id, tag

    @pytest.mark.asyncio
    async def test_child_task_request_id_isolated_from_sibling_overwrite(self) -> None:
        """A request_id set inside one child does not leak into its siblings."""
        parent_id = set_request_id("parent-iso-req")
        observed: list[str] = []

        async def overwriter() -> None:
            set_request_id("sibling-own-req")
            observed.append(get_request_id())

        async def reader() -> None:
            await asyncio.sleep(0.01)
            observed.append(get_request_id())

        await asyncio.gather(overwriter(), reader())

        assert observed[0] == "sibling-own-req"
        assert observed[1] == parent_id
        assert get_request_id() == parent_id


class TestSetupJsonLogging:
    def test_setup_json_logging_creates_formatter(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        assert len(root_logger.handlers) > 0
        assert isinstance(root_logger.handlers[0], logging.StreamHandler)
        assert not isinstance(root_logger.handlers[0], RichHandler)

    def test_setup_json_logging_sets_level(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.INFO)
        assert len(root_logger.handlers) > 0

    def test_json_formatter_includes_request_id(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)

        formatter = JSONFormatter()
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
        stream = io.StringIO()
        root_logger.handlers[0].setStream(stream)
        set_request_id("test-request-id")
        get_logger("test_json_output").info("Test message for JSON output")
        json_data = json.loads(stream.getvalue().strip())
        assert json_data["message"] == "Test message for JSON output"
        assert json_data["request_id"] == "test-request-id"
        assert len(root_logger.handlers) > 0

    def test_json_formatter_includes_context_fields(self) -> None:
        """JSON output includes service, hostname, pid, and version fields."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test_context_fields")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Context field message")

        json_data = json.loads(stream.getvalue())
        assert json_data["service"] == "secondbrain"
        assert json_data["hostname"] == socket.gethostname()
        assert json_data["pid"] == os.getpid()
        assert json_data["version"] == get_package_version("secondbrain")

        logger.removeHandler(handler)

    def test_json_formatter_version_falls_back_to_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Missing package metadata yields version "unknown" instead of raising."""
        from secondbrain.logging import _get_package_version

        def raise_missing(name: str) -> str:
            raise PackageNotFoundError(name)

        monkeypatch.setattr("secondbrain.logging._package_version", raise_missing)
        assert _get_package_version() == "unknown"

    def test_setup_json_logging_output_has_all_fields(self) -> None:
        """Real setup_json_logging output carries the full standard field set."""
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_json_logging(logging.DEBUG)
        stream = io.StringIO()
        root_logger.handlers[0].setStream(stream)
        set_request_id("field-check-req")
        get_logger("test_json_full_fields").info("Field completeness message")

        json_data = json.loads(stream.getvalue().strip())
        assert json_data["level"] == "INFO"
        assert json_data["logger"] == "test_json_full_fields"
        assert json_data["module"]
        assert json_data["function"]
        assert isinstance(json_data["line"], int)
        assert json_data["timestamp"]
        assert json_data["service"] == "secondbrain"
        assert json_data["hostname"] == socket.gethostname()
        assert json_data["pid"] == os.getpid()
        assert json_data["version"] == get_package_version("secondbrain")
        assert json_data["request_id"] == "field-check-req"


class TestGetHealthStatus:
    def test_get_health_status_structure(self) -> None:
        with patch(
            "secondbrain.storage.StorageFactory.create_from_config",
            return_value=MockVectorStorage(),
        ):
            status = get_health_status()
            assert "status" in status
            assert "timestamp" in status
            assert "services" in status
            assert "check_duration_seconds" in status

    def test_get_health_status_services_keys(self) -> None:
        with patch(
            "secondbrain.storage.StorageFactory.create_from_config",
            return_value=MockVectorStorage(),
        ):
            assert "qdrant" in get_health_status()["services"]


class TestCheckServices:
    def test_check_services_returns_dict(self) -> None:
        with patch(
            "secondbrain.storage.StorageFactory.create_from_config",
            return_value=MockVectorStorage(),
        ):
            assert isinstance(check_services(), dict)

    def test_check_services_has_required_keys(self) -> None:
        with patch(
            "secondbrain.storage.StorageFactory.create_from_config",
            return_value=MockVectorStorage(),
        ):
            assert "qdrant" in check_services()

    def test_check_services_values_are_booleans(self) -> None:
        with patch(
            "secondbrain.storage.StorageFactory.create_from_config",
            return_value=MockVectorStorage(),
        ):
            assert isinstance(check_services()["qdrant"], bool)


class TestFileLogging:
    @pytest.fixture(autouse=True)
    def _restore_root_logger_handlers(self) -> Iterator[None]:
        """Restore root handlers so deleted tmp-path file handlers don't survive."""
        root_logger = logging.getLogger()
        snapshot = list(root_logger.handlers)
        yield
        root_logger.handlers = snapshot

    def test_setup_logging_with_log_file_creates_file_handler(
        self, tmp_path: Path
    ) -> None:
        log_file = tmp_path / "test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(verbose=True, log_file=str(log_file))

        assert len(root_logger.handlers) == 2
        assert any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root_logger.handlers
        )
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

    def test_setup_logging_without_log_file_attaches_no_file_handler(self) -> None:
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        os.environ.pop("SECONDBRAIN_LOG_FILE", None)
        setup_logging(verbose=True)

        assert len(root_logger.handlers) == 1
        assert not any(
            isinstance(h, logging.handlers.RotatingFileHandler)
            for h in root_logger.handlers
        )

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

        file_handler = next(
            h
            for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        )
        assert file_handler.maxBytes == 1024

    def test_log_rotation_occurs(self, tmp_path: Path) -> None:
        log_file = tmp_path / "rotation_test.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_logging(
            verbose=True, log_file=str(log_file), max_bytes=500, backup_count=3
        )

        logger = get_logger("rotation_test")

        for i in range(10):
            logger.info(
                f"Test log message number {i} with some additional content to increase size"
            )

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

        file_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(file_handlers) == 1

        handler = file_handlers[0]
        assert str(handler.baseFilename).endswith("test_rotating.log")

    def test_max_bytes_respected(self, tmp_path: Path) -> None:
        log_file = tmp_path / "test_max_bytes.log"
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        max_bytes = 500
        setup_logging(verbose=True, log_file=str(log_file), max_bytes=max_bytes)

        file_handlers = [
            h
            for h in root_logger.handlers
            if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
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
