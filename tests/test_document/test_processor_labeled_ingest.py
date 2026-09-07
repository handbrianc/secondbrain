"""Label propagation through processor extraction and the chunk-embed worker."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from secondbrain.document.processor import (
    _extract_chunk_and_embed_file,
    convert_file_to_segments,
)

LONG_BODY = (
    "The Internet of Things connects physical devices to cloud platforms, "
    "enabling telemetry collection at scale across fleets of heterogeneous "
    "sensors and gateways that report telemetry continuously."
)


class _FakeCfg:
    def __init__(self, *, fast_text: bool, ocr: bool) -> None:
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
        self.embedding_batch_size = 16
        self.skip_existing_on_reingest = False


@pytest.fixture
def fake_config(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch the resolved config to control the fast-text flags."""

    def _set(*, fast_text: bool = False, ocr: bool = False) -> _FakeCfg:
        cfg = _FakeCfg(fast_text=fast_text, ocr=ocr)
        monkeypatch.setattr("secondbrain.config.config", lambda: cfg)
        return cfg

    return _set


def _converter_with(items: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(
        convert=lambda path: SimpleNamespace(document=SimpleNamespace(texts=items))
    )


def _labeled_items() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            text="1 Principles of IoT and AI",
            prov=[SimpleNamespace(page_no=1)],
            label=SimpleNamespace(value="section_header"),
        ),
        SimpleNamespace(
            text=LONG_BODY,
            prov=[SimpleNamespace(page_no=1)],
            label=SimpleNamespace(value="text"),
        ),
        SimpleNamespace(
            text="12",
            prov=[SimpleNamespace(page_no=1)],
            label=SimpleNamespace(value="page_footer"),
        ),
    ]


def _patch_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "secondbrain.embedding.EmbeddingProviderFactory.create_from_config",
        lambda cfg: SimpleNamespace(
            generate_batch=lambda texts: [[0.1] * 4 for _ in texts]
        ),
    )


@pytest.mark.unit
def test_convert_file_to_segments_carries_docling_labels(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Docling items expose their label on the extracted segment."""
    fake_config(fast_text=False, ocr=False)
    monkeypatch.setattr(
        "secondbrain.document.processor.create_converter",
        lambda p: _converter_with(_labeled_items()),
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    segments = convert_file_to_segments(pdf)

    assert segments[0] == {
        "text": "1 Principles of IoT and AI",
        "page": 1,
        "label": "section_header",
    }
    assert segments[1] == {"text": LONG_BODY, "page": 1, "label": "text"}


@pytest.mark.unit
def test_extract_chunk_and_embed_labels_heading_chunks(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Labeled headings/footers survive as standalone chunks with both keys."""
    fake_config(fast_text=False, ocr=False)
    _patch_embedding(monkeypatch)
    monkeypatch.setattr(
        "secondbrain.document.docling_factory.get_converter_for_path",
        lambda p: _converter_with(_labeled_items()),
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    result = _extract_chunk_and_embed_file(
        str(pdf),
        4096,
        200,
        progress_queue=None,
        embedding_model_name="test-model",
        embedding_cache=None,
        skip_existing=False,
    )

    assert result["success"] is True
    docs = result["documents"]
    assert docs
    for doc in docs:
        assert doc["element_type"] == doc["chunk_role"]
    heading_docs = [d for d in docs if d["chunk_role"] == "heading"]
    assert len(heading_docs) == 1
    assert heading_docs[0]["chunk_text"] == "1 Principles of IoT and AI"
    assert any(d["chunk_role"] == "navigation" for d in docs)
    assert any(d["chunk_role"] == "body" for d in docs)


@pytest.mark.unit
def test_extract_chunk_and_embed_label_less_yields_no_heading(
    fake_config, monkeypatch, tmp_path: Path
) -> None:
    """Without labels the legacy behavior holds: titles never become chunks."""
    fake_config(fast_text=False, ocr=False)
    _patch_embedding(monkeypatch)
    items = [
        SimpleNamespace(
            text="1 Principles of IoT and AI", prov=[SimpleNamespace(page_no=1)]
        ),
        SimpleNamespace(text=LONG_BODY, prov=[SimpleNamespace(page_no=1)]),
        SimpleNamespace(text="12", prov=[SimpleNamespace(page_no=1)]),
    ]
    monkeypatch.setattr(
        "secondbrain.document.docling_factory.get_converter_for_path",
        lambda p: _converter_with(items),
    )
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    result = _extract_chunk_and_embed_file(
        str(pdf),
        4096,
        200,
        progress_queue=None,
        embedding_model_name="test-model",
        embedding_cache=None,
        skip_existing=False,
    )

    assert result["success"] is True
    docs = result["documents"]
    assert docs
    assert not any(d["chunk_role"] == "heading" for d in docs)
    assert all(d["element_type"] == d["chunk_role"] for d in docs)
