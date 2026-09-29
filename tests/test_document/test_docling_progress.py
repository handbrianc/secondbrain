"""Unit tests for the docling page-batch progress scraper.

Covers :func:`secondbrain.document.docling_progress.scraped_page_progress`:

- a docling-shaped ``Finished converting pages N/M`` DEBUG record routed
  through the attached handler invokes ``on_tick(N, M)``;
- non-matching records produce no ticks;
- the logger level is raised to DEBUG during the block and restored on exit;
- the handler is removed after exit;
- ``on_tick`` exceptions are swallowed (the block still runs);
- a missing docling module degrades to a no-op context manager.

The test suite stubs the ``docling`` package with MagicMocks (see
``tests/test_document/conftest.py``), which makes
``import docling.pipeline.base_pipeline`` fail with ModuleNotFoundError. The
happy-path tests therefore inject a tiny stub module via ``sys.modules``
(mirroring the fake-pypdfium2 pattern in ``test_fast_text_gaps.py``); the
scraper only needs the import to succeed, it never touches the module's
attributes. No real conversion is run — the message format mirrors the
verified upstream line in ``docling/pipeline/base_pipeline.py``::

    _log.debug(f"Finished converting pages {total_pages_processed}/"
               f"{len(conv_res.pages)} time={end_batch_time:.3f}")
"""

from __future__ import annotations

import logging
import sys

import pytest

from secondbrain.document.docling_progress import (
    _PageBatchHandler,
    scraped_page_progress,
)

TARGET = "docling.pipeline.base_pipeline"


def _make_record(message: str, level: int = logging.DEBUG) -> logging.LogRecord:
    return logging.LogRecord(
        name=TARGET,
        level=level,
        pathname="base_pipeline.py",
        lineno=357,
        msg=message,
        args=(),
        exc_info=None,
    )


def _inject_stub_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``import docling.pipeline.base_pipeline`` succeed under the stub.

    The suite-wide conftest replaces the ``docling`` package with a
    MagicMock, so the submodule import raises ModuleNotFoundError and the
    scraper would degrade to its no-op path. Registering a real (empty) leaf
    module in ``sys.modules`` short-circuits the parent-package import (the
    leaf lookup hits first), restoring the import success the real package
    provides — the same trick the fake-pypdfium2 tests use.
    """
    import types

    monkeypatch.setitem(sys.modules, TARGET, types.ModuleType(TARGET))


class TestPageBatchHandler:
    """_PageBatchHandler regex parsing and exception containment."""

    def test_parses_done_and_total_from_docling_message(self) -> None:
        ticks: list[tuple[int, int]] = []
        handler = _PageBatchHandler(lambda d, t: ticks.append((d, t)))

        handler.emit(_make_record("Finished converting pages 6/12 time=1.234"))

        assert ticks == [(6, 12)]

    def test_non_matching_message_ignored(self) -> None:
        ticks: list[tuple[int, int]] = []
        handler = _PageBatchHandler(lambda d, t: ticks.append((d, t)))

        handler.emit(_make_record("Finished converting page 1"))
        handler.emit(_make_record("Finished converting pages x/y time=1.0"))
        handler.emit(_make_record("Starting pipeline"))

        assert ticks == []

    def test_on_tick_exception_swallowed(self) -> None:
        def hostile(done: int, total: int) -> None:
            raise RuntimeError("consumer exploded")

        handler = _PageBatchHandler(hostile)

        # Must not raise.
        handler.emit(_make_record("Finished converting pages 3/9 time=0.100"))


class TestScrapedPageProgress:
    """scraped_page_progress level/handler lifecycle and delivery."""

    def test_ticks_delivered_and_level_restored(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _inject_stub_docling(monkeypatch)
        log = logging.getLogger(TARGET)
        original_level = log.level
        original_propagate = log.propagate
        ticks: list[tuple[int, int]] = []
        batch_record = _make_record("Finished converting pages 4/10 time=0.500")

        with caplog.at_level(logging.DEBUG), scraped_page_progress(
            lambda d, t: ticks.append((d, t))
        ):
            assert log.level == logging.DEBUG
            assert log.propagate is False
            # The record travels through the real logger hierarchy, proving
            # both the level raise and the attached handler work end to end.
            log.handle(batch_record)

        assert ticks == [(4, 10)]
        assert log.level == original_level
        assert log.propagate is original_propagate
        assert not any(record.name == TARGET for record in caplog.records)
        handlers = [h for h in log.handlers if isinstance(h, _PageBatchHandler)]
        assert handlers == []

    def test_level_restored_after_exception_inside_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _inject_stub_docling(monkeypatch)
        log = logging.getLogger(TARGET)
        original_level = log.level

        with pytest.raises(RuntimeError), scraped_page_progress(lambda *_: None):
            raise RuntimeError("conversion blew up")

        assert log.level == original_level

    def test_cleanup_when_block_body_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The finally-path removes the handler and restores the level."""
        _inject_stub_docling(monkeypatch)
        log = logging.getLogger(TARGET)
        original_level = log.level
        ticks: list[tuple[int, int]] = []

        with pytest.raises(RuntimeError):
            with scraped_page_progress(lambda d, t: ticks.append((d, t))):
                log.handle(_make_record("Finished converting pages 2/8 time=0.100"))
                assert ticks == [(2, 8)]  # handler was live inside the block
                raise RuntimeError("conversion blew up")

        assert log.level == original_level
        assert not any(isinstance(h, _PageBatchHandler) for h in log.handlers)
        # Post-exit records are no longer intercepted (handler detached).
        log.handle(_make_record("Finished converting pages 3/8 time=0.100"))
        assert ticks == [(2, 8)]

    def test_on_tick_exception_does_not_break_block(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hostile consumer must not fail the conversion inside the block."""
        _inject_stub_docling(monkeypatch)

        def tick(done: int, total: int) -> None:
            raise RuntimeError("consumer exploded")

        executed: list[bool] = []
        with scraped_page_progress(tick):
            logging.getLogger(TARGET).handle(
                _make_record("Finished converting pages 1/5 time=0.010")
            )
            executed.append(True)

        assert executed == [True]

    def test_noop_when_docling_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failing docling import degrades to a plain no-op block."""
        import sys

        # Simulate docling being missing by making the submodule import fail
        # (a None entry in sys.modules makes `import` raise ImportError).
        monkeypatch.setitem(sys.modules, "docling.pipeline.base_pipeline", None)

        ran: list[bool] = []
        with scraped_page_progress(lambda *_: ran.append(True)):
            pass  # must be a plain no-op, no handler attached

        assert ran == []
        log = logging.getLogger(TARGET)
        assert not any(isinstance(h, _PageBatchHandler) for h in log.handlers)
