"""Row-oriented table serialization for ingest (fix-summary-fidelity, D4).

Where table content becomes chunk text (verified on the corrupted corpus):
with the project's default PDF configuration (``pdf_table_structure_enabled``
is False) docling still recovers table *regions* — ``DoclingDocument.tables``
carries one region item per detected table — but emits each table cell as a
plain text item in ``DoclingDocument.texts``, in row-major reading order. The
extraction loops iterate ``texts`` only, so cells reach the chunker as
ordinary body segments; the merge policy then glues adjacent cells across row
boundaries (``"5.26 minutes"`` + ``"99.9999"`` — the next row's label) and the
chunker splits the run freely, producing the degenerate pairing recorded in
the change proposal (stored chunk text ``"5.26 minutes 99.9999"``).

This module closes that gap in three steps:

1. **Row-oriented serialization** — cells attributed to a table region are
   grouped into rows by bounding-box geometry and serialized one line per
   row, cells joined by ``" — "`` (``"99.999% — 5.26 minutes"``), so a value
   always stays on the same line as its own row label/header.
2. **Row-boundary chunk splits** — a table is emitted as ONE segment labeled
   ``"table"``; ``chunker.chunk_segments`` splits table-labeled segments only
   at row boundaries (newlines), so a row's label and value never land in
   different chunks.
3. **Alignment check + flag** — the source cell stream must read in row order
   (row indices non-decreasing along the stream). When it does not, or when
   rows cannot be reconstructed at all (no cell geometry), the run is marked
   unaligned: its chunks carry a ``table_degenerate`` metadata flag (the
   durable, machine-readable signal) and the module logs a diagnostic INFO
   record. The INFO level keeps the record out of the CLI console flow by
   default (the console handler runs at WARNING) while the full text is still
   stored; re-enable diagnostics with ``secondbrain --verbose`` or
   ``SECONDBRAIN_LOG_LEVEL`` (honored by ``setup_logging``). A misordered
   stream keeps its reconstructed rows (same-row cells stay together);
   unreconstructable geometry falls back to a flat cell line
   (information-preserving).

The pure core (:func:`group_cells_into_rows`, :func:`serialize_rows`,
:func:`row_alignment_holds`, :func:`build_table_run`) is geometry-only and
docling-free. :func:`table_run_plan` is the docling adapter; it never raises
— a document it cannot read keeps the historical pass-through behavior.
When the docling document was parsed with table structure ENABLED and the
region item carries a recovered grid, the grid rows (docling's own row order)
are serialized directly instead of the geometric reconstruction.

Exports:
    CELL_SEPARATOR: Joiner between a row's cells (" — ").
    TABLE_LABEL: Segment label marking a serialized table run ("table").
    TABLE_ROW_OVERLAP_RATIO: Vertical-overlap fraction binding cells to a row.
    TABLE_REGION_SLACK: Relative growth of a region box for cell attribution.
    TableCell: One source cell (text, top-left bbox, stream position).
    TableRun: A serialized table (text, rows, page, alignment verdict, span).
    TableRunPlan: Anchored/floating runs plus consumed text-item indices.
    group_cells_into_rows: Geometry-only row grouping (indices per row).
    serialize_rows: One line per row, cells joined by CELL_SEPARATOR.
    row_alignment_holds: Whether the source stream reads rows in order.
    build_table_run: Group + serialize + align-check (with flat fallback).
    table_run_plan: Docling document adapter. Never raises.
    append_table_segment: Append a run as a standalone "table" segment.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from secondbrain.document.chunker import docling_item_label, label_to_element_type

logger = logging.getLogger(__name__)

# Design D4 example: one line per row, e.g. "99.999% — 5.26 minutes".
CELL_SEPARATOR = " — "

# Segment label marking a serialized table run. It is also a raw docling item
# label (chunker._LABEL_TO_ELEMENT_TYPE maps it to "body"), so table chunks
# keep the historical "body" element_type while the chunker treats the
# segment as standalone and splits it only at row boundaries.
TABLE_LABEL = "table"

# Fraction of the smaller cell's height two cells' vertical spans must share
# to count as one table row (design "Open Questions": calibration value).
TABLE_ROW_OVERLAP_RATIO = 0.5

# Relative growth of a table region box before attributing cell items to it
# (layout-model bbox slack; design "Open Questions": calibration value).
TABLE_REGION_SLACK = 0.05


@dataclass(frozen=True)
class TableCell:
    """One source table cell as read from the document text-item stream.

    Attributes
    ----------
    text : str
        The cell text (stripped, non-empty).
    bbox : tuple[float, float, float, float] | None
        Bounding box in top-left page coordinates ``(l, t, r, b)``; None when
        the source item carries no usable geometry.
    order : int
        The cell's position in the source text-item stream.
    """

    text: str
    bbox: tuple[float, float, float, float] | None
    order: int


@dataclass(frozen=True)
class TableRun:
    """A serialized table: row-oriented text plus its alignment verdict.

    Attributes
    ----------
    text : str
        The serialized table text (one line per row when aligned; a flat cell
        line when the row-alignment check failed).
    page : int
        The 1-based page the table region sits on.
    rows : tuple[tuple[str, ...], ...]
        The serialized rows (cell texts per row); empty for the flat fallback.
    aligned : bool
        Whether the run passed the row-alignment check. False runs must be
        flagged (``table_degenerate``) on the chunks they produce.
    first_index : int
        Index in the document text-item stream of the first consumed cell,
        anchoring the run's position in the segment stream; -1 for runs with
        no cell anchor (grid-only regions).
    last_index : int
        Index of the last consumed cell (inclusive); -1 when unanchored.
    """

    text: str
    page: int
    rows: tuple[tuple[str, ...], ...]
    aligned: bool
    first_index: int
    last_index: int


@dataclass(frozen=True)
class TableRunPlan:
    """Table runs of one document, keyed for interleaving into a segment list.

    Attributes
    ----------
    anchored : tuple[TableRun, ...]
        Runs anchored at a consumed cell range (``first_index >= 0``); they
        replace the consumed cell items at their stream position.
    floating : tuple[TableRun, ...]
        Runs with no cell anchor (grid-only regions); they are appended after
        the text items.
    start_index : dict[int, TableRun]
        Anchored runs keyed by their first consumed cell index.
    consumed : frozenset[int]
        Every text-item index absorbed into a run; callers must skip these
        items when emitting per-item segments.
    """

    anchored: tuple[TableRun, ...] = ()
    floating: tuple[TableRun, ...] = ()
    start_index: dict[int, TableRun] = field(default_factory=dict)
    consumed: frozenset[int] = frozenset()


def _vertical_overlap_ratio(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Return the vertical overlap of two boxes over the smaller box's height.

    Parameters
    ----------
    a, b : tuple[float, float, float, float]
        Top-left origin boxes ``(l, t, r, b)``.

    Returns
    -------
        Overlap height divided by the smaller box's height; 0.0 when the
        boxes do not overlap vertically or a height is non-positive.
    """
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    if overlap <= 0:
        return 0.0
    height_a = a[3] - a[1]
    height_b = b[3] - b[1]
    smaller = min(height_a, height_b)
    if smaller <= 0:
        return 0.0
    return overlap / smaller


