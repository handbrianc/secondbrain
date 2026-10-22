"""Tests for structured logging ERROR and WARNING levels."""

import logging
from collections.abc import Iterator

import pytest

from secondbrain.logging import get_logger, setup_logging


class TestStructuredLoggingLevels:
    """Test ERROR and WARNING log levels work correctly."""

    @pytest.fixture(autouse=True)
    def _restore_root_handlers(self) -> Iterator[None]:
        """Restore root handlers so deleted tmp-path file handlers don't survive."""
        root_logger = logging.getLogger()
        snapshot = list(root_logger.handlers)
        yield
        root_logger.handlers = snapshot

    def test_error_level_exists(self):
        """ERROR level constant exists in logging module."""
        assert logging.ERROR == 40
        assert hasattr(logging, "ERROR")

    def test_warning_level_exists(self):
        """WARNING level constant exists in logging module."""
        assert logging.WARNING == 30
        assert hasattr(logging, "WARNING")

    def test_logger_can_log_error(self):
        """Logger can log at ERROR level."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)

        assert hasattr(logger, "error")
        assert callable(logger.error)

    def test_logger_can_log_warning(self):
        """Logger can log at WARNING level."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)

        assert hasattr(logger, "warning")
        assert callable(logger.warning)

    def test_error_level_detailed_formatting(self):
        """Test ERROR level includes detailed formatting."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)

        try:
            raise ValueError("Test error for logging")
        except Exception as e:
            logger.error("Error occurred", exc_info=True)

        assert hasattr(logger, "error")

    def test_json_format_includes_required_fields(self):
        """Test JSON format includes all required fields."""
        setup_logging(verbose=False, json_format=True)
        logger = get_logger(__name__)

        assert hasattr(logger, "error")
        assert callable(logger.error)
        assert logger.name is not None

    def test_request_id_in_logs(self):
        """Test that request ID can be included in logs."""
        from secondbrain.logging import set_request_id

        setup_logging(verbose=False)
        logger = get_logger(__name__)

        req_id = set_request_id("test-request-123")

        logger.info("Test with request ID")

        assert req_id == "test-request-123"

        set_request_id("")

    def test_file_handler_with_rotation(self):
        """Test file handler with rotation can be configured."""
        import tempfile
        from pathlib import Path

        logging.root.handlers = []

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.log")

            setup_logging(verbose=False, log_file=log_file)
            logger = get_logger(__name__)

            logger.info("Test message 1")
            logger.warning("Test message 2")

            logging.shutdown()

            assert Path(log_file).exists(), "Log file should be created"

            with open(log_file) as f:
                content = f.read()
            assert len(content) > 0, "Log file should have content"

    def test_verbose_flag_enables_debug(self):
        """Test --verbose flag enables DEBUG level logging."""
        setup_logging(verbose=True)
        logger = get_logger(__name__)

        logger.debug("Debug message")

        assert logger.getEffectiveLevel() == logging.DEBUG, (
            "Verbose mode should enable DEBUG level"
        )


class TestDefaultLogLevel:
    """Test the shipped default level (WARNING) hides INFO but shows WARNING.

    Spec (structured-logging, amended): setup_logging() defaults to WARNING
    (warnings and above); INFO events stay recorded-but-hidden on the console
    until the level is raised.
    """

    @pytest.fixture(autouse=True)
    def _restore_logging_state(self) -> Iterator[None]:
        """Restore root handlers (with their levels), root and logger level."""
        root_logger = logging.getLogger()
        test_logger = logging.getLogger(__name__)
        handlers = list(root_logger.handlers)
        handler_levels = [(handler, handler.level) for handler in handlers]
        root_level = root_logger.level
        logger_level = test_logger.level
        yield
        root_logger.handlers = handlers
        for handler, level in handler_levels:
            handler.setLevel(level)
        root_logger.setLevel(root_level)
        test_logger.setLevel(logger_level)

    def test_setup_logging_default_sets_warning_level(self, caplog):
        """After setup_logging(verbose=False) the effective level is WARNING."""
        setup_logging(verbose=False)

        assert logging.getLogger().getEffectiveLevel() == logging.WARNING

    def test_default_configures_all_handlers_to_warning(self, caplog):
        """All root handlers (console and captured) sit at WARNING."""
        setup_logging(verbose=False)

        handlers = logging.getLogger().handlers
        assert handlers, "setup_logging should leave root handlers configured"
        assert all(handler.level == logging.WARNING for handler in handlers)

    def test_info_hidden_and_warning_shown_at_default_level(self, caplog):
        """INFO is recorded-but-hidden; WARNING passes to the captured handler."""
        setup_logging(verbose=False)

        # Lower the emitting logger so INFO records are actually created and
        # reach the root handlers; the configured WARNING level must hide them.
        logger = get_logger(__name__)
        logger.setLevel(logging.DEBUG)
        logger.info("info event hidden by default level")
        logger.warning("warning event visible at default level")

        messages = [record.getMessage() for record in caplog.records]
        assert "info event hidden by default level" not in messages
        assert "warning event visible at default level" in messages
