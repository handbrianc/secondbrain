"""Tests for table-aware chunking (openspec fix-summary-fidelity, D4).

Covers the chunker's table contract — row-boundary-only splits, whole-row
overlap, standalone flush, ``table_degenerate`` flag propagation, the
oversized-single-row word-boundary fallback — plus a synthetic regression of
the real corpus page (PVE admin guide page 409) and the worker-level flag
propagation into stored documents.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from secondbrain.document.chunker import (
    chunk_segments,
    deduplicate_segments,
)
from secondbrain.document.processor import (
    _extend_segments_from_document,
    _extract_chunk_and_embed_file,
)
from secondbrain.document.table_serialize import (
    TABLE_LABEL,
    table_run_plan,
)

# The page-409 degenerate pairing recorded in the change proposal.
_DEGENERATE_PAIRING = "5.26 minutes 99.9999"


def _box(left: float, top: float, right: float, bottom: float) -> SimpleNamespace:
    """Build a flat top-left-origin box (no ``to_top_left_origin``)."""
    # Attribute names l/t/r/b mirror docling's BoundingBox so the adapter's
    # attribute reads apply unchanged.
    return SimpleNamespace(l=float(left), t=float(top), r=float(right), b=float(bottom))


def _text_item(
    text: str,
    page_no: int = 1,
    box: SimpleNamespace | None = None,
    label: str | None = None,
) -> SimpleNamespace:
    """Build a fake docling text item with one provenance entry."""
    prov = SimpleNamespace(
        page_no=page_no, bbox=box if box is not None else _box(0, 0, 10, 10)
    )
    item = SimpleNamespace(text=text, prov=[prov])
    if label is not None:
        item.label = label
    return item


def _table_item(
    box: SimpleNamespace, num_rows: int = 1, num_cols: int = 1
) -> SimpleNamespace:
    """Build a fake docling table-region item with a placeholder grid."""
    return SimpleNamespace(
        prov=[SimpleNamespace(page_no=1, bbox=box)],
        data=SimpleNamespace(
            num_rows=num_rows, num_cols=num_cols, grid=[[]] * num_rows
        ),
    )


def _page_doc(texts: list, tables: list | None = None) -> SimpleNamespace:
    """Build a fake docling document for page 1."""
    return SimpleNamespace(
        texts=texts,
        tables=tables if tables is not None else [],
        pages={1: SimpleNamespace(size=SimpleNamespace(height=800.0))},
    )


def _rows(count: int) -> list[str]:
    """Build ``count`` complete row lines (~27 characters each)."""
    return [f"row {i:02d} label — row {i:02d} value" for i in range(count)]


def _table_segment(text: str, **extra: object) -> dict[str, object]:
    """A standalone table segment dict as the serializer appends it."""
    segment: dict[str, object] = {"text": text, "page": 1, "label": TABLE_LABEL}
    segment.update(extra)
    return segment


class TestRowBoundarySplits:
    def test_splits_only_at_row_boundaries(self) -> None:
        text = "\n".join(_rows(20))
        chunks = chunk_segments(
            [_table_segment(text)], chunk_size=120, chunk_overlap=50
        )
        assert len(chunks) > 1
        for chunk in chunks:
            lines = chunk["text"].splitlines()
            # Every line is a complete row: label and value stay together.
            assert all(" — " in line for line in lines), chunk["text"]

    def test_label_and_value_never_in_different_chunks(self) -> None:
        rows = [
            "99 — 3.65 days",
            "99.9 — 8.76 hours",
            "99.99 — 52.56 minutes",
            "99.999 — 5.26 minutes",
            "99.9999 — 31.5 seconds",
        ]
        # Tiny chunk size forces several splits; each pairing must stay whole
        # (the overlap may legitimately repeat a row across chunks).
        chunks = chunk_segments(
            [_table_segment("\n".join(rows))], chunk_size=45, chunk_overlap=20
        )
        assert len(chunks) > 1
        for pairing in rows:
            assert any(pairing in c["text"] for c in chunks), pairing

    def test_overlap_repeats_whole_rows_only(self) -> None:
        text = "\n".join(_rows(20))
        chunks = chunk_segments(
            [_table_segment(text)], chunk_size=120, chunk_overlap=50
        )
        for previous, current in pairwise(chunks):
            first_line = current["text"].splitlines()[0]
            assert first_line in previous["text"].splitlines()

    def test_oversized_single_row_falls_back_to_word_split(self) -> None:
        # One row far longer than the chunk size: no row boundary is
        # available inside the window; the loop must still advance.
        text = " ".join(f"word{i}" for i in range(150))
        chunks = chunk_segments(
            [_table_segment(text)], chunk_size=120, chunk_overlap=20
        )
        assert len(chunks) > 1
        assert all(chunk["text"].strip() for chunk in chunks)

    def test_table_segment_flushes_standalone(self) -> None:
        prose = (
            "Prose paragraph one. " * 20,
            "Prose paragraph two. " * 20,
        )
        segments = [
            {"text": prose[0], "page": 1},
            _table_segment("a — b\nc — d"),
            {"text": prose[1], "page": 1},
        ]
        chunks = chunk_segments(segments, chunk_size=200, chunk_overlap=20)
        table_chunks = [c for c in chunks if " — " in c["text"]]
        body_chunks = [c for c in chunks if " — " not in c["text"]]
        assert len(table_chunks) == 1
        assert table_chunks[0]["text"] == "a — b\nc — d"
        assert all("a — b" not in c["text"] for c in body_chunks)

    def test_table_chunks_keep_body_element_type(self) -> None:
        chunks = chunk_segments(
            [_table_segment("a — b")], chunk_size=200, chunk_overlap=20
        )
        assert chunks[0]["element_type"] == "body"
        assert chunks[0]["chunk_role"] == "body"


class TestFlagPropagation:
    def test_flagged_segment_flags_all_its_chunks(self) -> None:
        text = "\n".join(_rows(20))
        chunks = chunk_segments(
            [_table_segment(text, table_degenerate=True)],
            chunk_size=120,
            chunk_overlap=50,
        )
        assert len(chunks) > 1
        assert all(c["table_degenerate"] is True for c in chunks)

    def test_well_formed_segment_carries_no_flag(self) -> None:
        text = "\n".join(_rows(20))
        chunks = chunk_segments(
            [_table_segment(text)], chunk_size=120, chunk_overlap=50
        )
        assert all("table_degenerate" not in c for c in chunks)

    def test_flag_does_not_leak_into_other_segments(self) -> None:
        segments = [
            {"text": "Prose paragraph. " * 20, "page": 1},
            _table_segment("a — b", table_degenerate=True),
            {"text": "More prose. " * 20, "page": 1},
        ]
        chunks = chunk_segments(segments, chunk_size=200, chunk_overlap=20)
        flagged = [c for c in chunks if c.get("table_degenerate") is True]
        assert len(flagged) == 1
        assert flagged[0]["text"] == "a — b"

    def test_deduplicate_segments_keeps_flag_and_time_spans(self) -> None:
        segments = [
            {
                "text": "a — b",
                "page": 3,
                "label": TABLE_LABEL,
                "table_degenerate": True,
                "t_start": 1.5,
                "t_end": 4.0,
            }
        ]
        out = deduplicate_segments(Path("doc.pdf"), segments)
        assert len(out) == 1
        assert out[0]["table_degenerate"] is True
        assert out[0]["t_start"] == 1.5
        assert out[0]["t_end"] == 4.0


class TestPage409Regression:
    """Synthetic replay of the corpus page (PVE admin guide page 409).

    The real conversion (project converter, structure OFF) produces 26 text
    items and one placeholder-grid table region; the 14 in-region cells read
    row-major. This fixture mirrors the geometry and texts.
    """

    @staticmethod
    def _document() -> SimpleNamespace:
        rows = [
            ("Availability %", "Downtime per year"),
            ("99", "3.65 days"),
            ("99.9", "8.76 hours"),
            ("99.99", "52.56 minutes"),
            ("99.999", "5.26 minutes"),
            ("99.9999", "31.5 seconds"),
            ("99.99999", "3.15 seconds"),
        ]
        prose_boxes = [
            _box(0, 780, 500, 810),  # footer: "Proxmox VE ... 387 / 634"
            _box(0, 20, 600, 80),  # paragraphs above the table
            _box(0, 300, 600, 400),  # list items below the table
        ]
        texts = [
            _text_item("Proxmox VE Administration Guide", box=prose_boxes[0]),
            _text_item("387 / 634", box=prose_boxes[0]),
            _text_item(
                "Our modern society depends heavily on the availability of "
                "services and computer systems.",
                box=prose_boxes[1],
            ),
            _text_item("Table 15.1: Availability - Downtime per year", label="caption"),
            *(
                item
                for index, (label, value) in enumerate(rows)
                for item in (
                    _text_item(
                        label,
                        box=_box(50, 100.0 + index * 20.0, 150, 110.0 + index * 20.0),
                    ),
                    _text_item(
                        value,
                        box=_box(200, 100.0 + index * 20.0, 350, 110.0 + index * 20.0),
                    ),
                )
            ),
            _text_item(
                "There are several ways to increase availability.", box=prose_boxes[2]
            ),
        ]
        region = _table_item(box=_box(40, 90, 360, 245))
        return _page_doc(texts, [region])

    def test_rows_serialize_with_label_and_value_together(self) -> None:
        doc = self._document()
        plan = table_run_plan(doc)
        assert len(plan.anchored) == 1
        run = plan.anchored[0]
        assert run.aligned is True
        assert run.rows == (
            ("Availability %", "Downtime per year"),
            ("99", "3.65 days"),
            ("99.9", "8.76 hours"),
            ("99.99", "52.56 minutes"),
            ("99.999", "5.26 minutes"),
            ("99.9999", "31.5 seconds"),
            ("99.99999", "3.15 seconds"),
        )

    def test_no_chunk_pairs_value_with_next_rows_label(self) -> None:
        doc = self._document()
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        for chunk_size, chunk_overlap in ((120, 50), (60, 20), (45, 10)):
            chunks = chunk_segments(segments, chunk_size, chunk_overlap)
            assert not any(_DEGENERATE_PAIRING in c["text"] for c in chunks), (
                chunk_size,
                [c["text"] for c in chunks if _DEGENERATE_PAIRING in c["text"]],
            )
            paired = [c for c in chunks if "99.999 — 5.26 minutes" in c["text"]]
            assert len(paired) >= 1, chunk_size
            # Every row-bearing chunk holds complete rows only: no line is a
            # bare label or a bare value (that is the degenerate shape).
            for chunk in chunks:
                if " — " in chunk["text"]:
                    assert all(" — " in line for line in chunk["text"].splitlines())

    def test_degenerate_variant_flags_instead_of_storing_silently(self) -> None:
        doc = self._document()
        # Reverse the in-region stream (indices 4..17: the 14 table cells),
        # bottom row block first: the row-alignment check must fail and flag
        # the chunk.
        in_region = list(range(4, 18))
        doc.texts = [doc.texts[i] for i in in_region[::-1]] + [
            item for i, item in enumerate(doc.texts) if i not in in_region
        ]
        plan = table_run_plan(doc)
        assert plan.anchored[0].aligned is False
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        chunks = chunk_segments(segments, 120, 50)
        flagged = [c for c in chunks if c.get("table_degenerate") is True]
        assert flagged
        assert all(" — " in c["text"] for c in flagged)


class _CountingEmbeddingModel:
    def __init__(self) -> None:
        self.calls = 0
        self.embed_texts: list[str] = []

    def generate_batch(self, texts):
        self.calls += 1
        self.embed_texts.extend(texts)
        return [[0.1] * 4 for _ in texts]


class _Result:
    def __init__(self, document) -> None:
        self.document = document


class _FakeConverter:
    def __init__(self, document) -> None:
        self._document = document

    def convert(self, file_path):
        return _Result(self._document)


def _worker_setup(
    monkeypatch, tmp_path: Path, document: SimpleNamespace
) -> tuple[_CountingEmbeddingModel, Path]:
    monkeypatch.setattr(
        "secondbrain.document.docling_factory.get_converter_for_path",
        lambda _p: _FakeConverter(document),
    )
    model = _CountingEmbeddingModel()
    monkeypatch.setattr(
        "secondbrain.embedding.EmbeddingProviderFactory.create_from_config",
        lambda _cfg: model,
    )
    mock_cfg = MagicMock()
    mock_cfg.embedding_model = "test-model"
    mock_cfg.embedding_batch_size = 100
    mock_cfg.skip_existing_on_reingest = False
    monkeypatch.setattr("secondbrain.config.config", lambda: mock_cfg)
    file_path = tmp_path / "sample.txt"
    file_path.write_text("body", encoding="utf-8")
    return model, file_path


def _worker_document(*, degenerate: bool) -> SimpleNamespace:
    """A fake docling document with one prose item and one small table."""
    rows = [("r0a", "r0b"), ("r1a", "r1b")]
    items: list[SimpleNamespace] = []
    for index, (label, value) in enumerate(rows):
        # Geometry is fixed per row (top-left origin: row 0 is highest).
        top = 100.0 + index * 20.0
        items.append(_text_item(label, box=_box(50, top, 150, top + 10)))
        items.append(_text_item(value, box=_box(200, top, 350, top + 10)))
    if degenerate:
        # Stream the row blocks bottom-up (row 1 first): out of row order,
        # so the row-alignment check fails while the geometry stays valid.
        items = items[2:] + items[:2]
    texts = [
        _text_item("Intro prose paragraph. " * 10, box=_box(0, 20, 400, 40)),
        *items,
    ]
    region = _table_item(box=_box(40, 90, 360, 145))
    return _page_doc(texts, [region])


class TestWorkerFlagPropagation:
    def test_degenerate_table_reaches_stored_documents_flagged(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        _model, file_path = _worker_setup(
            monkeypatch, tmp_path, _worker_document(degenerate=True)
        )
        result = _extract_chunk_and_embed_file(
            str(file_path),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )
        assert result["success"] is True
        flagged = [d for d in result["documents"] if d.get("table_degenerate") is True]
        assert len(flagged) == 1
        assert flagged[0]["chunk_text"] == "r0a — r0b\nr1a — r1b"

    def test_well_formed_table_stores_unflagged_row_text(
        self, monkeypatch, tmp_path: Path
    ) -> None:
        _model, file_path = _worker_setup(
            monkeypatch, tmp_path, _worker_document(degenerate=False)
        )
        result = _extract_chunk_and_embed_file(
            str(file_path),
            chunk_size=512,
            chunk_overlap=50,
            progress_queue=None,
            embedding_model_name="test-model",
            skip_existing=False,
        )
        assert result["success"] is True
        table_docs = [d for d in result["documents"] if " — " in d["chunk_text"]]
        assert len(table_docs) == 1
        assert table_docs[0]["chunk_text"] == "r0a — r0b\nr1a — r1b"
        assert all("table_degenerate" not in d for d in result["documents"])