def group_cells_into_rows(
    cells: Sequence[TableCell],
) -> tuple[tuple[int, ...], ...] | None:
    """Group cells into rows by bounding-box geometry.

    Clusters cells whose vertical spans overlap by at least
    :data:`TABLE_ROW_OVERLAP_RATIO` of the smaller cell's height, orders rows
    top-to-bottom, and orders cells within each row left-to-right.

    Parameters
    ----------
    cells : Sequence[TableCell]
        Source cells in stream order; every cell must carry a bbox.

    Returns
    -------
        One tuple of cell indices per row (rows top-to-bottom, cells
        left-to-right), or None when any cell lacks geometry or no row can
        be formed.
    """
    if not cells or any(cell.bbox is None for cell in cells):
        return None

    def _top(index: int) -> float:
        box = cells[index].bbox
        assert box is not None  # nosec B101 - filtered above
        return box[1]

    ordered = sorted(range(len(cells)), key=_top)
    rows: list[list[int]] = []
    for index in ordered:
        box = cells[index].bbox
        assert box is not None  # nosec B101 - filtered above
        placed = False
        for row in rows:
            # Same row iff the cell's vertical span overlaps at least one
            # member's span by the binding ratio (member-wise, so one tall
            # cell cannot grow a union span that swallows the next row).
            for member in row:
                member_box = cells[member].bbox
                assert member_box is not None  # nosec B101 - filtered above
                if _vertical_overlap_ratio(box, member_box) >= TABLE_ROW_OVERLAP_RATIO:
                    row.append(index)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            rows.append([index])

    rows.sort(key=lambda row: min(_top(i) for i in row))
    for row in rows:
        row.sort(key=lambda i: (cells[i].bbox[0], cells[i].order))  # type: ignore[index]
    return tuple(tuple(row) for row in rows)


