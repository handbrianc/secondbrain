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
- native text insufficient -> ``None`` (fall through to docling).

No real docling / pypdfium2 inference and no real MongoDB are used. Docling is
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
    PDF_FAST_TEXT_MIN_CHARS,
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

    def __init__(self, *, fast_text: bool = False, ocr: bool = False) -> None:
        self.pdf_fast_text_enabled = fast_text
        self.pdf_ocr_enabled = ocr
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

    def _set(*, fast_text: bool = False, ocr: bool = False) -> _FakeCfg:
        cfg = _FakeCfg(fast_text=fast_text, ocr=ocr)
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
