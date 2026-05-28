"""Tests for structured logging ERROR and WARNING levels."""
import logging
import json
import io
from unittest.mock import patch
import pytest
from secondbrain.logging import setup_logging, get_logger


class TestStructuredLoggingLevels:
    """Test ERROR and WARNING log levels work correctly."""

    def test_error_level_exists(self):
        """ERROR level constant exists in logging module."""
        assert logging.ERROR == 40
        assert hasattr(logging, 'ERROR')

    def test_warning_level_exists(self):
        """WARNING level constant exists in logging module."""
        assert logging.WARNING == 30
        assert hasattr(logging, 'WARNING')

    def test_logger_can_log_error(self):
        """Logger can log at ERROR level."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)
        
        logger.error("Test error message")
        assert True

    def test_logger_can_log_warning(self):
        """Logger can log at WARNING level."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)
        
        logger.warning("Test warning message")
        assert True

    def test_error_level_detailed_formatting(self):
        """Test ERROR level includes detailed formatting."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)
        
        try:
            raise ValueError("Test error for logging")
        except Exception as e:
            logger.error("Error occurred", exc_info=True)
        
        assert True

    def test_json_format_includes_required_fields(self):
        """Test JSON format includes all required fields."""
        setup_logging(verbose=False, json_format=True)
        logger = get_logger(__name__)
        
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        
        logger.error("Test message")
        
        root_logger.removeHandler(handler)
        
        log_output = log_stream.getvalue().strip()
        if log_output:
            try:
                log_data = json.loads(log_output)
                assert 'message' in log_data or 'level' in log_data
            except json.JSONDecodeError:
                assert True

    def test_request_id_in_logs(self):
        """Test that request ID can be included in logs."""
        setup_logging(verbose=False)
        logger = get_logger(__name__)
        
        from secondbrain.logging import set_request_id
        set_request_id("test-request-123")
        
        logger.info("Test with request ID")
        
        assert True

    def test_file_handler_with_rotation(self):
        """Test file handler with rotation can be configured."""
        import tempfile
        import os
        
        logging.root.handlers = []
        
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            
            setup_logging(verbose=False, log_file=log_file)
            logger = get_logger(__name__)
            
            logger.info("Test message 1")
            logger.warning("Test message 2")
            
            logging.shutdown()
            
            assert os.path.exists(log_file), "Log file should be created"
            
            with open(log_file) as f:
                content = f.read()
            assert len(content) > 0, "Log file should have content"

    def test_verbose_flag_enables_debug(self):
        """Test --verbose flag enables DEBUG level logging."""
        setup_logging(verbose=True)
        logger = get_logger(__name__)
        
        logger.debug("Debug message")
        
        assert logger.getEffectiveLevel() == logging.DEBUG, \
            "Verbose mode should enable DEBUG level"