def serialize_rows(rows: Sequence[Sequence[str]]) -> str:
    """Serialize rows one line each, cells joined by :data:`CELL_SEPARATOR`.

    Parameters
    ----------
    rows : Sequence[Sequence[str]]
        Cell texts per row, rows in table order.

    Returns
    -------
        Newline-joined row lines; empty string when there are no rows.
    """
    return "\n".join(CELL_SEPARATOR.join(row) for row in rows)


def row_alignment_holds(
    cells: Sequence[TableCell],
    row_members: Sequence[Sequence[int]],
) -> bool:
    """Return whether the source stream reads the table's rows in order.

    The row-alignment invariant (spec: "cells out of source order relative to
    their rows"): every cell is placed in exactly one row, and the row index
    never decreases along the source stream — each row's cells appear
    contiguously, rows in source row order. Within-row cell order is not
    constrained (same-row cells always stay together in the serialization).

    Parameters
    ----------
    cells : Sequence[TableCell]
        Source cells in stream order.
    row_members : Sequence[Sequence[int]]
        Cell indices per row (as produced by :func:`group_cells_into_rows`).

    Returns
    -------
        True when the stream reads rows in order (well-formed table), False
        when cells read out of row order (degenerate extraction) or the
        grouping does not cover every cell exactly once.
    """
    row_of: dict[int, int] = {}
    for row_index, members in enumerate(row_members):
        for cell_index in members:
            if cell_index in row_of:
                return False
            row_of[cell_index] = row_index
    if len(row_of) != len(cells):
        return False

    stream = sorted(range(len(cells)), key=lambda i: cells[i].order)
    previous = 0
    for index in stream:
        if row_of[index] < previous:
            return False
        previous = row_of[index]
    return True


def build_table_run(
    cells: Sequence[TableCell],
    *,
    page: int,
    first_index: int,
    last_index: int,
) -> TableRun:
    """Serialize one table's cells into a row-oriented (or flat) run.

    Groups the cells into rows, serializes one line per row, and runs the
    row-alignment check. When rows cannot be reconstructed (missing
    geometry), the cells are serialized as a flat space-joined line — the
    historical degenerate form — and the run is marked unaligned so the
    affected chunks get flagged.

    Parameters
    ----------
    cells : Sequence[TableCell]
        The table's cells in source stream order.
    page : int
        The table's 1-based page number.
    first_index, last_index : int
        The cell stream range the run replaces.

    Returns
    -------
        The serialized :class:`TableRun` (``aligned=False`` runs must be
        flagged and logged at INFO — diagnostic only — by the caller).
    """
    row_members = group_cells_into_rows(cells)
    if row_members is None:
        flat = " ".join(cell.text for cell in cells)
        return TableRun(
            text=flat,
            page=page,
            rows=(),
            aligned=False,
            first_index=first_index,
            last_index=last_index,
        )
    rows = tuple(
        tuple(cells[index].text for index in members) for members in row_members
    )
    return TableRun(
        text=serialize_rows(rows),
        page=page,
        rows=rows,
        aligned=row_alignment_holds(cells, row_members),
        first_index=first_index,
        last_index=last_index,
    )


def append_table_segment(segments: list[Any], run: TableRun) -> None:
    """Append *run* to *segments* as a standalone table segment.

    The segment carries the ``"table"`` label (the chunker flushes it
    standalone and splits it only at row boundaries) and, for unaligned
    runs, the ``table_degenerate`` flag that the ingest paths propagate into
    the stored chunk metadata.

    Parameters
    ----------
    segments : list[Any]
        The segment list being assembled by an extraction site.
    run : TableRun
        The serialized table run.
    """
    segment: dict[str, Any] = {
        "text": run.text,
        "page": run.page,
        "label": TABLE_LABEL,
    }
    if not run.aligned:
        segment["table_degenerate"] = True
    segments.append(segment)


def _cell_str(value: Any) -> str:
    """Format one grid cell value as text; pandas NaN becomes empty."""
    if isinstance(value, float) and value != value:
        return ""
    return str(value)


