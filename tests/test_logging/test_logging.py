"""Tests for logging module."""

import logging

from secondbrain.logging import get_logger, setup_logging


def test_setup_logging_info() -> None:
    """Test setup logging with INFO level."""
    setup_logging(verbose=False)
    # Should not raise any errors


def test_setup_logging_debug() -> None:
    """Test setup logging with DEBUG level."""
    setup_logging(verbose=True)
    # Should not raise any errors


def test_get_logger() -> None:
    """Test getting a logger instance."""
    logger = get_logger("test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test"
