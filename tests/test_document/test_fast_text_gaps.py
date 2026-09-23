"""Gap tests for fast_text page-stamp parsing and native PDF extraction.

Targets the uncovered branches reported by coverage for
``secondbrain/document/fast_text.py``:

- ``extract_printed_page`` rejecting page markers outside the sanity bound;
- ``_checked_page`` raising for out-of-range stamps;
- ``footer_page_offset`` skipping non-matching footer text and out-of-range
  printed values, and rejecting inconsistent offsets;
- ``resolve_printed_pages`` skipping out-of-range footer stamps and leaving
  pages outside the footer-covered set untouched;
- ``extract_native_pdf_text`` pypdfium2-import failure, happy path with blank
  pages skipped, extraction errors, and PdfDocument open failure (mocked
  pypdfium2 module, no real PDFs).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from secondbrain.document import fast_text


class TestPrintedPageBounds:
    """extract_printed_page / _checked_page sanity bound."""

    @pytest.mark.unit
    def test_marker_below_one_returns_none(self) -> None:
        assert fast_text.extract_printed_page("[ 0 ] page header") is None

    @pytest.mark.unit
    def test_marker_above_max_returns_none(self) -> None:
        assert fast_text.extract_printed_page("citation [ 50000 ] IEEE") is None

    @pytest.mark.unit
    def test_valid_marker_boundary_values(self) -> None:
        assert fast_text.extract_printed_page("[ 1 ]") == 1
        assert fast_text.extract_printed_page("[ 9999 ]") == 9999

    @pytest.mark.unit
    def test_checked_page_raises_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            fast_text._checked_page(0)
        with pytest.raises(ValueError):
            fast_text._checked_page(10000)

    @pytest.mark.unit
    def test_checked_page_passes_in_range(self) -> None:
        assert fast_text._checked_page(42) == 42


class TestFooterPageOffset:
    """footer_page_offset sampling, skips, and agreement gates."""

    def test_non_matching_footer_texts_do_not_count_toward_three(self) -> None:
        """Only two matching footers plus noise -> below the 3-sample gate."""
        nav = {
            88: "78 / 634",
            89: "not a footer at all",
            90: "79 / 634",
            91: "  ",  # whitespace-only, also non-matching
        }
        assert fast_text.footer_page_offset(nav) is None

    def test_out_of_range_printed_value_skipped(self) -> None:
        nav = {
            88: "0 / 634",  # _checked_page(0) raises -> skip
            89: "79 / 634",
            90: "80 / 634",
            91: "81 / 634",
        }
        assert fast_text.footer_page_offset(nav) == 10

    def test_printed_at_or_above_physical_skipped(self) -> None:
        nav = {
            88: "88 / 634",  # printed == physical -> not sampled
            89: "79 / 634",
            90: "80 / 634",
            91: "81 / 634",
        }
        assert fast_text.footer_page_offset(nav) == 10

    def test_fewer_than_three_samples_returns_none(self) -> None:
        nav = {88: "78 / 634", 89: "79 / 634"}
        assert fast_text.footer_page_offset(nav) is None

    def test_inconsistent_offsets_rejected(self) -> None:
        nav = {
            88: "78 / 634",  # offset 10
            89: "79 / 634",  # offset 10
            90: "12 / 634",  # offset 78 -> disagreement
        }
        assert fast_text.footer_page_offset(nav) is None

    def test_agreement_below_eighty_percent_rejected(self) -> None:
        nav = {
            88: "78 / 634",
            89: "79 / 634",
            90: "80 / 634",
            91: "13 / 634",  # 3 agree, 1 disagrees -> 75% < 80%
        }
        assert fast_text.footer_page_offset(nav) is None

    def test_majority_offset_wins_with_agreement(self) -> None:
        nav = {
            88: "78 / 634",
            89: "79 / 634",
            90: "80 / 634",
            91: "81 / 634",
            92: "14 / 634",  # 4 of 5 agree on 10 (80%)
        }
        assert fast_text.footer_page_offset(nav) == 10


def _nav_chunk(physical: int, printed: int, total: int = 634) -> dict[str, Any]:
    return {
        "page_number": physical,
        "chunk_text": f"{printed} / {total}",
        "element_type": "navigation",
        "chunk_role": "navigation",
        "printed_page": None,
    }


def _body_chunk(
    physical: int, text: str = "body prose", printed: Any = None
) -> dict[str, Any]:
    return {
        "page_number": physical,
        "chunk_text": text,
        "element_type": "body",
        "chunk_role": "body",
        "printed_page": printed,
    }


class TestResolvePrintedPages:
    """resolve_printed_pages stamping, skips, and outside-page preservation."""

    def test_out_of_range_footer_skipped_returns_zero(self) -> None:
        docs = [
            _nav_chunk(88, 50000),  # out of range -> ValueError -> continue
            _nav_chunk(89, 79),
            _nav_chunk(90, 80),
        ]
        assert fast_text.resolve_printed_pages(docs) == 0

    def test_fewer_than_three_footer_pages_returns_zero(self) -> None:
        docs = [_nav_chunk(88, 78), _nav_chunk(89, 79)]
        assert fast_text.resolve_printed_pages(docs) == 0

    def test_inconsistent_offsets_return_zero(self) -> None:
        docs = [
            _nav_chunk(88, 78),
            _nav_chunk(89, 79),
            _nav_chunk(90, 12),  # offset 78 vs 10 elsewhere
        ]
        assert fast_text.resolve_printed_pages(docs) == 0

    def test_consistent_footers_stamp_all_covered_pages(self) -> None:
        docs = [
            _body_chunk(88, "chapter prose", printed=500),
            _nav_chunk(88, 78),
            _body_chunk(89, "more prose", printed=501),
            _nav_chunk(89, 79),
            _nav_chunk(90, 80),
        ]

        stamped = fast_text.resolve_printed_pages(docs)

        assert stamped == 3
        by_page = {d["page_number"]: d["printed_page"] for d in docs}
        assert by_page[88] == 78
        assert by_page[89] == 79
        assert by_page[90] == 80

    def test_pages_outside_footer_coverage_keep_bracket_stamps(self) -> None:
        docs = [
            _nav_chunk(88, 78),
            _nav_chunk(89, 79),
            _nav_chunk(90, 80),
            _body_chunk(20, "uncovered page", printed=777),
        ]

        stamped = fast_text.resolve_printed_pages(docs)

        assert stamped == 3
        uncovered = [d for d in docs if d["page_number"] == 20]
        assert uncovered[0]["printed_page"] == 777

    def test_matching_bracket_stamps_not_rewritten(self) -> None:
        """printed_page already equal to the resolved stamp is left as-is."""
        docs = [
            _body_chunk(88, "prose", printed=78),
            _nav_chunk(88, 78),
            _nav_chunk(89, 79),
            _nav_chunk(90, 80),
        ]

        stamped = fast_text.resolve_printed_pages(docs)

        assert stamped == 3
        body = next(d for d in docs if d["element_type"] == "body")
        assert body["printed_page"] == 78


class _FakeTextPage:
    def __init__(self, text: str, fail: bool = False) -> None:
        self._text = text
        self._fail = fail
        self.closed = 0

    def get_text_range(self) -> str:
        if self._fail:
            raise RuntimeError("text range exploded")
        return self._text

    def close(self) -> None:
        self.closed += 1


class _FakePage:
    def __init__(self, text: str, fail: bool = False) -> None:
        self._textpage = _FakeTextPage(text, fail)

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
        self.opened: list[str] = []

    def PdfDocument(self, path: str) -> _FakePdf:  # noqa: N802 - mirrors pypdfium2 API
        self.opened.append(path)
        if self._pdf._fail_open:
            raise RuntimeError("corrupt pdf")
        return self._pdf


class TestExtractNativePdfText:
    """extract_native_pdf_text with a mocked pypdfium2 module."""

    def _inject(self, monkeypatch: pytest.MonkeyPatch, pdfium: Any) -> None:
        import types

        mod: Any = types.ModuleType("pypdfium2")
        mod.PdfDocument = pdfium.PdfDocument
        monkeypatch.setitem(sys.modules, "pypdfium2", mod)

    def test_happy_path_skips_blank_pages_and_closes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf(
            [
                _FakePage("first page text"),
                _FakePage("   \n  "),  # blank -> skipped
                _FakePage("third page text"),
            ]
        )
        self._inject(monkeypatch, _FakePdfium(pdf))

        result = fast_text.extract_native_pdf_text(tmp_path / "book.pdf")

        assert result == [
            {"text": "first page text", "page": 1},
            {"text": "third page text", "page": 3},
        ]
        assert pdf.closed == 1
        assert all(
            tp.closed == 1
            for tp in (
                pdf[0].get_textpage(),
                pdf[1].get_textpage(),
                pdf[2].get_textpage(),
            )
        )

    def test_text_range_failure_returns_empty_and_closes_textpage(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pdf = _FakePdf([_FakePage("irrelevant", fail=True)])
        self._inject(monkeypatch, _FakePdfium(pdf))

        result = fast_text.extract_native_pdf_text(tmp_path / "book.pdf")

        assert result == []
        assert pdf.closed == 1

    def test_open_failure_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._inject(monkeypatch, _FakePdfium(_FakePdf([], fail_open=True)))

        assert fast_text.extract_native_pdf_text(tmp_path / "bad.pdf") == []

    def test_pypdfium2_import_failure_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setitem(sys.modules, "pypdfium2", None)  # import raises

        assert fast_text.extract_native_pdf_text(tmp_path / "any.pdf") == []

    def test_empty_pdf_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        self._inject(monkeypatch, _FakePdfium(_FakePdf([])))

        assert fast_text.extract_native_pdf_text(tmp_path / "empty.pdf") == []
