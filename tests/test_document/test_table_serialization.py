"""Tests for row-oriented table serialization (openspec fix-summary-fidelity, D4).

Covers the pure core of ``table_serialize`` (row grouping, serialization
format, row-alignment check, flat fallback), the docling adapter
(``table_run_plan`` — cell attribution, caption exclusion, grid handling,
placeholder rejection, never-raises containment) and the segment interleave
in ``processor._extend_segments_from_document``.

All docling documents in these tests are plain ``SimpleNamespace`` fakes
shaped like docling 2.139 objects: text items carry ``text`` and ``prov``
(``page_no``, top-left-origin ``bbox`` with ``l/t/r/b`` attributes), regions
are table items with ``prov``/``data``. The real docling conversion path was
verified separately against the corpus page (PVE admin guide page 409).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from secondbrain.document.processor import _extend_segments_from_document
from secondbrain.document.table_serialize import (
    CELL_SEPARATOR,
    TABLE_LABEL,
    TableCell,
    TableRun,
    append_table_segment,
    build_table_run,
    group_cells_into_rows,
    row_alignment_holds,
    serialize_rows,
    table_run_plan,
)


def _box(left: float, top: float, right: float, bottom: float) -> SimpleNamespace:
    """Build a flat top-left-origin box (no ``to_top_left_origin``)."""
    # Attribute names l/t/r/b mirror docling's BoundingBox so the adapter's
    # attribute reads apply unchanged.
    return SimpleNamespace(l=float(left), t=float(top), r=float(right), b=float(bottom))


def _tbox(
    left: float, top: float, right: float, bottom: float
) -> tuple[float, float, float, float]:
    """Build a top-left-origin bbox tuple for the pure-core functions."""
    return (left, top, right, bottom)


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
    page_no: int = 1,
    box: SimpleNamespace | None = None,
    num_rows: int = 1,
    num_cols: int = 1,
) -> SimpleNamespace:
    """Build a fake docling table-region item with a placeholder grid."""
    return SimpleNamespace(
        prov=[
            SimpleNamespace(
                page_no=page_no, bbox=box if box is not None else _box(0, 0, 10, 10)
            )
        ],
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


def _cells_for_page409() -> list[SimpleNamespace]:
    """The 14 in-region text items of the corpus page (PVE guide page 409).

    Real texts and scaled top-left geometry: two columns, seven row bands.
    """
    rows = [
        ("Availability %", "Downtime per year"),
        ("99", "3.65 days"),
        ("99.9", "8.76 hours"),
        ("99.99", "52.56 minutes"),
        ("99.999", "5.26 minutes"),
        ("99.9999", "31.5 seconds"),
        ("99.99999", "3.15 seconds"),
    ]
    items = []
    for index, (label, value) in enumerate(rows):
        top = 100.0 + index * 20.0
        items.append(_text_item(label, box=_box(50, top, 150, top + 10)))
        items.append(_text_item(value, box=_box(200, top, 350, top + 10)))
    return items


def _page409_region() -> SimpleNamespace:
    """A placeholder-grid table region covering the page-409 cell band."""
    return _table_item(box=_box(40, 90, 360, 245))


class TestGroupCellsIntoRows:
    def test_groups_by_vertical_overlap_top_to_bottom(self) -> None:
        cells = [
            TableCell(text="a", bbox=_tbox(0, 100, 50, 110), order=0),
            TableCell(text="b", bbox=_tbox(60, 100, 120, 110), order=1),
            TableCell(text="c", bbox=_tbox(0, 200, 50, 210), order=2),
            TableCell(text="d", bbox=_tbox(60, 200, 120, 210), order=3),
        ]
        rows = group_cells_into_rows(cells)
        assert rows == ((0, 1), (2, 3))

    def test_orders_cells_left_to_right_within_row(self) -> None:
        # Stream order reversed within a row: grouping must still read
        # left-to-right.
        cells = [
            TableCell(text="right", bbox=_tbox(60, 100, 120, 110), order=0),
            TableCell(text="left", bbox=_tbox(0, 100, 50, 110), order=1),
        ]
        rows = group_cells_into_rows(cells)
        assert rows == ((1, 0),)

    def test_rows_ordered_top_to_bottom(self) -> None:
        # Stream order bottom row first: rows must come out top-to-bottom.
        cells = [
            TableCell(text="bottom", bbox=_tbox(0, 200, 50, 210), order=0),
            TableCell(text="top", bbox=_tbox(0, 100, 50, 110), order=1),
        ]
        rows = group_cells_into_rows(cells)
        assert rows == ((1,), (0,))

    def test_returns_none_when_any_cell_lacks_bbox(self) -> None:
        cells = [
            TableCell(text="a", bbox=_box(0, 100, 50, 110), order=0),
            TableCell(text="b", bbox=None, order=1),
        ]
        assert group_cells_into_rows(cells) is None

    def test_returns_none_for_empty_cells(self) -> None:
        assert group_cells_into_rows([]) is None


class TestSerializeRows:
    def test_one_line_per_row_cells_joined_by_separator(self) -> None:
        assert serialize_rows([("a", "b"), ("c",)]) == f"a{CELL_SEPARATOR}b\nc"

    def test_empty_rows_serialize_to_empty_string(self) -> None:
        assert serialize_rows([]) == ""

    def test_separator_is_the_design_example_form(self) -> None:
        # D4: one line per row, e.g. "99.999% — 5.26 minutes".
        assert serialize_rows([("99.999", "5.26 minutes")]) == "99.999 — 5.26 minutes"


class TestRowAlignmentHolds:
    def _row_major_cells(self) -> list[TableCell]:
        return [
            TableCell(text="r0a", bbox=_tbox(0, 100, 50, 110), order=0),
            TableCell(text="r0b", bbox=_tbox(60, 100, 120, 110), order=1),
            TableCell(text="r1a", bbox=_tbox(0, 200, 50, 210), order=2),
            TableCell(text="r1b", bbox=_tbox(60, 200, 120, 210), order=3),
        ]

    def test_row_major_stream_holds(self) -> None:
        cells = self._row_major_cells()
        rows = group_cells_into_rows(cells)
        assert rows is not None
        assert row_alignment_holds(cells, rows) is True

    def test_row_blocks_out_of_order_fails(self) -> None:
        cells = [
            TableCell(text="r1a", bbox=_tbox(0, 200, 50, 210), order=0),
            TableCell(text="r1b", bbox=_tbox(60, 200, 120, 210), order=1),
            TableCell(text="r0a", bbox=_tbox(0, 100, 50, 110), order=2),
            TableCell(text="r0b", bbox=_tbox(60, 100, 120, 110), order=3),
        ]
        rows = group_cells_into_rows(cells)
        assert rows is not None
        assert row_alignment_holds(cells, rows) is False

    def test_within_row_order_does_not_fail(self) -> None:
        # Same-row cells swapped: within-row order is not constrained.
        cells = [
            TableCell(text="r0b", bbox=_tbox(60, 100, 120, 110), order=0),
            TableCell(text="r0a", bbox=_tbox(0, 100, 50, 110), order=1),
        ]
        rows = group_cells_into_rows(cells)
        assert rows is not None
        assert row_alignment_holds(cells, rows) is True

    def test_grouping_not_covering_every_cell_fails(self) -> None:
        cells = self._row_major_cells()
        assert row_alignment_holds(cells, ((0, 1),)) is False


class TestBuildTableRun:
    def test_aligned_row_oriented_run(self) -> None:
        cells = [
            TableCell(text="99.999", bbox=_tbox(0, 100, 50, 110), order=0),
            TableCell(text="5.26 minutes", bbox=_tbox(60, 100, 120, 110), order=1),
            TableCell(text="99.9999", bbox=_tbox(0, 200, 50, 210), order=2),
            TableCell(text="31.5 seconds", bbox=_tbox(60, 200, 120, 210), order=3),
        ]
        run = build_table_run(cells, page=7, first_index=0, last_index=3)
        assert run.text == "99.999 — 5.26 minutes\n99.9999 — 31.5 seconds"
        assert run.rows == (
            ("99.999", "5.26 minutes"),
            ("99.9999", "31.5 seconds"),
        )
        assert run.aligned is True
        assert (run.page, run.first_index, run.last_index) == (7, 0, 3)

    def test_missing_geometry_falls_back_to_flat_flagged_run(self) -> None:
        cells = [
            TableCell(text="99.999", bbox=None, order=0),
            TableCell(text="5.26 minutes", bbox=None, order=1),
        ]
        run = build_table_run(cells, page=1, first_index=0, last_index=1)
        # Historical degenerate form, but information-preserving and flagged.
        assert run.text == "99.999 5.26 minutes"
        assert run.rows == ()
        assert run.aligned is False

    def test_misordered_stream_keeps_rows_but_flags(self) -> None:
        cells = [
            TableCell(text="r1a", bbox=_tbox(0, 200, 50, 210), order=0),
            TableCell(text="r1b", bbox=_tbox(60, 200, 120, 210), order=1),
            TableCell(text="r0a", bbox=_tbox(0, 100, 50, 110), order=2),
            TableCell(text="r0b", bbox=_tbox(60, 100, 120, 110), order=3),
        ]
        run = build_table_run(cells, page=1, first_index=0, last_index=3)
        # Same-row cells stay together (rows reconstructed from geometry);
        # the degenerate stream order only sets the flag.
        assert run.text == "r0a — r0b\nr1a — r1b"
        assert run.aligned is False


class TestAppendTableSegment:
    def test_aligned_run_appends_unflagged_table_segment(self) -> None:
        segments: list[dict] = []
        run = TableRun(
            text="a — b",
            page=3,
            rows=(("a", "b"),),
            aligned=True,
            first_index=0,
            last_index=1,
        )
        append_table_segment(segments, run)
        assert segments == [{"text": "a — b", "page": 3, "label": TABLE_LABEL}]

    def test_unaligned_run_appends_flagged_table_segment(self) -> None:
        segments: list[dict] = []
        run = TableRun(
            text="a b",
            page=3,
            rows=(),
            aligned=False,
            first_index=0,
            last_index=1,
        )
        append_table_segment(segments, run)
        assert segments == [
            {
                "text": "a b",
                "page": 3,
                "label": TABLE_LABEL,
                "table_degenerate": True,
            }
        ]


class TestTableRunPlan:
    def test_cells_inside_region_consumed_into_one_run(self) -> None:
        texts = _cells_for_page409()
        doc = _page_doc(texts, [_page409_region()])
        plan = table_run_plan(doc)
        assert len(plan.anchored) == 1
        assert len(plan.floating) == 0
        run = plan.anchored[0]
        assert run.aligned is True
        assert run.page == 1
        assert run.first_index == 0
        assert run.last_index == 13
        assert plan.consumed == frozenset(range(14))
        assert plan.start_index[0] is run
        assert run.rows == (
            ("Availability %", "Downtime per year"),
            ("99", "3.65 days"),
            ("99.9", "8.76 hours"),
            ("99.99", "52.56 minutes"),
            ("99.999", "5.26 minutes"),
            ("99.9999", "31.5 seconds"),
            ("99.99999", "3.15 seconds"),
        )
        assert run.text.startswith("Availability % — Downtime per year\n99 — 3.65 days")

    def test_items_outside_region_stay_unconsumed(self) -> None:
        prose = _text_item("Surrounding prose paragraph.", box=_box(0, 500, 400, 600))
        texts = [prose, *_cells_for_page409()]
        doc = _page_doc(texts, [_page409_region()])
        plan = table_run_plan(doc)
        assert plan.consumed == frozenset(range(1, 15))
        assert plan.anchored[0].first_index == 1

    def test_caption_and_heading_roles_are_not_cells(self) -> None:
        caption = _text_item(
            "Table 15.1: Availability",
            box=_box(50, 80, 350, 90),
            label="caption",
        )
        heading = _text_item(
            "High Availability",
            box=_box(50, 85, 350, 95),
            label="section_header",
        )
        cells = _cells_for_page409()
        doc = _page_doc([caption, heading, *cells], [_page409_region()])
        plan = table_run_plan(doc)
        # The caption/heading texts are neither consumed nor present in rows.
        assert plan.consumed == frozenset(range(2, 16))
        flat = plan.anchored[0].text
        assert "Table 15.1" not in flat
        assert "High Availability" not in flat

    def test_other_page_items_never_absorbed(self) -> None:
        cells = _cells_for_page409()
        stranger = _text_item(
            "page 2 body text", page_no=2, box=_box(50, 100, 350, 110)
        )
        doc = _page_doc([*cells, stranger], [_page409_region()])
        doc.pages[2] = SimpleNamespace(size=SimpleNamespace(height=800.0))
        plan = table_run_plan(doc)
        assert 14 not in plan.consumed
        assert len(plan.anchored) == 1

    def test_real_grid_serialized_directly(self) -> None:
        region = _table_item(box=_box(40, 90, 360, 245), num_rows=2, num_cols=2)
        region.export_to_dataframe = lambda doc=None: pd.DataFrame(
            {"Name": ["a", "c"], "Value": ["b", "d"]}
        )
        cells = [
            _text_item("a", box=_box(50, 100, 150, 110)),
            _text_item("b", box=_box(200, 100, 350, 110)),
            _text_item("c", box=_box(50, 200, 150, 210)),
            _text_item("d", box=_box(200, 200, 350, 210)),
        ]
        doc = _page_doc(cells, [region])
        plan = table_run_plan(doc)
        assert len(plan.anchored) == 1
        run = plan.anchored[0]
        # Header columns kept (non-numeric labels); grid rows in docling order.
        assert run.rows == (("Name", "Value"), ("a", "b"), ("c", "d"))
        assert run.aligned is True
        assert run.first_index == 0
        assert run.last_index == 3

    def test_placeholder_grid_rejected_in_favor_of_geometry(self) -> None:
        # Structure-OFF parse: 1x1 placeholder grid must NOT replace the real
        # cells (verified failure shape on the corpus page before the fix).
        region = _page409_region()
        doc = _page_doc(_cells_for_page409(), [region])
        plan = table_run_plan(doc)
        run = plan.anchored[0]
        assert run.rows[0] == ("Availability %", "Downtime per year")
        assert "rich cell" not in run.text

    def test_grid_only_region_is_a_floating_run(self) -> None:
        region = _table_item(box=_box(40, 90, 360, 245), num_rows=2, num_cols=2)
        region.export_to_dataframe = lambda doc=None: pd.DataFrame(
            {"Name": ["a"], "Value": ["b"]}
        )
        prose = _text_item("Prose outside the table.", box=_box(0, 500, 400, 600))
        doc = _page_doc([prose], [region])
        plan = table_run_plan(doc)
        assert plan.anchored == ()
        assert len(plan.floating) == 1
        assert plan.floating[0].first_index == -1
        assert plan.consumed == frozenset()

    def test_empty_or_foreign_documents_yield_empty_plan(self) -> None:
        empty = table_run_plan(_page_doc([], []))
        assert empty.anchored == ()
        assert empty.floating == ()
        assert empty.consumed == frozenset()
        # No texts/tables at all (object without attributes).
        assert table_run_plan(object()).consumed == frozenset()
        assert table_run_plan(object()).anchored == ()

    def test_doc_without_pages_metadata_still_plans_flat_boxes(self) -> None:
        # Flat boxes without to_top_left_origin do not need page metadata.
        texts = _cells_for_page409()
        doc = SimpleNamespace(texts=texts, tables=[_page409_region()])
        plan = table_run_plan(doc)
        assert len(plan.anchored) == 1
        assert plan.anchored[0].aligned is True

    def test_raise_inside_document_read_is_contained(self) -> None:
        class _Boom:
            texts: tuple = ()

            @property
            def tables(self) -> list:
                raise RuntimeError("unreadable document")

        plan = table_run_plan(_Boom(), file_path=None)
        assert plan.anchored == ()
        assert plan.consumed == frozenset()

    def test_magic_mock_document_yields_empty_plan(self) -> None:
        plan = table_run_plan(MagicMock())
        assert plan.anchored == ()
        assert plan.floating == ()
        assert plan.consumed == frozenset()

    def test_unaligned_run_logs_info_record(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Bottom row block streamed first: misordered cells -> INFO record
        # (diagnostic; the durable signal is the table_degenerate flag on the
        # chunk, which stays visible at the CLI's WARNING console level).
        cells = [
            TableCell(text="r1a", bbox=_box(0, 200, 50, 210), order=0),
            TableCell(text="r1b", bbox=_box(60, 200, 120, 210), order=1),
            TableCell(text="r0a", bbox=_box(0, 100, 50, 110), order=2),
            TableCell(text="r0b", bbox=_box(60, 100, 120, 110), order=3),
        ]
        items = [_text_item(cell.text, box=cell.bbox) for cell in cells]
        region = _table_item(box=_box(0, 90, 130, 220))
        doc = _page_doc(items, [region])
        with caplog.at_level(
            logging.INFO, logger="secondbrain.document.table_serialize"
        ):
            plan = table_run_plan(doc, file_path=None)
        assert plan.anchored[0].aligned is False
        assert any(
            record.levelno == logging.INFO and "table_degenerate" in record.message
            for record in caplog.records
        )
        # No WARNING-or-higher record from this logger for a flagged run.
        assert not any(
            record.name == "secondbrain.document.table_serialize"
            and record.levelno >= logging.WARNING
            for record in caplog.records
        )


class TestExtendSegmentsFromDocument:
    def test_table_segment_replaces_consumed_cells_in_place(self) -> None:
        prose_before = _text_item("Intro paragraph.", box=_box(0, 20, 400, 40))
        prose_after = _text_item("Closing paragraph.", box=_box(0, 500, 400, 600))
        texts = [prose_before, *_cells_for_page409(), prose_after]
        doc = _page_doc(texts, [_page409_region()])
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        assert len(segments) == 3
        assert segments[0]["text"] == "Intro paragraph."
        table_segment = segments[1]
        assert table_segment["label"] == TABLE_LABEL
        assert table_segment["page"] == 1
        assert "table_degenerate" not in table_segment
        assert table_segment["text"].startswith("Availability % — Downtime per year")
        assert segments[2]["text"] == "Closing paragraph."

    def test_degenerate_run_flags_its_segment(self) -> None:
        cells = [
            TableCell(text="r1a", bbox=_box(0, 200, 50, 210), order=0),
            TableCell(text="r1b", bbox=_box(60, 200, 120, 210), order=1),
            TableCell(text="r0a", bbox=_box(0, 100, 50, 110), order=2),
            TableCell(text="r0b", bbox=_box(60, 100, 120, 110), order=3),
        ]
        items = [_text_item(cell.text, box=cell.bbox) for cell in cells]
        region = _table_item(box=_box(0, 90, 130, 220))
        doc = _page_doc(items, [region])
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        assert len(segments) == 1
        assert segments[0]["table_degenerate"] is True
        assert segments[0]["label"] == TABLE_LABEL

    def test_grid_only_region_appends_floating_segment_last(self) -> None:
        region = _table_item(box=_box(40, 90, 360, 245), num_rows=2, num_cols=2)
        region.export_to_dataframe = lambda doc=None: pd.DataFrame(
            {"Name": ["a"], "Value": ["b"]}
        )
        prose = _text_item("Prose outside the table.", box=_box(0, 500, 400, 600))
        doc = _page_doc([prose], [region])
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        assert [s.get("label") for s in segments] == [None, TABLE_LABEL]
        assert segments[1]["text"] == "Name — Value\na — b"

    def test_no_texts_grid_only_document_still_serializes(self) -> None:
        region = _table_item(box=_box(40, 90, 360, 245), num_rows=2, num_cols=2)
        region.export_to_dataframe = lambda doc=None: pd.DataFrame(
            {"Name": ["a"], "Value": ["b"]}
        )
        doc = _page_doc([], [region])
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        assert len(segments) == 1
        assert segments[0]["label"] == TABLE_LABEL
        assert segments[0]["text"] == "Name — Value\na — b"

    def test_document_without_tables_passes_items_through(self) -> None:
        texts = [
            _text_item("First.", box=_box(0, 20, 400, 40)),
            _text_item("Second.", box=_box(0, 60, 400, 80)),
        ]
        doc = _page_doc(texts)
        segments: list[dict] = []
        _extend_segments_from_document(doc, segments, file_path=None)
        assert [s["text"] for s in segments] == ["First.", "Second."]
        assert all("label" not in s for s in segments)
