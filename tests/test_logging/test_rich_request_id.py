"""Tests for request-ID correlation in the Rich log transport.

Spec (structured-logging, Request ID correlation): after set_request_id() log
output SHALL include the request ID - the JSON transport carries it as a
structured field, the Rich transport appends it to the rendered message and
stays clean when no request ID is set.
"""

import io
import json
import logging
from collections.abc import Iterator

import pytest
from rich.console import Console
from rich.logging import RichHandler

from secondbrain.logging import (
    JSONFormatter,
    RichRequestFormatter,
    get_request_id,
    set_request_id,
    setup_rich_logging,
)


def _record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
    """Build a standalone log record for direct formatter/handler testing."""
    return logging.LogRecord(
        name="secondbrain.tests.rich",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=None,
        exc_info=None,
    )


class TestRichRequestFormatter:
    """Unit tests for the Rich transport request-ID formatter."""

    @pytest.fixture(autouse=True)
    def _reset_request_id(self) -> Iterator[None]:
        """Start and end each test with an empty request-ID context."""
        set_request_id("")
        yield
        set_request_id("")

    def test_appends_request_id_when_set(self) -> None:
        """A set request ID is appended to the rendered message."""
        set_request_id("req-123")
        formatter = RichRequestFormatter(fmt="%(message)s")

        assert formatter.format(_record("hello world")) == (
            "hello world [request_id=req-123]"
        )

    def test_stays_clean_without_request_id(self) -> None:
        """With no request ID set the message is rendered unchanged."""
        assert get_request_id() == ""
        formatter = RichRequestFormatter(fmt="%(message)s")

        assert formatter.format(_record("hello world")) == "hello world"

    def test_json_transport_message_not_suffixed(self) -> None:
        """The JSON transport keeps the raw message and structured request_id."""
        set_request_id("req-123")
        entry = json.loads(JSONFormatter().format(_record("hello world")))

        assert entry["message"] == "hello world"
        assert entry["request_id"] == "req-123"


class TestRichTransportRendersRequestId:
    """End-to-end tests for RichHandler rendering with the formatter."""

    @pytest.fixture(autouse=True)
    def _reset_request_id(self) -> Iterator[None]:
        """Start and end each test with an empty request-ID context."""
        set_request_id("")
        yield
        set_request_id("")

    @staticmethod
    def _render(record: logging.LogRecord) -> str:
        """Render a record through a RichHandler like setup_rich_logging does."""
        stream = io.StringIO()
        handler = RichHandler(
            console=Console(file=stream, width=200), rich_tracebacks=False
        )
        handler.setFormatter(RichRequestFormatter(fmt="%(message)s", datefmt="[%X]"))
        handler.emit(record)
        return stream.getvalue()

    def test_rich_output_contains_request_id_when_set(self) -> None:
        """Rich-rendered output includes the request ID when one is set."""
        set_request_id("req-abc-123")

        output = self._render(_record("Ingest finished", logging.WARNING))

        assert "Ingest finished" in output
        assert "request_id=req-abc-123" in output

    def test_rich_output_clean_without_request_id(self) -> None:
        """Rich-rendered output has no request-id marker when none is set."""
        assert get_request_id() == ""

        output = self._render(_record("Ingest finished", logging.WARNING))

        assert "Ingest finished" in output
        # The record's source path is rendered too, so match the concrete
        # suffix marker rather than the bare "request_id" substring.
        assert "request_id=" not in output


class TestSetupRichLoggingWiring:
    """Verify setup_rich_logging installs the request-ID formatter."""

    @pytest.fixture(autouse=True)
    def _restore_root_logging(self) -> Iterator[None]:
        """Snapshot root handlers (with levels) and restore them afterwards."""
        root_logger = logging.getLogger()
        handlers = list(root_logger.handlers)
        handler_levels = [(handler, handler.level) for handler in handlers]
        root_level = root_logger.level
        root_logger.handlers = []
        yield
        root_logger.handlers = handlers
        for handler, level in handler_levels:
            handler.setLevel(level)
        root_logger.setLevel(root_level)

    def test_rich_handler_uses_request_formatter(self) -> None:
        """The RichHandler configured by setup_rich_logging carries the formatter."""
        # basicConfig is a no-op while root has handlers (pytest's capture
        # handler re-attaches after fixture setup), so clear them first like
        # the other setup_rich_logging tests do.
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        setup_rich_logging(logging.INFO)

        rich_handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, RichHandler)
        ]
        assert len(rich_handlers) == 1
        assert isinstance(rich_handlers[0].formatter, RichRequestFormatter)