def _grid_rows(table_item: Any, doc: Any) -> tuple[tuple[str, ...], ...] | None:
    """Return a table item's recovered grid rows, or None when grid-less.

    Reads docling's recovered table grid (``TableItem.export_to_dataframe``,
    populated only when table structure parsing produced data) into cell-text
    rows. A structure-OFF parse leaves a placeholder 1x1 grid whose one cell
    carries the table's whole raw text (verified against the corpus page:
    ``data.num_rows == 1 and data.num_cols == 1`` and
    ``export_to_dataframe`` returns a 1x1 frame) — that placeholder is
    rejected so the caller falls back to the geometric reconstruction of the
    region's cell items. The header row is kept only when the frame carries
    real (non numeric) column labels. Any failure returns None.
    """
    try:
        data = getattr(table_item, "data", None)
        if data is not None:
            num_rows = int(getattr(data, "num_rows", 0) or 0)
            num_cols = int(getattr(data, "num_cols", 0) or 0)
            if num_rows <= 1 and num_cols <= 1:
                return None
        if not hasattr(table_item, "export_to_dataframe"):
            return None
        try:
            frame = table_item.export_to_dataframe(doc=doc)
        except TypeError:
            # Older docling-core without the doc parameter.
            frame = table_item.export_to_dataframe()
        rows = [
            [_cell_str(cell) for cell in row]
            for row in frame.itertuples(index=False, name=None)
        ]
        header = [str(column) for column in frame.columns]
        if header and not any(column.isdigit() for column in header):
            rows.insert(0, header)
        usable = tuple(tuple(row) for row in rows if any(cell.strip() for cell in row))
        return usable or None
    except Exception:  # adapter must never raise
        return None


@dataclass(frozen=True)
class _Region:
    """A docling table region to fill from the text-item stream.

    Attributes
    ----------
    page : int
        The region's 1-based page number.
    bbox : tuple[float, float, float, float]
        The region box in top-left page coordinates.
    grid : tuple[tuple[str, ...], ...] | None
        The region's recovered grid rows (structure-enabled parses), or None.
    """

    page: int
    bbox: tuple[float, float, float, float]
    grid: tuple[tuple[str, ...], ...] | None = None


def _item_box(
    item: Any, doc: Any
) -> tuple[int, tuple[float, float, float, float]] | None:
    """Return an item's (page, top-left bbox), or None when unavailable.

    Parameters
    ----------
    item : Any
        A docling text item; its first provenance entry carries page and bbox.
    doc : Any
        The owning docling document (page metadata for coordinate conversion).

    Returns
    -------
        ``(page_no, (l, t, r, b))`` in top-left coordinates, or None when the
        item, its provenance, its bbox, or the page metadata is unusable.
    """
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    entry = prov[0]
    page_no = getattr(entry, "page_no", None)
    bbox = getattr(entry, "bbox", None)
    if page_no is None or bbox is None:
        return None
    to_top_left = getattr(bbox, "to_top_left_origin", None)
    if callable(to_top_left):
        # Real docling bounding boxes are in bottom-left page coordinates and
        # always carry the origin-aware conversion; without page metadata the
        # box cannot be converted reliably, so the item stays unusable.
        try:
            page_height = float(doc.pages[int(page_no)].size.height)
            top_left = to_top_left(page_height)
        except Exception:  # adapter must never raise
            return None
    else:
        # Flat/synthetic boxes (tests, mocks) without the method are taken as
        # already top-left coordinates; attribute access below still validates
        # the box shape.
        top_left = bbox
    try:
        box = (
            float(top_left.l),
            float(top_left.t),
            float(top_left.r),
            float(top_left.b),
        )
    except Exception:  # adapter must never raise
        return None
    return int(page_no), box


def _grown(
    box: tuple[float, float, float, float], ratio: float
) -> tuple[float, float, float, float]:
    """Grow a box by *ratio* of its extent on every side."""
    left, top, right, bottom = box
    grow_x = (right - left) * ratio
    grow_y = (bottom - top) * ratio
    return (left - grow_x, top - grow_y, right + grow_x, bottom + grow_y)


def table_run_plan(doc: Any, *, file_path: Path | None = None) -> TableRunPlan:
    """Extract row-oriented table runs from a docling document.

    For every table region in ``doc.tables`` (a region exists even when
    table-structure parsing is off — it just carries no grid), the text items
    whose bounding-box center falls inside the region on the same page are
    consumed as that table's cells and serialized row by row. Regions with a
    recovered grid (structure-enabled parses) serialize the grid rows
    directly and still consume their in-region cell items. Unaligned runs
    (cells out of row order, or no reconstructable geometry) are serialized
    as a flat cell line and logged at INFO — a diagnostic record (default-
    suppressed by the CLI's WARNING console level); the chunks themselves
    carry the durable ``table_degenerate`` flag.

    Never raises: a document the adapter cannot read yields an empty plan and
    the caller keeps the historical per-item pass-through behavior.

    Parameters
    ----------
    doc : Any
        A docling ``DoclingDocument`` (``result.document``) or any object.
    file_path : Path | None
        Source file path for the warning log line, when known.

    Returns
    -------
        The :class:`TableRunPlan` for interleaving (see the extraction sites
        in ``processor.py`` / ``ingestor/_sync.py``).
    """
    try:
        return _build_table_run_plan(doc, file_path=file_path)
    except Exception as e:  # adapter must never raise
        logger.debug(
            "Table-run extraction failed (%s: %s); table cells pass through "
            "unchunked-structure",
            type(e).__name__,
            e,
        )
        return TableRunPlan()


