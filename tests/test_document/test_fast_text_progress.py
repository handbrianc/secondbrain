"""Progress-callback tests for fast_text native PDF extraction.

Covers the ``page_progress`` channel added to the fast native-text path:

- :func:`extract_native_pdf_text` fires ``(0, total)`` once after the document
  is opened, then ``(page_index + 1, total)`` after each page's text is
  appended (blank pages tick too — the counter is pages scanned, not segments
  produced);
- :func:`try_fast_pdf_extraction` forwards the callback only when it actually
  extracts (never invoked on the ``None`` routing returns);
- :func:`pdf_page_count` reports page counts and closes the document;
- callback failures are swallowed and never break extraction.

Mocking style matches ``test_fast_text_gaps.py``: fake pypdfium2 module
injected via ``sys.modules`` (no real PDFs).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from secondbrain.document import fast_text


class _FakeTextPage:
    def __init__(self, text: str) -> None:
        self._text = text
        self.closed = 0

    def get_text_range(self) -> str:
        return self._text

    def close(self) -> None:
        self.closed += 1


class _FakePage:
    def __init__(self, text: str) -> None:
        self._textpage = _FakeTextPage(text)

    def get_textpage(self) -> _FakeTextPage:
        return self._textpage


class _FakePdf:
    def __init__(self, pages: list[_FakePage], fail_open: bool = False) -> None:
        self._pages = pages
        self._fail_open = fail_open
        self.closed = 0

    def __len__(self) -> int:
        return len(self._pages)

    def __getitem__(self, index: int) -> _FakePage:
        return self._pages[index]

    def close(self) -> None:
        self.closed += 1


class _FakePdfium:
    def __init__(self, pdf: _FakePdf) -> None:
        self._pdf = pdf

    def PdfDocument(self, path: str) -> _FakePdf:  # noqa: N802 - mirrors pypdfium2
        if self._pdf._fail_open:
            raise RuntimeError("corrupt pdf")
        return self._pdf


def _inject(monkeypatch: pytest.MonkeyPatch, pdfium: Any) -> None:
    import types

    mod: Any = types.ModuleType("pypdfium2")
    mod.PdfDocument = pdfium.PdfDocument
    monkeypatch.setitem(sys.modules, "pypdfium2", mod)


class TestExtractNativePdfTextPageProgress:
    """(0, total) seed then per-page ticks from extract_native_pdf_text."""

    def test_callback_sequence_seed_then_per_page(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf(
            [
                _FakePage("first page text"),
                _FakePage("   \n  "),  # blank page still ticks
                _FakePage("third page text"),
            ]
        )
        _inject(monkeypatch, _FakePdfium(pdf))

        ticks: list[tuple[int, int]] = []
        result = fast_text.extract_native_pdf_text(
            tmp_path / "book.pdf",
            page_progress=lambda done, total: ticks.append((done, total)),
        )

        assert result == [
            {"text": "first page text", "page": 1},
            {"text": "third page text", "page": 3},
        ]
        assert ticks == [(0, 3), (1, 3), (2, 3), (3, 3)]

    def test_no_callback_keeps_legacy_behavior(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([_FakePage("only page text")])
        _inject(monkeypatch, _FakePdfium(pdf))

        result = fast_text.extract_native_pdf_text(tmp_path / "book.pdf")

        assert result == [{"text": "only page text", "page": 1}]

    def test_empty_pdf_ticks_seed_only(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([])
        _inject(monkeypatch, _FakePdfium(pdf))

        ticks: list[tuple[int, int]] = []
        result = fast_text.extract_native_pdf_text(
            tmp_path / "empty.pdf",
            page_progress=lambda done, total: ticks.append((done, total)),
        )

        assert result == []
        assert ticks == [(0, 0)]

    def test_callback_exception_does_not_break_extraction(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([_FakePage("alpha"), _FakePage("beta")])
        _inject(monkeypatch, _FakePdfium(pdf))

        def hostile(done: int, total: int) -> None:
            raise RuntimeError("progress consumer exploded")

        result = fast_text.extract_native_pdf_text(
            tmp_path / "book.pdf", page_progress=hostile
        )

        assert result == [
            {"text": "alpha", "page": 1},
            {"text": "beta", "page": 2},
        ]

    def test_open_failure_returns_empty_without_callback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([], fail_open=True)
        _inject(monkeypatch, _FakePdfium(pdf))

        ticks: list[tuple[int, int]] = []

        def record(done: int, total: int) -> None:
            ticks.append((done, total))

        assert (
            fast_text.extract_native_pdf_text(
                tmp_path / "bad.pdf", page_progress=record
            )
            == []
        )
        # PdfDocument never opened -> no seed tick, no page ticks.
        assert ticks == []


class TestTryFastPdfExtractionProgress:
    """try_fast_pdf_extraction threads the callback through when extracting."""

    @pytest.fixture
    def fast_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _FakeCfg:
            pdf_fast_text_enabled = True
            pdf_ocr_enabled = False
            pdf_structure_probe_enabled = False

        monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())

    def test_callback_forwarded_on_extraction(
        self,
        fast_config: None,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A real extraction forwards ticks; the segments still come back."""
        pdf = _FakePdf([_FakePage("fast body " * 60)])
        _inject(monkeypatch, _FakePdfium(pdf))

        ticks: list[tuple[int, int]] = []
        result = fast_text.try_fast_pdf_extraction(
            tmp_path / "native.pdf",
            page_progress=lambda done, total: ticks.append((done, total)),
        )

        assert result is not None and len(result) == 1
        assert ticks == [(0, 1), (1, 1)]

    def test_callback_not_invoked_when_feature_disabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        class _FakeCfg:
            pdf_fast_text_enabled = False
            pdf_ocr_enabled = False
            pdf_structure_probe_enabled = False

        monkeypatch.setattr("secondbrain.config.config", lambda: _FakeCfg())

        ticks: list[tuple[int, int]] = []
        result = fast_text.try_fast_pdf_extraction(
            tmp_path / "native.pdf",
            page_progress=lambda done, total: ticks.append((done, total)),
        )

        assert result is None
        assert ticks == []

    def test_callback_not_invoked_for_non_pdf(self, tmp_path: Path) -> None:
        ticks: list[tuple[int, int]] = []
        result = fast_text.try_fast_pdf_extraction(
            tmp_path / "notes.txt",
            page_progress=lambda done, total: ticks.append((done, total)),
        )

        assert result is None
        assert ticks == []


class TestPdfPageCount:
    """pdf_page_count sizing helper for the docling extract phase."""

    def test_counts_pages_and_closes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([_FakePage("a"), _FakePage("b"), _FakePage("c")])
        _inject(monkeypatch, _FakePdfium(pdf))

        assert fast_text.pdf_page_count(tmp_path / "book.pdf") == 3
        assert pdf.closed == 1

    def test_open_failure_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _inject(monkeypatch, _FakePdfium(_FakePdf([], fail_open=True)))

        assert fast_text.pdf_page_count(tmp_path / "bad.pdf") == 0

    def test_pypdfium2_missing_returns_zero(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "pypdfium2", None)

        assert fast_text.pdf_page_count(tmp_path / "any.pdf") == 0
