"""Tests for the fast native-text PDF extraction pipeline.

Covers :func:`secondbrain.document.fast_text.try_fast_pdf_extraction` routing
and the wiring of the fast path into the extraction sites
(:func:`secondbrain.document.processor.convert_file_to_segments` and
:class:`secondbrain.document.ingestor._sync.DocumentIngestor._extract_text`).

The contract under test:

- non-PDF input -> ``None`` (never fast);
- ``pdf_fast_text_enabled=False`` -> ``None`` (feature off);
- ``pdf_ocr_enabled=True`` -> ``None`` (OCR explicitly requested, do not bypass);
- native text sufficient (>= ``PDF_FAST_TEXT_MIN_CHARS`` non-whitespace chars)
  -> fast segments with correct page numbers, docling NOT invoked;
- book-structure markers in the leading pages (structure probe on) -> ``None``
  (text-layer books route through docling to capture per-item labels);
- native text insufficient -> ``None`` (fall through to docling).

No real docling / pypdfium2 inference and no live vector store is used. Docling is
stubbed by the ``tests/test_document/conftest.py`` session fixture, the native
text source is monkeypatched, and config is driven via a fake ``config()``
(matching the ``test_ocr_on_demand.py`` idiom).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secondbrain.document import docling_factory, fast_text
from secondbrain.document.fast_text import (
    PDF_FAST_TEXT_CORRUPTION_RATIO,
    PDF_FAST_TEXT_MIN_CHARS,
    _looks_corrupted,
    _looks_like_structured_book,
    extract_printed_page,
    try_fast_pdf_extraction,
)
from secondbrain.document.ingestor._sync import DocumentIngestor
from secondbrain.document.processor import convert_file_to_segments

_LONG_TEXT = "native text layer content " * 30  # > PDF_FAST_TEXT_MIN_CHARS


class _FakeCfg:
    """Minimal stand-in for the Config object's PDF fast-text/OCR fields.

    Mirrors the field set ``docling_factory`` reads when it builds its
    converters (plus the fast-text/OCR flags under test), so instantiating a
    ``DocumentIngestor`` (which eagerly builds a shared converter) works.
    """

    def __init__(
        self,
        *,
        fast_text: bool = False,
        ocr: bool = False,
        structure_probe: bool = True,
    ) -> None:
        self.pdf_fast_text_enabled = fast_text
        self.pdf_ocr_enabled = ocr
        self.pdf_structure_probe_enabled = structure_probe
        self.pdf_table_structure_enabled = False
        self.pdf_table_fast_mode = True
        self.pdf_table_cell_matching = False
        self.pdf_accelerator_device = "auto"
        self.pdf_num_threads = 4
        self.pdf_threaded_pipeline = False
        self.pdf_layout_batch_size = 4
        self.pdf_generate_page_images = False
        self.pdf_generate_picture_images = False
        self.pdf_images_scale = 1.0


@pytest.fixture
def fake_config(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the resolved config to control the fast-text flags."""

    def _set(
        *,
        fast_text: bool = False,
        ocr: bool = False,
        structure_probe: bool = True,
    ) -> _FakeCfg:
        cfg = _FakeCfg(fast_text=fast_text, ocr=ocr, structure_probe=structure_probe)
        monkeypatch.setattr("secondbrain.config.config", lambda: cfg)
        return cfg

    return _set


def _pdf(tmp_path: Path) -> Path:
    """A real (but empty) PDF path that the fast path would open."""
    path = tmp_path / "native.pdf"
    path.write_bytes(b"%PDF-1.4 minimal")
    return path


# ---------------------------------------------------------------------------
# try_fast_pdf_extraction routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.fast
def test_extract_printed_page() -> None:
    """Prints the bracketed printed-page marker, or None when absent."""
    assert extract_printed_page("[ 500 ]\r\nSome page content") == 500
    assert extract_printed_page("Chapter 15\r\n[ 471 ]\r\nFigure 15.6") == 471
    assert extract_printed_page("plain text with no marker") is None
    assert extract_printed_page("") is None


@pytest.mark.unit
@pytest.mark.fast
def test_non_pdf_never_fast(fake_config, tmp_path: Path) -> None:
    """A non-PDF extension returns None even with the feature enabled."""
    fake_config(fast_text=True, ocr=False)
    txt = tmp_path / "notes.txt"
    txt.write_text(_LONG_TEXT)
    assert try_fast_pdf_extraction(txt) is None


@pytest.mark.unit
@pytest.mark.fast
def test_feature_disabled_returns_none(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """pdf_fast_text_enabled=False -> None (feature off)."""
    fake_config(fast_text=False, ocr=False)
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: [{"text": _LONG_TEXT, "page": 1}],
    )
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None


@pytest.mark.unit
@pytest.mark.fast
def test_ocr_forced_returns_none(fake_config, monkeypatch, tmp_path: Path) -> None:
    """pdf_ocr_enabled=True -> None even when native text is sufficient."""
    fake_config(fast_text=True, ocr=True)
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: [{"text": _LONG_TEXT, "page": 1}],
    )
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None