def _build_table_run_plan(doc: Any, file_path: Path | None = None) -> TableRunPlan:
    """Body of :func:`table_run_plan` (exceptions are contained by the caller).

    ``file_path`` is used only for the degenerate-table log record's context.
    """
    tables = getattr(doc, "tables", None) or []
    texts = getattr(doc, "texts", None) or []
    if not tables:
        # No table regions: nothing to serialize (the caller keeps the
        # historical per-item pass-through).
        return TableRunPlan()

    regions: list[_Region] = []
    for table_item in tables:
        located = _item_box(table_item, doc)
        if located is None:
            continue
        page_no, box = located
        regions.append(
            _Region(page=page_no, bbox=box, grid=_grid_rows(table_item, doc))
        )
    if not regions:
        return TableRunPlan()

    cells_per_region: list[list[TableCell]] = [[] for _ in regions]
    consumed: set[int] = set()
    for index, item in enumerate(texts):
        text = getattr(item, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        # Captions, headings and other labeled roles are not table cells:
        # only body-mapped (or unlabeled) items may be absorbed by a region.
        role = label_to_element_type(docling_item_label(item))
        if role not in (None, "body"):
            continue
        located = _item_box(item, doc)
        if located is None:
            continue
        page_no, box = located
        center_x = (box[0] + box[2]) / 2
        center_y = (box[1] + box[3]) / 2
        for region_index, region in enumerate(regions):
            if region.page != page_no:
                continue
            left, top, right, bottom = _grown(region.bbox, TABLE_REGION_SLACK)
            if left <= center_x <= right and top <= center_y <= bottom:
                cells_per_region[region_index].append(
                    TableCell(text=text.strip(), bbox=box, order=index)
                )
                consumed.add(index)
                break

    anchored: list[TableRun] = []
    floating: list[TableRun] = []
    start_index: dict[int, TableRun] = {}
    for region_index, region in enumerate(regions):
        region_cells = cells_per_region[region_index]
        if region.grid is not None:
            if region_cells:
                orders = [cell.order for cell in region_cells]
                run = TableRun(
                    text=serialize_rows(region.grid),
                    page=region.page,
                    rows=region.grid,
                    aligned=True,
                    first_index=min(orders),
                    last_index=max(orders),
                )
            else:
                # Grid without in-region cell items (structure-enabled parse
                # moved the cell text into the grid): no stream anchor.
                run = TableRun(
                    text=serialize_rows(region.grid),
                    page=region.page,
                    rows=region.grid,
                    aligned=True,
                    first_index=-1,
                    last_index=-1,
                )
        elif region_cells:
            orders = [cell.order for cell in region_cells]
            run = build_table_run(
                region_cells,
                page=region.page,
                first_index=min(orders),
                last_index=max(orders),
            )
        else:
            continue
        if not run.aligned:
            # INFO, not WARNING: the durable, machine-readable signal is the
            # ``table_degenerate`` flag the caller attaches to the stored
            # chunks (the chunk still carries the table's full text). This
            # record is console diagnostics only and stays out of the normal
            # console flow — the CLI console handler defaults to WARNING —
            # and can be re-enabled via ``secondbrain --verbose`` or
            # ``SECONDBRAIN_LOG_LEVEL`` (honored by ``setup_logging``).
            logger.info(
                "Table serialization failed the row-alignment check for %s "
                "(page %d): cells read out of row order; storing chunk with "
                "table_degenerate flag — table content may be unreliable",
                file_path if file_path is not None else "<unknown file>",
                run.page,
            )
        if run.first_index >= 0:
            anchored.append(run)
            start_index[run.first_index] = run
        else:
            floating.append(run)

    return TableRunPlan(
        anchored=tuple(anchored),
        floating=tuple(floating),
        start_index=start_index,
        consumed=frozenset(consumed),
    )