@pytest.mark.unit
@pytest.mark.fast
def test_sufficient_native_text_returns_segments(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Sufficient text -> segments with correct pages; extraction called once."""
    fake_config(fast_text=True, ocr=False)
    calls: list[Path] = []
    segments = [
        {"text": "page one " * 40, "page": 1},
        {"text": "page two " * 40, "page": 2},
    ]

    def fake_extract(path: Path) -> list[dict[str, object]]:
        calls.append(path)
        return segments

    monkeypatch.setattr(fast_text, "extract_native_pdf_text", fake_extract)

    result = try_fast_pdf_extraction(_pdf(tmp_path))

    assert result == segments
    assert calls == [_pdf(tmp_path)]


@pytest.mark.unit
@pytest.mark.fast
def test_insufficient_text_returns_none(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Below PDF_FAST_TEXT_MIN_CHARS non-whitespace chars -> None."""
    fake_config(fast_text=True, ocr=False)
    monkeypatch.setattr(fast_text, "extract_native_pdf_text", lambda p: [])
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None

    short = "x" * (PDF_FAST_TEXT_MIN_CHARS - 1)
    monkeypatch.setattr(
        fast_text, "extract_native_pdf_text", lambda p: [{"text": short, "page": 1}]
    )
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None


# ---------------------------------------------------------------------------
# Corruption detector (_looks_corrupted) + routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_clean_ascii_is_false() -> None:
    """Plain ASCII prose is never flagged as corrupted."""
    assert (
        _looks_corrupted("The quick brown fox jumps over the lazy dog. " * 10) is False
    )


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_empty_is_false() -> None:
    """Empty/whitespace-only input is not corrupted."""
    assert _looks_corrupted("") is False
    assert _looks_corrupted("   \n\t  ") is False


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_legit_unicode_is_false() -> None:
    """Legit math/typographic glyphs are not flagged (no false positives)."""
    legit = ("régime naïve überstraße " * 20) + (
        "a \u00d7 b \u00b1 c \u00b2 \u00b3 \u00b9 " * 20
    )
    assert _looks_corrupted(legit) is False


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_fffd_is_true() -> None:
    """A page riddled with the Unicode replacement char is corrupted."""
    text = ("good prose " * 20) + ("\ufffd" * 30)
    assert _looks_corrupted(text) is True


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_c1_controls_is_true() -> None:
    """C1 control chars (the mojibake fingerprint) flag the text as corrupted."""
    text = "clean text " * 20 + "\x80\x93\x94".join("mojibake" for _ in range(30))
    assert _looks_corrupted(text) is True


@pytest.mark.unit
@pytest.mark.fast
def test_looks_corrupted_below_threshold_is_false() -> None:
    """A spurious single suspicious char stays below the ratio threshold."""
    total_needed = int(1 / PDF_FAST_TEXT_CORRUPTION_RATIO) + 1
    text = ("clean " * total_needed) + "\ufffd"
    assert _looks_corrupted(text) is False


@pytest.mark.unit
@pytest.mark.fast
def test_corrupted_native_text_returns_none(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Fast text that trips _looks_corrupted -> None (route to docling/OCR)."""
    fake_config(fast_text=True, ocr=False)
    corrupted_segments = [
        {"text": "clean page one " * 40, "page": 1},
        {"text": ("garbled " * 10) + ("\ufffd" * 40), "page": 2},
    ]
    monkeypatch.setattr(
        fast_text, "extract_native_pdf_text", lambda p: corrupted_segments
    )
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None


# ---------------------------------------------------------------------------
# Structure probe (_looks_like_structured_book) + routing
# ---------------------------------------------------------------------------


def _book_segments() -> list[dict[str, object]]:
    """Text-layer book: a dotted ToC page plus chapter-opener pages."""
    toc = "\n".join(f"Chapter {n}  Topic {n} ....... {100 + n}" for n in range(1, 6))
    return [
        {"text": toc, "page": 1},
        {"text": f"Chapter 1\nFirst Topic\n\n{'body prose ' * 40}", "page": 2},
        {"text": f"Chapter 2\nSecond Topic\n\n{'body prose ' * 40}", "page": 3},
    ]


@pytest.mark.unit
@pytest.mark.fast
def test_probe_toc_only_is_true() -> None:
    """Three or more dotted ToC entries classify the text as a book."""
    toc = "\n".join(f"Intro Topic ....... {n}" for n in range(1, 4))
    assert _looks_like_structured_book([{"text": toc, "page": 1}]) is True


@pytest.mark.unit
@pytest.mark.fast
def test_probe_chapter_openers_only_is_true() -> None:
    """Two or more line-start chapter openers classify the text as a book."""
    text = "Chapter 1\nAlpha\n\nChapter 2\nBeta\n\nfiller prose"
    assert _looks_like_structured_book([{"text": text, "page": 1}]) is True


@pytest.mark.unit
@pytest.mark.fast
def test_probe_single_mention_is_false() -> None:
    """A lone chapter cross-reference or one dotted line is not a book."""
    assert (
        _looks_like_structured_book(
            [{"text": "as discussed in Chapter 3 earlier " * 10, "page": 1}]
        )
        is False
    )
    assert (
        _looks_like_structured_book(
            [{"text": "some title ....... 12\n" + ("prose " * 60), "page": 1}]
        )
        is False
    )


@pytest.mark.unit
@pytest.mark.fast
def test_probe_plain_prose_is_false() -> None:
    """Ordinary prose never trips the probe."""
    assert _looks_like_structured_book([{"text": _LONG_TEXT, "page": 1}]) is False


@pytest.mark.unit
@pytest.mark.fast
def test_probe_ignores_beyond_leading_pages() -> None:
    """Markers past PDF_STRUCTURE_PROBE_MAX_PAGES pages do not classify."""
    segments: list[dict[str, object]] = [
        {"text": _LONG_TEXT, "page": n} for n in range(1, 41)
    ]
    segments.append({"text": "Chapter 1\nAlpha\n\nChapter 2\nBeta", "page": 41})
    assert _looks_like_structured_book(segments) is False


@pytest.mark.unit
@pytest.mark.fast
def test_structured_book_routes_to_docling(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """A text-layer book returns None so the caller falls through to docling."""
    fake_config(fast_text=True, ocr=False)
    monkeypatch.setattr(
        fast_text, "extract_native_pdf_text", lambda p: _book_segments()
    )
    assert try_fast_pdf_extraction(_pdf(tmp_path)) is None


@pytest.mark.unit
@pytest.mark.fast
def test_structure_probe_disabled_keeps_fast_path(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Probe off -> even book-like text stays on the fast path."""
    fake_config(fast_text=True, ocr=False, structure_probe=False)
    segments = _book_segments()
    monkeypatch.setattr(fast_text, "extract_native_pdf_text", lambda p: segments)
    assert try_fast_pdf_extraction(_pdf(tmp_path)) == segments


# ---------------------------------------------------------------------------
# Site-level wiring: processor.convert_file_to_segments
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_convert_file_to_segments_fast_path_skips_docling(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Fast returns segments -> docling converter never created."""
    fake_config(fast_text=True, ocr=False)
    fast_segments = [
        {"text": "fast page one " * 40, "page": 1},
        {"text": "fast page two " * 40, "page": 2},
    ]
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: fast_segments,
    )
    # If the fast path fails to short-circuit, docling would be constructed.
    monkeypatch.setattr(
        "secondbrain.document.processor.create_converter",
        lambda p: (_ for _ in ()).throw(
            AssertionError("docling converter should not be created")
        ),
    )

    result = convert_file_to_segments(_pdf(tmp_path))

    assert result == fast_segments


@pytest.mark.unit
def test_convert_file_to_segments_falls_back_to_docling(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Fast returns None -> unchanged docling path yields its segments."""
    fake_config(fast_text=False, ocr=False)  # feature off -> fast returns None
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: (_ for _ in ()).throw(
            AssertionError("native extraction should not run when disabled")
        ),
    )

    item = MagicMock()
    item.text = "docling extraction output"
    item.prov = [MagicMock(page_no=3)]
    result_doc = MagicMock(texts=[item])
    result = MagicMock(document=result_doc)
    converter = MagicMock()
    converter.convert = MagicMock(return_value=result)
    monkeypatch.setattr(
        "secondbrain.document.processor.create_converter", lambda p: converter
    )

    out = convert_file_to_segments(_pdf(tmp_path))

    assert out == [{"text": "docling extraction output", "page": 3}]
    converter.convert.assert_called_once()


# ---------------------------------------------------------------------------
# Site-level wiring: ingestor._sync._extract_text
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sync_extract_text_fast_path_returns_segments(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Fast returns segments -> docling resolver never reached."""
    fake_config(fast_text=True, ocr=False)
    fast_segments = [{"text": "fast page one " * 40, "page": 1}]
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: fast_segments,
    )
    monkeypatch.setattr(
        docling_factory,
        "get_converter_for_path",
        lambda p: (_ for _ in ()).throw(
            AssertionError("docling resolver should not be reached")
        ),
    )

    ingestor = DocumentIngestor()
    out = ingestor._extract_text(_pdf(tmp_path))

    assert out == fast_segments


@pytest.mark.unit
def test_sync_extract_text_falls_back_to_docling(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Fast returns None -> unchanged docling path yields its segments."""
    fake_config(fast_text=False, ocr=False)  # feature off -> fast returns None
    monkeypatch.setattr(
        fast_text,
        "extract_native_pdf_text",
        lambda p: (_ for _ in ()).throw(
            AssertionError("native extraction should not run when disabled")
        ),
    )

    item = MagicMock(text="docling sync output")
    del item.export_to_data_frame
    item.prov = [MagicMock(page_no=1)]
    result_doc = MagicMock(texts=[item])
    result = MagicMock(document=result_doc)
    converter = MagicMock()
    converter.convert = MagicMock(return_value=result)
    monkeypatch.setattr(docling_factory, "get_converter_for_path", lambda p: converter)

    ingestor = DocumentIngestor()
    out = ingestor._extract_text(_pdf(tmp_path))

    assert out == [{"text": "docling sync output", "page": 1}]
    converter.convert.assert_called_once()
