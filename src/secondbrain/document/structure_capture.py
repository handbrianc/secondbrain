"""Structure capture at ingest time (structure-aware ingestion, lane 1a).

Captures a document's structure tree once at ingest from authoritative
sources, per the change design §5:

* **PDF outline** (:func:`capture_pdf_outline`) — the PDF's own bookmark tree
  read through pypdfium2; the authoritative chapter tree when present.
* **/PageLabels** (:func:`capture_page_labels`) — per-page printed labels,
  grouped into runs (printed-page map for display; never used to filter
  retrieval).
* **docling heading hierarchy** (:func:`capture_docling_headings`) —
  ``SectionHeaderItem`` items (with the heading levels docling's
  heading-hierarchy stage attaches when
  ``heading_hierarchy_options.enabled=True``); fills sections when the
  outline is absent and always participates in the merge. Items failing the
  heading plausibility gate (:func:`is_plausible_heading`,
  fix-chunk-heading-context D1) create no nodes; outline capture is never
  gated. A plausible candidate whose physical page lies INSIDE the detected
  ToC page span AND whose text matches a ToC listing row is suppressed
  (fix-chat-session-integrity D4): docling detects flattened ToC rows as
  headings, and without suppression a table of contents mints ghost
  chapter nodes. Suppressed candidates are recorded in the capture's
  sources payload under ``suppressed_toc_headings``, which the storage
  layer persists verbatim into ``structure_meta``.
* **Merge** (:func:`merge_structures`) — outline nodes win where both sources
  describe the same region; docling-only headings attach under the containing
  outline node by page range; docling-only chapters fill the tree when no
  outline exists.
* **ToC number recovery** (:func:`recover_chapter_numbers`) — after the merge,
  number-less nodes are matched against the document's own table-of-contents
  listings (dot-leader and leader-less rows parsed from the PDF's native text
  layer via :func:`parse_toc_rows`) and gain their chapter/section numbers
  (fix-chapter-coverage, D1). Parsed numbers always win; ambiguous or
  unmatched nodes stay number-less. A match must also sit where the ToC says
  it does: the row's printed page, mapped through /PageLabels, has to land
  within a few physical pages of the node (:func:`_page_bound_allows`), so a
  generic title cannot reach across the document. Where the labels yield no
  mapping, the printed→physical offset is derived as the median offset of
  the listings already matched in the same walk instead of being assumed
  (fix-chat-session-integrity D5), and a recovered number already held by a
  same-scope sibling is refused rather than doubled.
* **Dispatcher** (:func:`capture_structure`) — the single capture point the
  processor worker and the async ingestor call. **Never raises**: any failure
  is caught, logged as a warning, and reported as ``None`` so ingest proceeds
  and the document simply has no tree.

Page semantics: every page number here is the absolute **1-based** physical
page — the same axis as docling's ``prov.page_no`` (verified in
``processor.py``'s comment) and the qdrant payload ``page_number``. pypdfium2
bookmark/dest page indexes are 0-based and converted on read.

Audio capture (ASR timestamps → segment nodes, design §5) and LLM topic
segmentation (:func:`audio_topic_segments`) live here as lane 1b work: the
dispatcher routes audio documents to :func:`capture_audio_structure`, which
degrades honestly to ``None`` when no ASR document reaches it (the current
ingest wiring releases the ASR document after extraction, so live audio
documents stay treeless until that wiring passes it through).
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import unicodedata
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple, cast

from secondbrain.document.chunker import docling_item_label, is_plausible_heading
from secondbrain.document.fast_text import extract_native_pdf_text
from secondbrain.storage.structure_sqlite import (
    AudioSegment,
    DocumentStructure,
    PageLabelRange,
    StructureNode,
)

__all__ = [
    "TocListing",
    "audio_topic_segments",
    "capture_audio_structure",
    "capture_docling_headings",
    "capture_page_labels",
    "capture_pdf_outline",
    "capture_structure",
    "merge_structures",
    "parse_toc_rows",
    "recover_chapter_numbers",
]

logger = logging.getLogger(__name__)

# docling label (string value) whose items carry heading text + level for the
# heading-hierarchy source. Compared against the *string* label via
# :func:`docling_item_label` so fabricated/shaped items and real docling
# items are read the same way (and no docling import is needed here).
_SECTION_HEADER_LABEL = "section_header"

# Audio suffixes routed to the ASR converter (mirrors
# docling_factory._AUDIO_SUFFIXES; resolved lazily in the dispatcher to keep
# this module free of docling_factory coupling at import time).
_AUDIO_SUFFIXES_FALLBACK = frozenset({".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"})

# Leading numbering tokens parsed out of heading titles, design §5 ("Chapter
# 5", "5.2", "I.1"). Ordered: the chapter-word shape first, then dotted
# numbers, then bare numbers/romans.
_CHAPTER_WORD_RE = re.compile(
    r"^chapter\s+(?P<num>\d{1,3}|[IVXLCDM]+)\b(?:\s*[.:—–-]\s*|\s+)(?P<rest>\S.*)$",  # noqa: RUF001 - the class intentionally matches Unicode dashes
    re.IGNORECASE,
)
_CHAPTER_WORD_ONLY_RE = re.compile(
    r"^chapter\s+(?P<num>\d{1,3}|[IVXLCDM]+)\b[.:\s]*$", re.IGNORECASE
)
_DOTTED_NUMBER_RE = re.compile(
    r"^(?P<num>\d{1,3}(?:\.\d{1,3})+|[IVXLCDM]+\.\d{1,3}(?:\.\d{1,3})*)\.?"
    r"\s+(?P<rest>\S.*)$"
)
_DOTTED_NUMBER_ONLY_RE = re.compile(
    r"^(?P<num>\d{1,3}(?:\.\d{1,3})+|[IVXLCDM]+\.\d{1,3}(?:\.\d{1,3})*)\.?$"
)
# Bare shapes require trailing text so a title that is only a year ("1984")
# is never mistaken for a number.
_BARE_NUMBER_RE = re.compile(r"^(?P<num>\d{1,3})\.?\s+(?P<rest>\S.*)$")
# Bare romans need length >= 2 (and uppercase) so ordinary capitalized words
# ("A", "I", "D") are never read as roman numerals.
_BARE_ROMAN_RE = re.compile(r"^(?P<num>[IVXLCDM]{2,})\.?\s+(?P<rest>\S.*)$")

_ROMAN_IS_ONE_RE = re.compile(r"^[IVXLCDM]+$")
_PART_TITLE_RE = re.compile(r"^part\b", re.IGNORECASE)

_SLUG_MAX_LEN = 40


# ---------------------------------------------------------------------------
# Title / numbering helpers (pure)
# ---------------------------------------------------------------------------


def _normalize_number(number: str) -> str:
    """Normalize a numbering token: digits collapse leading zeros, romans uppercase.

    Args:
        number: Raw numbering token, e.g. ``"05"``, ``"5.02"`` or ``"iv"``.

    Returns
    -------
        Normalized token, e.g. ``"5"``, ``"5.2"``, ``"IV"``.
    """
    components = number.split(".")
    normalized: list[str] = []
    for component in components:
        if component.isdigit():
            normalized.append(str(int(component)))
        else:
            normalized.append(component.upper())
    return ".".join(normalized)


def _parse_numbering(title: str) -> tuple[str | None, str]:
    """Parse a leading numbering token out of a heading title.

    Recognizes the design §5 shapes — ``"Chapter 5"``, ``"5.2"``, ``"I.1"`` —
    plus bare ``"5 Introduction"``/``"IV Results"`` forms. Titles that do not
    open with a recognizable numbering token return ``(None, title)``.

    Args:
        title: Raw heading/outline title.

    Returns
    -------
        ``(number, clean_title)`` where *number* is the normalized token
        (``"5"``, ``"5.2"``, ``"I.1"``) or ``None`` when unnumbered, and
        *clean_title* is the title with the numbering token removed (falls
        back to the original when nothing else remains).
    """
    for pattern in (
        _CHAPTER_WORD_RE,
        _DOTTED_NUMBER_RE,
        _BARE_NUMBER_RE,
        _BARE_ROMAN_RE,
    ):
        match = pattern.match(title)
        if match is None:
            continue
        number = _normalize_number(match.group("num"))
        rest = match.group("rest").strip()
        return number, (rest or title)
    # Titles consisting of ONLY the number ("Chapter 5", "5.2") still carry
    # the number; the title itself stays as the display text.
    for pattern in (_CHAPTER_WORD_ONLY_RE, _DOTTED_NUMBER_ONLY_RE):
        match = pattern.match(title)
        if match is not None:
            return _normalize_number(match.group("num")), title
    return None, title


def _is_chapter_one(number: str | None) -> bool:
    """Check whether *number* reads as a chapter-level "1" (restart signal).

    Used for anthology part-opener detection: a level-1 outline item whose
    descendants restart level-1-style chapter numbering (first child numbered
    ``1``/``I``) is a part opener.

    Args:
        number: Normalized numbering token or None.

    Returns
    -------
        True when the number is the single component ``"1"`` or roman ``"I"``.
    """
    if number is None:
        return False
    components = number.split(".")
    if len(components) != 1:
        return False
    component = components[0]
    if component.isdigit():
        return int(component) == 1
    return bool(_ROMAN_IS_ONE_RE.fullmatch(component)) and component == "I"


def _slugify(text: str) -> str:
    """Slugify a title for deterministic unnumbered node ids.

    Args:
        text: Title text.

    Returns
    -------
        Lowercase ASCII slug (non-alphanumerics folded to ``-``), truncated;
        ``"node"`` when nothing usable remains.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_folded = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_folded.lower()).strip("-")
    slug = slug[:_SLUG_MAX_LEN].rstrip("-")
    return slug or "node"


def _padded_id_number(number: str) -> str:
    """Zero-pad each decimal component of a number for node-id construction.

    Args:
        number: Normalized number, e.g. ``"5"``, ``"5.2"``, ``"I.1"``.

    Returns
    -------
        Id fragment, e.g. ``"05"``, ``"05.02"``, ``"I.01"``.
    """
    components = number.split(".")
    padded = [
        f"{int(component):02d}" if component.isdigit() else component
        for component in components
    ]
    return ".".join(padded)


# ---------------------------------------------------------------------------
# Tree construction (pure — shared by outline and docling capture)
# ---------------------------------------------------------------------------


def _heading_entry(
    level: int, title: str, page_start: int | None
) -> tuple[int, str | None, str, int | None]:
    """Build one normalized heading entry from raw heading inputs.

    Args:
        level: Raw heading level (clamped to >= 1).
        title: Raw heading title.
        page_start: 1-based page the heading opens on, or None.

    Returns
    -------
        ``(level, number, clean_title, page_start)`` with the numbering token
        parsed out of the title.
    """
    number, clean_title = _parse_numbering(title.strip())
    return max(1, int(level)), number, clean_title, page_start


def _assign_parents_by_level(
    entries: list[tuple[int, str | None, str, int | None]],
) -> list[dict[str, Any]]:
    """Assign parent links to heading entries by a level stack.

    Walks the entries in document order holding the open heading at each
    level; a heading at level *L* becomes the child of the nearest still-open
    heading at a shallower level. Skipped levels are tolerated.

    Args:
        entries: Normalized heading entries in document order.

    Returns
    -------
        Entry dicts with ``parent`` (index or None) set; original tuple kept
        under ``entry``.
    """
    nodes: list[dict[str, Any]] = []
    stack: list[int] = []
    for index, entry in enumerate(entries):
        level, number, title, page_start = entry
        while stack and entries[stack[-1]][0] >= level:
            stack.pop()
        parent = stack[-1] if stack else None
        nodes.append(
            {
                "entry": entry,
                "level": level,
                "number": number,
                "title": title,
                "page_start": page_start,
                "parent": parent,
            }
        )
        stack.append(index)
    return nodes


def _kind_for_docling_level(level: int) -> str:
    """Map a heading level to its node kind (docling/merged docling nodes).

    Level 1 → ``chapter``, 2 → ``section``, deeper → ``subsection`` (design
    §5, docling branch).

    Args:
        level: 1-based heading level.

    Returns
    -------
        One of the ``StructureNode.kind`` values.
    """
    if level <= 1:
        return "chapter"
    if level == 2:
        return "section"
    return "subsection"


def _detect_part_openers(built: list[dict[str, Any]], allow_parts: bool) -> None:
    """Mark anthology part-opener nodes in place (outline capture only).

    Two opener shapes are recognized (design §5):

    * a level-1 item titled ``"Part …"``, or
    * a level-1 item whose first child's number restarts level-1-style
      chapter numbering (``"1"``/``"I"``) — descendants redefine level-1
      numbering, the anthology signature.

    Children of a detected part keep their outline level but are chapters by
    role; ids stay collision-free because chapter ids under a part are
    scoped to the part (see :func:`_build_nodes_from_headings`). A title
    opener whose title carries a number ("Part I — Basics") also gains that
    number, driving the ``partI``-style id and ``"Part I"`` heading label.

    Args:
        built: Parent-assigned entry dicts (mutated: ``kind`` added).
        allow_parts: Whether part detection runs (True for outline capture,
            False for docling headings, whose levels map directly).
    """
    for node in built:
        node["kind"] = None  # filled below

    if not allow_parts:
        return

    children: dict[int, list[int]] = {}
    for index, node in enumerate(built):
        parent = node["parent"]
        if parent is not None:
            children.setdefault(parent, []).append(index)

    for index, node in enumerate(built):
        if node["parent"] is not None or node["level"] != 1:
            continue
        title = node["title"]
        title_opener = bool(_PART_TITLE_RE.match(title))
        kid_indices = children.get(index, [])
        restart_opener = bool(kid_indices) and _is_chapter_one(
            built[kid_indices[0]]["number"]
        )
        if title_opener or restart_opener:
            node["kind"] = "part"
            if node["number"] is None:
                node["number"] = _part_number_from_title(title)


def _part_number_from_title(title: str) -> str | None:
    """Extract the part number from a "Part <num>" title (pure).

    Args:
        title: Part-opener title, e.g. ``"Part I — Basics"``.

    Returns
    -------
        The normalized number (``"I"``, ``"2"``), or None when the title
        carries no number.
    """
    match = re.match(r"^part\s+(?P<num>\d{1,3}|[IVXLCDM]+)\b", title, re.IGNORECASE)
    return _normalize_number(match.group("num")) if match else None


def _role_kind(node: dict[str, Any], built: list[dict[str, Any]]) -> str:
    """Derive the node kind from its position in the (outline) tree.

    Roots and children of parts are chapters; children of chapters are
    sections; everything deeper is a subsection. Explicitly detected parts
    keep the ``part`` kind.

    Args:
        node: Entry dict with ``kind`` (possibly pre-set to ``"part"``),
            ``parent`` and ``level``.
        built: All entry dicts (for parent lookups).

    Returns
    -------
        One of the ``StructureNode.kind`` values (``segment`` never occurs in
        heading capture).
    """
    preset = node["kind"]
    if preset == "part":
        return "part"
    parent = node["parent"]
    if parent is None:
        return "chapter"
    parent_kind = built[parent]["kind"]
    if parent_kind == "part":
        return "chapter"
    if parent_kind == "chapter":
        return "section"
    return "subsection"


def _node_label(kind: str, number: str | None, title: str) -> str:
    """Build the heading-path segment for one node.

    Chapters render as ``"Chapter {number} — {title}"`` (design §3 example),
    parts as ``"Part {number}"``; numbered sections render as their bare
    number (``"1.2"``, matching the design example ``"… > 1.2 > 1.2.3"``);
    unnumbered nodes fall back to their title.

    Args:
        kind: Node kind.
        number: Normalized number or None.
        title: Clean title.

    Returns
    -------
        The heading-path segment string.
    """
    if kind == "part":
        return f"Part {number}" if number else title
    if kind == "chapter":
        if number and title:
            return f"Chapter {number} — {title}"
        if number:
            return f"Chapter {number}"
        return title
    if number:
        return number
    return title


def _unique_node_id(candidate: str, used: set[str]) -> str:
    """Return *candidate* or a deterministic ``-2``/``-3``… disambiguation.

    Args:
        candidate: Proposed node id.
        used: Ids already assigned (updated in place).

    Returns
    -------
        A node id unique within *used*.
    """
    if candidate not in used:
        used.add(candidate)
        return candidate
    counter = 2
    while f"{candidate}-{counter}" in used:
        counter += 1
    disambiguated = f"{candidate}-{counter}"
    used.add(disambiguated)
    return disambiguated


def _build_nodes_from_headings(
    headings: list[tuple[int, str, int | None]],
    *,
    source_file: str,
    allow_parts: bool,
    final_page: int | None,
) -> list[StructureNode]:
    """Build a node tree from a document-ordered heading stream.

    Pure mapping used by both capture sources: outline bookmarks and docling
    section headers normalize to ``(level, title, page_start)`` entries, get
    parent links by level stack, part openers are detected (outline only),
    kinds/ids/heading paths are assigned deterministically, and page ranges
    are derived from tree order (next same-or-shallower node start - 1,
    clamped so a node never ends before it starts; the last node ends at
    *final_page*).

    Args:
        headings: ``(level, title, page_start)`` tuples in document order;
            entries without a page are skipped by the caller.
        source_file: The document key the nodes belong to.
        allow_parts: Run anthology part-opener detection (outline capture).
        final_page: Page bound for the tree's last node (document page count
            for outline capture, last known page for docling capture).

    Returns
    -------
        The tree's nodes in document order, with ``parent_id``, ``kind``,
        deterministic ``node_id`` and ``heading_path`` filled.
    """
    entries = [
        _heading_entry(level, title, page_start)
        for level, title, page_start in headings
        if page_start is not None
    ]
    built = _assign_parents_by_level(entries)
    _detect_part_openers(built, allow_parts)

    used_ids: set[str] = set()
    for node in built:
        kind = _role_kind(node, built)
        node["kind"] = kind
        node["node_id"] = _make_node_id(node, built, kind, used_ids)

    # Heading paths need parent kinds/ids settled first.
    for node in built:
        node["heading_label"] = _node_label(node["kind"], node["number"], node["title"])
    for index, node in enumerate(built):
        ancestor_labels = []
        cursor: int | None = index
        while cursor is not None:
            ancestor_labels.append(built[cursor]["heading_label"])
            cursor = built[cursor]["parent"]
        node["heading_path"] = " > ".join(reversed(ancestor_labels))

    _derive_page_ends(built, final_page)

    return [
        StructureNode(
            node_id=node["node_id"],
            parent_id=(
                built[node["parent"]]["node_id"] if node["parent"] is not None else None
            ),
            kind=node["kind"],
            level=node["level"],
            number=node["number"],
            title=node["title"],
            page_start=node["page_start"],
            page_end=node["page_end"],
            heading_path=node["heading_path"],
        )
        for node in built
    ]


def _make_node_id(
    node: dict[str, Any],
    built: list[dict[str, Any]],
    kind: str,
    used: set[str],
) -> str:
    """Build the deterministic node id for one tree node.

    Shapes (design §3): ``"ch05"`` (numbered chapter), ``"sec05.02"``
    (numbered section, every decimal component zero-padded, roman components
    kept), ``"partI"`` (numbered part), part-scoped chapters as
    ``"{part_id}.{number}"`` (e.g. ``"partI.1"``), and slug fallbacks
    (``"ch-installing"``, ``"sec-introduction"``, ``"part-prologue"``) for
    unnumbered nodes.

    Args:
        node: The entry dict (level/number/title/parent).
        built: All entry dicts (for part-scoped chapter ids).
        kind: The node's kind.
        used: Ids assigned so far (shared across the tree).

    Returns
    -------
        A deterministic, tree-unique node id.
    """
    number = node["number"]
    if kind == "part":
        base = f"part{number}" if number else f"part-{_slugify(node['title'])}"
        return _unique_node_id(base, used)
    if kind == "chapter":
        if number is None:
            return _unique_node_id(f"ch-{_slugify(node['title'])}", used)
        parent = node["parent"]
        if parent is not None and built[parent]["kind"] == "part":
            # Chapter numbering restarts inside anthology parts, so chapter
            # ids are scoped by their part id: part I chapter 1 → "partI.1".
            return _unique_node_id(f"{built[parent]['node_id']}.{number}", used)
        return _unique_node_id(f"ch{_padded_id_number(number)}", used)
    if number is None:
        return _unique_node_id(f"sec-{_slugify(node['title'])}", used)
    return _unique_node_id(f"sec{_padded_id_number(number)}", used)


def _derive_page_ends(built: list[dict[str, Any]], final_page: int | None) -> None:
    """Derive page ranges from tree order, in place.

    Each node ends where the next node at the same-or-shallower level starts
    (minus 1); the last node ends at *final_page*. Same-page openers stay
    nested correctly because ranges follow tree order, and derived ends are
    clamped so a node never ends before its own start page.

    Args:
        built: Entry dicts with ``level`` and ``page_start`` (mutated:
            ``page_end`` added).
        final_page: Bound for the tree's last node, or None.
    """
    for index, node in enumerate(built):
        page_start = node["page_start"]
        if page_start is None:
            node["page_end"] = None
            continue
        page_end: int | None = None
        for follower in built[index + 1 :]:
            if follower["level"] <= node["level"]:
                follower_start = follower["page_start"]
                if follower_start is not None:
                    page_end = follower_start - 1
                break
        if page_end is None:
            page_end = final_page
        if page_end is not None:
            page_end = max(page_start, page_end)
        node["page_end"] = page_end


# ---------------------------------------------------------------------------
# PDF outline + page labels
# ---------------------------------------------------------------------------


def _outline_items_from_bookmarks(
    bookmarks: list[Any],
) -> list[tuple[int, str, int | None]]:
    """Normalize bookmark-shaped objects to heading entries.

    Pure adapter so the mapping logic is testable without a real PDF: items
    need ``level`` (0-based, as pypdfium2 ≥ 5 yields), ``get_title()`` and a
    ``get_dest()`` exposing ``get_index()`` (0-based page index or None).
    Items with no resolvable page are skipped (design §5).

    Args:
        bookmarks: Bookmark-shaped objects in document (DFS) order.

    Returns
    -------
        ``(level_1_based, title, page_start_1_based)`` tuples.
    """
    items: list[tuple[int, str, int | None]] = []
    for bookmark in bookmarks:
        try:
            title = bookmark.get_title() or ""
            level = int(bookmark.level) + 1
            dest = bookmark.get_dest()
            page_index = dest.get_index() if dest is not None else None
        except Exception:  # pragma: no cover - hostile bookmark shape
            continue
        if page_index is None or page_index < 0:
            continue
        items.append((level, title, page_index + 1))
    return items


def capture_pdf_outline(path: Path) -> DocumentStructure:
    """Capture the PDF's outline (bookmark tree) as a structure part.

    Opens the PDF with pypdfium2 and reads the table of contents (design §5).
    Never raises: on any failure an empty part with ``sources["outline"] =
    False`` is returned so the merge can still proceed with docling headings.

    Args:
        path: Path to the PDF file (unresolved — this string becomes the
            tree's ``source_file`` key).

    Returns
    -------
        A :class:`DocumentStructure` carrying the outline nodes (page ranges
        derived from tree order, last node ending at the document page count)
        and ``sources={"outline": <found>}``.
    """
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            page_count = len(pdf)
            # Extract titles/pages WHILE the document is open: get_toc()
            # yields lazy PdfBookmark handles whose get_title()/get_dest()
            # call into libpdfium — reading them after close() would touch
            # freed memory.
            headings = _outline_items_from_bookmarks(list(pdf.get_toc()))
        finally:
            pdf.close()
        nodes = _build_nodes_from_headings(
            headings,
            source_file=str(path),
            allow_parts=True,
            final_page=page_count if page_count > 0 else None,
        )
        return DocumentStructure(
            source_file=str(path), nodes=nodes, sources={"outline": bool(nodes)}
        )
    except Exception as e:
        logger.warning(
            "PDF outline capture failed for %s (%s: %s); proceeding without it",
            path,
            type(e).__name__,
            e,
        )
        return DocumentStructure(source_file=str(path), sources={"outline": False})


def _label_style(label: str) -> str | None:
    """Extract the label style when trivially parseable, else None.

    Args:
        label: One page-label string.

    Returns
    -------
        ``"decimal"``, ``"lower_roman"``, ``"upper_roman"``,
        ``"lower_alpha"``, ``"upper_alpha"``, or None for anything not
        trivially parseable (prefixed/composite labels).
    """
    if label.isdigit():
        return "decimal"
    if re.fullmatch(r"[ivxlcdm]+", label):
        return "lower_roman"
    if re.fullmatch(r"[IVXLCDM]+", label):
        return "upper_roman"
    if re.fullmatch(r"[a-z]", label):
        return "lower_alpha"
    if re.fullmatch(r"[A-Z]", label):
        return "upper_alpha"
    return None


def _group_label_runs(labels: list[str]) -> list[PageLabelRange]:
    """Group equal consecutive page labels into runs (pure).

    Empty labels (pages outside any ``/PageLabels`` range) are skipped so a
    document without labels yields no rows.

    Args:
        labels: One label string per physical page, 1-based order.

    Returns
    -------
        :class:`PageLabelRange` rows covering the labeled pages.
    """
    runs: list[PageLabelRange] = []
    run_start = 0
    for index in range(1, len(labels) + 1):
        if index < len(labels) and labels[index] == labels[run_start]:
            continue
        label = labels[run_start]
        if label:
            runs.append(
                PageLabelRange(
                    page_start=run_start + 1,
                    page_end=index,
                    label=label,
                    style=_label_style(label),
                )
            )
        run_start = index
    return runs


def capture_page_labels(path: Path) -> list[PageLabelRange]:
    """Capture the PDF's ``/PageLabels`` as grouped runs (design §5).

    Reads one label per page through pypdfium2's ``get_page_label`` (the
    ``FPDF_GetPageLabel`` binding) and groups equal consecutive labels.
    Never raises: on any failure an empty list is returned.

    Args:
        path: Path to the PDF file.

    Returns
    -------
        :class:`PageLabelRange` rows; empty when the document has no labels
        or reading failed.
    """
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        try:
            labels = [pdf.get_page_label(index) for index in range(len(pdf))]
        finally:
            pdf.close()
    except Exception as e:
        logger.warning(
            "Page-label capture failed for %s (%s: %s); proceeding without them",
            path,
            type(e).__name__,
            e,
        )
        return []
    return _group_label_runs(labels)


# ---------------------------------------------------------------------------
# docling heading hierarchy
# ---------------------------------------------------------------------------


def _docling_item_page(item: Any) -> int | None:
    """Read the 1-based page of a docling text item (processor.py semantics).

    Same provenance read as ``processor._extend_segments_from_document``:
    ``item.prov[0].page_no`` is the absolute 1-based PDF page index (verified
    against docling 2.138.0 — see the comment at processor.py:214-225).

    Args:
        item: A docling text item (or fabricated shape).

    Returns
    -------
        The 1-based page number, or None when the item has no usable
        provenance.
    """
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None
    page_no = getattr(prov[0], "page_no", None)
    if isinstance(page_no, bool) or not isinstance(page_no, (int, float)):
        return None
    return int(page_no)


def _iter_docling_texts(docling_doc: Any) -> list[Any]:
    """Collect the text items of one docling document (or a sequence of them).

    Args:
        docling_doc: A parsed docling document, or a sequence of per-window
            parsed documents (page-windowed conversion captures one window at
            a time and releases it; the sequence keeps document order).

    Returns
    -------
        The concatenated ``.texts`` item lists in document order.
    """
    docs = docling_doc if isinstance(docling_doc, (list, tuple)) else [docling_doc]
    items: list[Any] = []
    for doc in docs:
        if doc is None:
            continue
        texts = getattr(doc, "texts", None)
        if not texts:
            continue
        items.extend(texts)
    return items


# structure_meta key under which suppressed ToC-page heading candidates are
# recorded (fix-chat-session-integrity D4). ``structure_meta`` stores the
# capture's ``sources`` payload verbatim as JSON (storage/ owns that write;
# this lane must not touch it), and the payload's typed shape is
# ``dict[str, bool]`` — so the suppressed-candidate list rides under its own
# key as its JSON encoding. The storage-side reload bool-coerces sources
# values, so a reloaded tree sees the key's presence while the persisted row
# keeps the full list for audit.
_META_SUPPRESSED_KEY = "suppressed_toc_headings"


def _text_matches_toc_listing(
    text: str, listing_keys: Sequence[tuple[str, str]]
) -> bool:
    """Whether a heading candidate's text echoes a ToC listing row (D4).

    The numbering token is parsed out of the heading text first (docling
    reads the flattened ToC row verbatim — "7 Proxmox VE Storage" — while
    :func:`parse_toc_rows` already stripped the row's number), then both
    match keys (:func:`_match_key`, glued-variant :func:`_match_squash`) are
    compared against every listing title.

    Args:
        text: The heading candidate's raw text.
        listing_keys: ``(key, squash)`` pairs of the parsed listing titles.

    Returns
    -------
        True when the title (with or without its numbering token) equals a
        listing row's title.
    """
    _, rest = _parse_numbering(text)
    key, squash = _match_key(rest), _match_squash(rest)
    return any(
        listing_key == key or listing_squash == squash
        for listing_key, listing_squash in listing_keys
    )


def _suppress_toc_page_headings(
    headings: list[tuple[int, str, int | None]],
    listings: Sequence[TocListing],
    toc_page_span: tuple[int, int] | None,
) -> tuple[list[tuple[int, str, int | None]], list[dict[str, Any]]]:
    """Split heading candidates into kept and ToC-ghost-suppressed (D4).

    A candidate is suppressed only when BOTH conditions hold — its physical
    page lies inside the detected ToC page span AND its text matches a ToC
    listing row (:func:`_text_matches_toc_listing`). A page-inside-span test
    alone is too eager (front-matter headings share those pages); a
    text-match test alone re-admits ghosts when pages are mis-parsed. Real
    chapter candidates starting at or after the span's end are kept
    untouched, and page-less candidates are kept (they cannot be placed
    inside a span).

    Args:
        headings: ``(level, title, page_start)`` candidates in document order.
        listings: The document's parsed ToC rows.
        toc_page_span: Inclusive 1-based physical page span, or None when
            unknown (nothing is suppressed without span evidence).

    Returns
    -------
        ``(kept, suppressed)`` — the surviving candidates and one
        ``{"title": …, "page": …}`` record per suppressed candidate.
    """
    if toc_page_span is None or not listings:
        return headings, []
    span_low, span_high = toc_page_span
    listing_keys = [
        (_match_key(row.title), _match_squash(row.title)) for row in listings
    ]
    kept: list[tuple[int, str, int | None]] = []
    suppressed: list[dict[str, Any]] = []
    for level, text, page in headings:
        if (
            page is not None
            and span_low <= page <= span_high
            and _text_matches_toc_listing(text, listing_keys)
        ):
            suppressed.append({"title": text, "page": page})
            continue
        kept.append((level, text, page))
    return kept, suppressed


def _attach_suppressed_meta(
    structure: DocumentStructure, suppressed: Sequence[dict[str, Any]]
) -> None:
    """Record suppressed ToC-page headings in the capture's sources payload.

    ``structure_meta`` persists ``sources`` verbatim as JSON (the storage
    layer owns that write), so the suppressed candidates ride the payload
    under :data:`_META_SUPPRESSED_KEY` — encoded, because the payload's
    typed shape is ``dict[str, bool]`` (see the constant's comment). Mutating
    the mapping in place after construction is the established pattern
    (``merged.sources["page_labels"] = …``); a no-op when nothing was
    suppressed.

    Args:
        structure: The captured structure to annotate, in place.
        suppressed: ``{"title": …, "page": …}`` records to record.
    """
    if not suppressed:
        return
    entries = sorted(
        ({"title": str(e["title"]), "page": e["page"]} for e in suppressed),
        key=lambda e: (int(e["page"]), str(e["title"])),
    )
    sources = cast("dict[str, Any]", structure.sources)
    sources[_META_SUPPRESSED_KEY] = json.dumps(entries, sort_keys=True)


def _suppressed_entries_of(part: DocumentStructure) -> list[dict[str, Any]]:
    """Read a captured part's suppressed-candidate records back.

    Decoding mirrors :func:`_attach_suppressed_meta`; anything absent or
    unparsable (including the bool-coerced shape a reloaded tree carries)
    yields no entries.

    Args:
        part: A captured (or merged) structure part.

    Returns
    -------
        The decoded ``{"title": …, "page": …}`` records, in stored order.
    """
    raw = cast("object", part.sources.get(_META_SUPPRESSED_KEY))
    if not isinstance(raw, str):
        return []
    try:
        decoded = json.loads(raw)
    except ValueError:
        logger.warning("Unparsable suppressed-ToC-heading payload; ignoring")
        return []
    if not isinstance(decoded, list):
        return []
    return [
        {"title": str(entry.get("title", "")), "page": entry.get("page")}
        for entry in decoded
        if isinstance(entry, dict)
    ]


def capture_docling_headings(
    docling_doc: Any,
    path: Path,
    *,
    toc_listings: Sequence[TocListing] | None = None,
    toc_page_span: tuple[int, int] | None = None,
) -> DocumentStructure | None:
    """Capture the docling heading hierarchy of a parsed document.

    Scans ``SectionHeaderItem`` items (``label == "section_header"``) taking
    their text, ``level`` (attached by docling's heading-hierarchy stage,
    which ``docling_factory`` enables for PDF pipelines) and provenance page
    (same 1-based page semantics as ``processor.py:204-230``). Level 1 →
    ``chapter``, deeper → ``section``/``subsection`` (design §5). Items whose
    text fails the :func:`is_plausible_heading` gate (run-in labels, synopsis
    lines — openspec fix-chunk-heading-context D1) are skipped from node
    creation; outline capture stays ungated and no text item is altered,
    dropped, or reordered.

    Plausible candidates whose physical page lies INSIDE the detected ToC
    page span AND whose text matches a ToC listing row are suppressed from
    node creation (fix-chat-session-integrity D4): docling detects the
    flattened ToC rows themselves as section headers, and every one of them
    used to become a ghost chapter node sitting on the ToC's own pages.
    Suppressed candidates are recorded in the part's sources payload under
    ``suppressed_toc_headings`` (persisted into ``structure_meta`` by the
    storage layer); real chapter candidates starting at or after the span's
    end are kept untouched. A capture whose every candidate was suppressed
    reports ``None`` (no part to record the suppression on) — the ghost
    nodes are gone either way. Never raises.

    Args:
        docling_doc: A parsed docling document, or a sequence of per-window
            parsed documents. Page-windowed conversion yields one document
            per window; every ``prov.page_no`` is absolute (verified), so the
            parts concatenate into one document-order stream.
        path: Path to the source file (unresolved — becomes ``source_file``).
        toc_listings: The document's precomputed ToC rows (from
            :func:`_pdf_toc_listings`); when omitted they are scanned once
            here — only for ``.pdf`` paths, and only for direct callers, as
            :func:`capture_structure` precomputes the same evidence for the
            suppression AND the number-recovery pass.
        toc_page_span: The precomputed ToC page span accompanying
            *toc_listings*.

    Returns
    -------
        A :class:`DocumentStructure` part with ``sources={"heading_hierarchy":
        True}`` when the document has any section headers, else ``None``.
    """
    try:
        if toc_listings is None and path.suffix.lower() == ".pdf":
            toc_listings, toc_page_span = _toc_evidence(path)
        candidates: list[tuple[int, str, int | None]] = []
        for item in _iter_docling_texts(docling_doc):
            if docling_item_label(item) != _SECTION_HEADER_LABEL:
                continue
            text = getattr(item, "text", None)
            if not text or not str(text).strip():
                continue
            heading_text = str(text).strip()
            # D1 gate (openspec fix-chunk-heading-context): docling's layout
            # model also marks run-in labels and synopsis lines as section
            # headers, and every one of them used to become a tree node.
            # The gate only decides heading treatment — text items are never
            # altered, dropped, or reordered, and the PDF outline capture
            # (capture_pdf_outline) stays ungated.
            if not is_plausible_heading(heading_text):
                continue
            raw_level = getattr(item, "level", None)
            if isinstance(raw_level, bool) or not isinstance(raw_level, (int, float)):
                level = 1
            else:
                level = max(1, int(raw_level))
            candidates.append((level, heading_text, _docling_item_page(item)))
        headings, suppressed = _suppress_toc_page_headings(
            candidates, toc_listings or [], toc_page_span
        )
        last_page: int | None = None
        for _, _, page_start in headings:
            if page_start is not None:
                last_page = (
                    page_start if last_page is None else max(last_page, page_start)
                )
        if not headings:
            return None
        nodes = _build_nodes_from_headings(
            headings,
            source_file=str(path),
            allow_parts=False,
            final_page=last_page,
        )
        if not nodes:
            # Every heading lacked provenance — nothing to place on a page;
            # an empty part would dishonestly mark "heading_hierarchy" as a
            # source, so report no capture at all.
            return None
        part = DocumentStructure(
            source_file=str(path),
            nodes=nodes,
            sources={"heading_hierarchy": True},
        )
        _attach_suppressed_meta(part, suppressed)
        return part
    except Exception as e:
        logger.warning(
            "docling heading capture failed for %s (%s: %s); proceeding without it",
            path,
            type(e).__name__,
            e,
        )
        return None


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------


def _norm_title(title: str) -> str:
    """Normalize a title for outline/docling duplicate matching.

    Args:
        title: A node title.

    Returns
    -------
        Lowercased, whitespace-collapsed title with trailing punctuation
        stripped.
    """
    collapsed = " ".join(title.split()).lower()
    return collapsed.rstrip(".:;")


def _is_outline_part(part: DocumentStructure) -> bool:
    """Check whether a captured part came from the PDF outline source.

    Args:
        part: A captured structure part.

    Returns
    -------
        True when the part's sources mark it as outline-captured.
    """
    return bool(part.sources.get("outline"))


def _outline_covered(
    docling_node: StructureNode, outline_nodes: list[StructureNode]
) -> bool:
    """Check whether an outline node already describes the same region.

    Outline wins (design §5): a docling heading is dropped when an outline
    node opens on the same page with the same normalized title, or — when
    both carry numbers — with the same number.

    Args:
        docling_node: A docling-captured node.
        outline_nodes: All outline-captured nodes.

    Returns
    -------
        True when the docling node is redundant next to the outline.
    """
    page = docling_node.page_start
    if page is None:
        return False
    docling_number = docling_node.number
    for outline_node in outline_nodes:
        if outline_node.page_start != page:
            continue
        if _norm_title(outline_node.title) == _norm_title(docling_node.title):
            return True
        if (
            docling_number is not None
            and outline_node.number is not None
            and outline_node.number == docling_number
        ):
            return True
    return False


def _contains_page(node: StructureNode, page: int) -> bool:
    """Check whether a node's page range contains *page*.

    Args:
        node: A node with a page range.
        page: 1-based physical page.

    Returns
    -------
        True when ``page_start <= page <= page_end`` (an open-ended node
        contains everything from its start).
    """
    if node.page_start is None or page < node.page_start:
        return False
    return node.page_end is None or page <= node.page_end


def _deepest_outline_container(
    page: int, outline_nodes: list[StructureNode]
) -> StructureNode | None:
    """Find the deepest outline node whose page range contains *page*.

    Design §5 attaches docling-only headings "under the containing outline
    chapter (by page range)"; the deepest containing node is used so a
    docling heading nests under a finer outline section when one exists and
    falls back to the chapter otherwise.

    Args:
        page: 1-based physical page of the docling heading.
        outline_nodes: All outline-captured nodes.

    Returns
    -------
        The deepest containing outline node, or None when none contains the
        page (e.g. front matter before the outline starts).
    """
    deepest: StructureNode | None = None
    for outline_node in outline_nodes:
        if _contains_page(outline_node, page) and (
            deepest is None or outline_node.level > deepest.level
        ):
            deepest = outline_node
    return deepest


def _rebuild_docling_forest(
    docling_nodes: list[StructureNode],
) -> list[tuple[StructureNode, StructureNode | None]]:
    """Re-parent docling nodes by a level stack over the concatenated stream.

    Docling-only trees (no outline) use this: parents follow from heading
    levels in document order. Level ties/jumps are tolerated. Returns
    ``(node, parent)`` pairs.

    Args:
        docling_nodes: Docling-captured nodes in document order.

    Returns
    -------
        ``(node, parent_node)`` pairs preserving document order.
    """
    pairs: list[tuple[StructureNode, StructureNode | None]] = []
    stack: list[StructureNode] = []
    for node in docling_nodes:
        while stack and stack[-1].level >= node.level:
            stack.pop()
        parent = stack[-1] if stack else None
        if parent is not None:
            # A window-boundary opener captured as its own part's root
            # ("chapter") may actually nest under an earlier window's node —
            # recompute the kind from its final depth.
            node = node.model_copy(update={"kind": _kind_for_docling_level(node.level)})
        pairs.append((node, parent))
        stack.append(node)
    return pairs


def _page_sort_key(
    pair: tuple[StructureNode, StructureNode | None],
) -> tuple[int, int]:
    """Sort key placing pageless pairs last, then by page (stable)."""
    node, _ = pair
    page = node.page_start if node.page_start is not None else 2_147_483_647
    return (page, 0)


def _flatten_pairs(
    pairs: list[tuple[StructureNode, StructureNode | None]],
) -> list[tuple[StructureNode, StructureNode | None]]:
    """Flatten ``(node, parent)`` pairs into DFS document order.

    Children of each parent keep document order, ordered by page so docling
    nodes attached inside an outline chapter interleave with the chapter's
    outline sections correctly (stable sort; outline nodes come first on
    page ties so outline ordering wins).

    Args:
        pairs: ``(node, parent)`` pairs.

    Returns
    -------
        Pairs in DFS document order.
    """
    children: dict[int, list[tuple[StructureNode, StructureNode | None]]] = {}
    roots: list[tuple[StructureNode, StructureNode | None]] = []
    pair_by_id: dict[int, tuple[StructureNode, StructureNode | None]] = {}
    for pair in pairs:
        node, parent = pair
        pair_by_id[id(node)] = pair
        if parent is None:
            roots.append(pair)
        else:
            children.setdefault(id(parent), []).append(pair)

    ordered_pairs: list[tuple[StructureNode, StructureNode | None]] = []

    def _emit(pair: tuple[StructureNode, StructureNode | None]) -> None:
        ordered_pairs.append(pair)
        node, _ = pair
        for child_pair in sorted(children.get(id(node), []), key=_page_sort_key):
            _emit(child_pair)

    for root_pair in sorted(roots, key=_page_sort_key):
        _emit(root_pair)
    return [pair_by_id[id(node)] for node, _ in ordered_pairs]


def _merge_tree(
    outline_nodes: list[StructureNode],
    docling_nodes: list[StructureNode],
) -> list[tuple[StructureNode, StructureNode | None]]:
    """Build the merged ``(node, parent)`` pairs from both sources.

    Outline nodes keep their captured parent links (the outline is the PDF's
    own authority); docling-only headings attach under the deepest outline
    node containing their page (re-based so a child is never at or above its
    parent's level, with kind recomputed from the final level), and become
    roots when no outline node contains their page. Without outline nodes
    the docling forest stands alone.

    Args:
        outline_nodes: Outline-captured nodes in document order.
        docling_nodes: Docling-captured nodes in document order (already
            filtered of outline-covered duplicates).

    Returns
    -------
        ``(node, parent)`` pairs for the whole merged tree.
    """
    if not outline_nodes:
        return _rebuild_docling_forest(docling_nodes)

    by_id = {node.node_id: node for node in outline_nodes}
    pairs: list[tuple[StructureNode, StructureNode | None]] = [
        (node, by_id.get(node.parent_id) if node.parent_id else None)
        for node in outline_nodes
    ]
    for docling_node in docling_nodes:
        parent: StructureNode | None = None
        page = docling_node.page_start
        if page is not None:
            parent = _deepest_outline_container(page, outline_nodes)
        if parent is not None:
            # Re-base so a child is never at or above its parent's level, and
            # recompute the kind from the FINAL level: a docling part's own
            # root is a "chapter" by construction, but once it nests under an
            # outline node its role follows its final depth (2 → section,
            # deeper → subsection).
            level = docling_node.level
            if level <= parent.level:
                level = parent.level + 1
            docling_node = docling_node.model_copy(
                update={
                    "level": level,
                    "kind": _kind_for_docling_level(level),
                }
            )
        pairs.append((docling_node, parent))
    return pairs


def _union_sources(parts: list[DocumentStructure]) -> dict[str, bool]:
    """OR-union the sources maps of the merged parts.

    Args:
        parts: The captured parts being merged.

    Returns
    -------
        One sources dict with the four canonical keys (``outline``,
        ``heading_hierarchy``, ``page_labels``, ``audio``) plus any
        non-canonical keys carried by the parts.
    """
    sources = {
        "outline": False,
        "heading_hierarchy": False,
        "page_labels": False,
        "audio": False,
    }
    for part in parts:
        for key, value in part.sources.items():
            if key == _META_SUPPRESSED_KEY:
                continue  # carried separately; merge_structures re-attaches it
            sources[key] = bool(sources.get(key, False)) or bool(value)
    return sources


def _tree_end_hint(parts: list[DocumentStructure]) -> int | None:
    """Derive the document page extent from the merged parts.

    Outline parts stamp their last node with the PDF page count and docling
    parts with the last known page, so the maximum page end/start across all
    parts is the document extent for the merged tree's last node (design §5:
    "last node ends at document page count (outline) or last known page
    (docling)").

    Args:
        parts: The captured parts being merged.

    Returns
    -------
        The page extent, or None when nothing carries a page.
    """
    ends = [
        node.page_end
        for part in parts
        for node in part.nodes
        if node.page_end is not None
    ]
    if ends:
        return max(ends)
    starts = [
        node.page_start
        for part in parts
        for node in part.nodes
        if node.page_start is not None
    ]
    return max(starts) if starts else None


def merge_structures(*parts: DocumentStructure | None) -> DocumentStructure:
    """Merge captured parts into one document tree (design §5).

    Outline nodes win where both sources describe the same region (matched
    by page + normalized title, or by page + number when both carry one);
    docling-only headings attach under the deepest outline node containing
    their page; docling-only chapters fill the tree when no outline exists.
    Page ranges are re-derived from merged tree order — next node start - 1
    at the same-or-shallower level, clamped to never end before a node's own
    start, last node ending at the document extent — so same-page openers
    keep nesting correctly. Node ids stay deterministic; a colliding
    docling-side id (outline ids are emitted first) is disambiguated with a
    deterministic ``-2``/``-3``… suffix, and re-parented ids propagate to the
    subtree's ``parent_id`` links.

    Args:
        *parts: Captured structure parts (any may be None; e.g. the outline
            part from :func:`capture_pdf_outline` and docling heading parts
            from :func:`capture_docling_headings`).

    Returns
    -------
        The merged :class:`DocumentStructure` (sources OR-united,
        ``captured_at`` stamped at merge time). Without any part, an empty
        structure is returned.
    """
    real_parts = [part for part in parts if part is not None]
    if not real_parts:
        return DocumentStructure(source_file="", sources={})
    source_file = next(
        (part.source_file for part in real_parts if part.source_file), ""
    )

    outline_nodes: list[StructureNode] = []
    docling_nodes: list[StructureNode] = []
    for part in real_parts:
        if _is_outline_part(part):
            outline_nodes.extend(part.nodes)
        else:
            docling_nodes.extend(part.nodes)

    if outline_nodes:
        docling_nodes = [
            node for node in docling_nodes if not _outline_covered(node, outline_nodes)
        ]

    pairs = _merge_tree(outline_nodes, docling_nodes)
    ordered_pairs = _flatten_pairs(pairs)
    tree_end = _tree_end_hint(real_parts)

    nodes = _finalize_nodes(ordered_pairs, set(), tree_end)
    merged = DocumentStructure(
        source_file=source_file,
        nodes=nodes,
        sources=_union_sources(real_parts),
        captured_at=datetime.now(UTC).isoformat(),
    )
    # Suppressed ToC-page headings ride the parts' sources payloads; the
    # union above skips the key (its value is not a bool), so the combined
    # record is re-attached here — every part's entries survive the merge.
    _attach_suppressed_meta(
        merged,
        [entry for part in real_parts for entry in _suppressed_entries_of(part)],
    )
    return merged


def _finalize_nodes(
    ordered_pairs: list[tuple[StructureNode, StructureNode | None]],
    used_ids: set[str],
    tree_end: int | None,
) -> list[StructureNode]:
    """Emit the final merged nodes with ids, paths and page ranges settled.

    Args:
        ordered_pairs: ``(node, parent)`` pairs in DFS document order.
        used_ids: Ids already reserved (first writer keeps its id).
        tree_end: Document page extent for the tree's last node.

    Returns
    -------
        Final :class:`StructureNode` list.
    """
    # (node, resolved_id, label, ancestors[(id, label)]) bookkeeping
    entries: list[tuple[StructureNode, str, str, list[tuple[str, str]]]] = []
    parent_stack: list[tuple[StructureNode, str, str]] = []

    for node, parent in ordered_pairs:
        while parent_stack and parent is not parent_stack[-1][0]:
            parent_stack.pop()
        ancestors = [(p_node_id, p_label) for _, p_node_id, p_label in parent_stack]
        resolved_id = _unique_node_id(node.node_id, used_ids)
        label = _node_label(node.kind, node.number, node.title)
        entries.append((node, resolved_id, label, ancestors))
        parent_stack.append((node, resolved_id, label))

    resolved_parent_ids: dict[int, str] = {}
    for node, _node_id, _label, ancestors in entries:
        if ancestors:
            resolved_parent_ids[id(node)] = ancestors[-1][0]

    final: list[StructureNode] = []
    page_ends = _derive_merged_page_ends(ordered_pairs, tree_end)
    for (node, resolved_id, label, ancestors), page_end in zip(
        entries, page_ends, strict=True
    ):
        # Ancestor labels then the node's own label, design §5's
        # "Chapter 1 — Installing > 1.2 > 1.2.3" shape.
        heading_path = " > ".join([*[node_label for _, node_label in ancestors], label])
        parent_id = resolved_parent_ids.get(id(node))
        final.append(
            node.model_copy(
                update={
                    "node_id": resolved_id,
                    "parent_id": parent_id,
                    "heading_path": heading_path,
                    "page_end": page_end,
                }
            )
        )
    return final


def _derive_merged_page_ends(
    ordered_pairs: list[tuple[StructureNode, StructureNode | None]],
    tree_end: int | None,
) -> list[int | None]:
    """Derive page ends for the merged tree from DFS order.

    Args:
        ordered_pairs: ``(node, parent)`` pairs in DFS document order.
        tree_end: Document page extent for the tree's last node.

    Returns
    -------
        One page_end per pair (same order), clamped so a node never ends
        before its own start.
    """
    page_ends: list[int | None] = []
    for index, (node, _parent) in enumerate(ordered_pairs):
        page_start = node.page_start
        if page_start is None:
            page_ends.append(None)
            continue
        page_end: int | None = None
        for follower, _fparent in ordered_pairs[index + 1 :]:
            if follower.level <= node.level:
                follower_start = follower.page_start
                if follower_start is not None:
                    page_end = follower_start - 1
                break
        if page_end is None:
            page_end = tree_end
        if page_end is not None:
            page_end = max(page_start, page_end)
        page_ends.append(page_end)
    return page_ends


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# ToC-listing number recovery (fix-chapter-coverage, D1)
# ---------------------------------------------------------------------------

# The ToC-row shapes the recovery pass matches against (design D1):
# "1 Introduction .... 1", "1.1 Central Management .... 2". Multi-component
# numbers are tried first so "1.1 X" never backtracks into the bare shape;
# the optional trailing dot after the number tolerates punctuated rows
# ("1. Introduction .... 1").
_TOC_ROW_RE = re.compile(
    r"^\s*(?P<num>\d{1,3}(?:\.\d{1,3})+|\d{1,3})(?P<dot>\.?)\s+(?P<rest>\S.*?)\s*$"
)
# The docling-parse space regression also deletes the space AFTER a dotted
# section number ("5.14.2MigrationNetwork") — the same shape the pipeline's
# glued-row scan rescues. Multi-component numbers only, and only with title
# evidence (several tokens or an intra-word case/paren boundary), so version
# strings ("1.2Beta") and single words are never read as rows.
_TOC_ROW_GLUED_RE = re.compile(
    r"^\s*(?P<num>\d{1,3}(?:\.\d{1,3})+)(?P<rest>[A-Z(]\S.*)$"
)
# A dotted number alone on a line ("1.13") is the number half of a row the
# extractor wrapped right after the number; single digits are too often
# prose/table/footer noise to trust.
_TOC_NUMBER_ONLY_RE = re.compile(r"^\s*(?P<num>\d{1,3}(?:\.\d{1,3})+)\.?\s*$")
# Dot-leader + printed page tail: whitespace, then at least one leader glyph
# (dots, middle dots, ellipses, underscores), possibly interleaved with more
# leader glyphs and spaces, then the page digits at end of line. The leader
# run must be whitespace-separated from the title so a title's own dotted
# sub-number never donates a fake page ("2.3 Release 7.2" keeps its "7.2" —
# that dot is glued to the title, not a leader); the required leader glyph
# still keeps a page with no dots at all ("Introduction  12") off this shape
# and on the bare-page path below, where it belongs.
_TOC_PAGE_TAIL_RE = re.compile(
    r"^(?P<title>\S.*?)\s+[.·‥⋯…_][\s.·‥⋯…_]*(?P<page>\d{1,4})\s*$"
)
# Bare printed-page tail, no leader glyphs: a trailing whitespace-separated
# 1-4-digit printed page, the shape of leader-less chapter rows in the wild
# ("1 Introduction 1", "2 Installing Proxmox VE 10"). Only trusted when the
# remaining title still carries at least one alphabetic character, so a
# pure-number rest ("2 4 6") never donates a fake page.
_TOC_BARE_PAGE_TAIL_RE = re.compile(r"^(?P<title>\S.*?)\s+(?P<page>\d{1,4})$")
# Trailing leader/punctuation remnants stripped from parsed row titles.
_TOC_TITLE_TRAILING = " .·‥⋯…_"


class TocListing(NamedTuple):
    """One parsed table-of-contents row (fix-chapter-coverage, D1).

    Attributes:
        number: Normalized numbering token (``"1"``, ``"1.1"``; ``"05.02"``
            normalizes to ``"5.2"``).
        title: Clean row title — numbering token, dot-leader and trailing
            printed page removed, fully-glued titles re-spaced (see
            :func:`_unglue_glued_title`).
        page: The row's printed page number, or None when the row carries
            no page column.
        level: Nesting level from the number's dot components (1 for
            ``"1"``, 2 for ``"1.1"``, …).
    """

    number: str
    title: str
    page: int | None
    level: int


def _unglue_glued_title(title: str) -> str:
    """Re-space a fully-glued CamelCase title for matching.

    Local mirror of the pipeline's ``_pretty_glued_title`` (design D1
    chooses a capture-layer parser over a cross-layer refactor): it fires
    ONLY when the title contains no whitespace at all AND is at least 10
    chars, and splits at lower→upper CamelCase boundaries plus before "("
    after a lowercase letter. Normally-spaced titles pass through
    untouched.

    Args:
        title: A parsed ToC row title.

    Returns
    -------
        The re-spaced title, or the input unchanged when it is not glued.
    """
    t = title.strip()
    if len(t) < 10 or re.search(r"\s", t):
        return t
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    return re.sub(r"(?<=[a-z])\(", " (", spaced)


def _clean_toc_title(title: str) -> str:
    """Collapse a parsed row title and strip trailing leader remnants.

    Args:
        title: The raw title fragment captured before a dot-leader tail.

    Returns
    -------
        The whitespace-collapsed title without trailing dots/leaders.
    """
    return " ".join(title.split()).rstrip(_TOC_TITLE_TRAILING)


def _row_title_and_page(rest: str) -> tuple[str, int | None]:
    """Split a parsed row's rest into its title fragment and printed page.

    Two tail shapes, tried in order:

    * a dot-leader tail (:func:`_TOC_PAGE_TAIL_RE`) — whitespace, a leader
      run, then the page digits (``"Central Management . . . . 2"``);
    * a bare printed-page tail (:func:`_TOC_BARE_PAGE_TAIL_RE`) — a trailing
      whitespace-separated 1-4-digit page with no leader glyphs, the shape
      of leader-less chapter rows (``"Introduction 1"``). Trusted only when
      the remaining title keeps at least one alphabetic character, so a
      pure-number rest never donates a fake page.

    Anything else stays whole with no page: a rest like ``"Release 7.2"``
    (no whitespace before the trailing digits) and one with no trailing
    number at all keep their full text and ``page=None`` — while a rest
    without any alphabetic character at all (``".... 2"``) has no title
    text and yields an empty title, which the caller drops.

    Args:
        rest: A matched ToC row's text after the numbering token.

    Returns
    -------
        ``(title_fragment, page)`` — the raw title fragment (cleaned by the
        caller) and the printed page, or None when the rest carries no
        trusted page tail.
    """
    tail = _TOC_PAGE_TAIL_RE.match(rest)
    if tail is not None:
        return tail.group("title"), int(tail.group("page"))
    bare = _TOC_BARE_PAGE_TAIL_RE.match(rest)
    if bare is not None:
        bare_title = bare.group("title")
        if bare_title and any(ch.isalpha() for ch in bare_title):
            return bare_title, int(bare.group("page"))
    if not any(ch.isalpha() for ch in rest):
        # A letterless rest (leader dots, digits, punctuation only) carries
        # no title text at all — the caller drops the row entirely.
        return "", None
    return rest, None


def _glued_toc_row(line: str) -> re.Match[str] | None:
    """Match the space-glued row shape ("5.14.2MigrationNetwork") or None.

    The docling-parse space regression deletes the space AFTER a dotted
    section number. Mirrors the pipeline's glued-row gate: the title part
    (dot-leader tail removed) must show glue evidence — several tokens or
    an intra-word case/paren boundary — so a single unbroken word
    ("1.2Beta") is never read as a row.

    Args:
        line: One raw text line.

    Returns
    -------
        The glued row match, or None when the shape/gate does not hold.
    """
    match = _TOC_ROW_GLUED_RE.match(line)
    if match is None:
        return None
    tail = _TOC_PAGE_TAIL_RE.match(match.group("rest"))
    title = tail.group("title") if tail else match.group("rest")
    if len(title.split()) > 1 or re.search(r"(?<=[a-z])[A-Z(]", title):
        return match
    return None


def _match_key(title: str) -> str:
    """Normalize a title for listing↔node matching (case-fold, ws-squash).

    Args:
        title: A node or listing title.

    Returns
    -------
        The case-folded, whitespace-collapsed key with trailing
        punctuation/leader remnants stripped.
    """
    return " ".join(title.split()).casefold().rstrip(_TOC_TITLE_TRAILING + ":;")


def _match_squash(title: str) -> str:
    """Glued-variant match key: ALL whitespace removed (case-folded).

    Equals :func:`_match_key` for spaced titles and matches the glued
    spelling of the same words either way around, so a glued node title
    ("InstallingProxmoxVE") still finds its spaced ToC listing.

    Args:
        title: A node or listing title.

    Returns
    -------
        The case-folded, whitespace-free key with trailing punctuation
        stripped.
    """
    return re.sub(r"\s+", "", title).casefold().rstrip(_TOC_TITLE_TRAILING + ":;")


def parse_toc_rows(text: str) -> list[TocListing]:
    """Parse table-of-contents rows out of raw page text (pure).

    Recognizes the design D1 row shapes — ``"1 Introduction .... 1"`` and
    ``"1.1 Central Management .... 2"`` — plus their leader-less chapter-row
    variants (``"1 Introduction 1"``, a bare whitespace-separated trailing
    printed page), page-less rows, wrapped rows (the page column on the
    following unnumbered line, or the number alone on its own line) and the
    docling space-glued number→title junction
    (``"5.14.2MigrationNetwork"``). Prose look-alikes are rejected: list
    items (``"1. Install the package"``), years, bare footer page numbers
    and number-less lines are never rows, and a rest without a trusted page
    tail stays whole (``"2.3 Release 7.2"`` keeps its version number).
    Roman-numeral rows are not recognized (the affected outlines number
    chapters decimally).

    Args:
        text: Raw text — one page's extracted text (or any concatenation);
            no I/O happens here.

    Returns
    -------
        The parsed rows in line order. Rows keep ``page=None`` when their
        page column is absent (tolerated); a wrapped row's title/page merge
        into that single row.
    """
    rows: list[TocListing] = []
    pending: int | None = None  # index of the last page-less row awaiting its page
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        number_only = _TOC_NUMBER_ONLY_RE.match(line)
        if number_only is not None:
            # The number half of a wrapped row; the title/page follow.
            pending = len(rows)
            rows.append(
                TocListing(
                    number=_normalize_number(number_only.group("num")),
                    title="",
                    page=None,
                    level=number_only.group("num").count(".") + 1,
                )
            )
            continue
        row = _TOC_ROW_RE.match(line)
        if row is None:
            row = _glued_toc_row(line)
        if row is not None:
            number = _normalize_number(row.group("num"))
            title_fragment, page = _row_title_and_page(row.group("rest"))
            title = _unglue_glued_title(_clean_toc_title(title_fragment))
            if page is None and row.groupdict().get("dot") and "." not in number:
                # "1. Install the package" — a prose list item, not a row
                # (punctuated rows are only trusted with a page column or a
                # multi-component number).
                pending = None
                continue
            if title:
                rows.append(
                    TocListing(
                        number=number,
                        title=title,
                        page=page,
                        level=number.count(".") + 1,
                    )
                )
                pending = len(rows) - 1 if page is None else None
            else:
                pending = None
            continue
        tail = _TOC_PAGE_TAIL_RE.match(line)
        if tail is not None and pending is not None:
            # Wrapped row: the page column lands on the following unnumbered
            # line ("1.10 Configuring the Network for / Guest Access .... 12").
            fold_title = _clean_toc_title(tail.group("title"))
            if fold_title:
                holder = rows[pending]
                merged_title = _unglue_glued_title(
                    f"{holder.title} {fold_title}".strip()
                )
                rows[pending] = holder._replace(
                    title=merged_title, page=int(tail.group("page"))
                )
        pending = None  # any other content expires the pending wrap
    return rows


# Two consecutive paged pages may lie at most this many pages apart (i.e.
# with up to two page-less pages between them) and still count as one
# contiguous ToC run; a larger gap ends the run, so a body page that
# fabricated paged rows is an outlier, not an extension of the ToC span.
_TOC_RUN_MAX_STEP = 3


def _longest_paged_run(pages: Sequence[int]) -> tuple[int, int]:
    """Find the longest contiguous run of ToC paged pages (pure).

    The ToC page span must be a RUN of pages, never the min/max over every
    page that yielded a paged row: a body page can fabricate paged rows (a
    ``ceph osd crush tree`` example printing ``12 nvme 0.72769 osd.12``), and
    a min/max span would stretch across the whole body and make the span
    exclusion guard drop every real node between the ToC and the outlier.
    Consecutive paged pages up to :data:`_TOC_RUN_MAX_STEP` apart keep the
    run going; a larger gap ends it. Equal-length runs take the earliest.

    Args:
        pages: Distinct 1-based pages that yielded paged rows, sorted
            ascending and non-empty (the caller filters and sorts).

    Returns
    -------
        ``(first_page, last_page)`` of the winning run, inclusive.
    """
    runs: list[list[int]] = [[pages[0]]]
    for page in pages[1:]:
        if page - runs[-1][-1] <= _TOC_RUN_MAX_STEP:
            runs[-1].append(page)
        else:
            runs.append([page])
    best = max(runs, key=lambda run: (len(run), -run[0]))
    return best[0], best[-1]


def _pdf_toc_listings(
    path: Path,
) -> tuple[list[TocListing], tuple[int, int] | None]:
    """Parse the PDF's ToC listings from its native text layer (design D1).

    Reads every page's text through :func:`extract_native_pdf_text`
    (pypdfium2, no docling — the same reader the fast path uses) and parses
    ToC rows per page. The pages that yielded rows carrying a printed page
    column define the ToC page span as their longest contiguous run
    (:func:`_longest_paged_run`) — body pages can fabricate ToC-looking rows
    (command output, running heads), so pages outside that run are dropped
    from the listing set entirely, and page-less rows are kept only inside
    the run.

    Args:
        path: Path to the PDF file.

    Returns
    -------
        ``(listings, toc_page_span)`` — the parsed rows in document order
        and the inclusive 1-based physical page span of the longest
        contiguous run of pages that yielded paged rows (None when no paged
        row exists). Empty listings when the document has no readable text
        layer or no ToC rows. Never raises.
    """
    per_page: list[tuple[int, list[TocListing]]] = []
    try:
        for segment in extract_native_pdf_text(path):
            page = int(segment.get("page") or 0)
            if page <= 0:
                continue
            page_rows = parse_toc_rows(str(segment.get("text") or ""))
            if page_rows:
                per_page.append((page, page_rows))
    except Exception as e:
        logger.warning(
            "ToC listing scan failed for %s (%s: %s); skipping number recovery",
            path,
            type(e).__name__,
            e,
        )
        return [], None
    paged_pages = sorted(
        {
            page
            for page, page_rows in per_page
            if any(row.page is not None for row in page_rows)
        }
    )
    if not paged_pages:
        return [], None
    span = _longest_paged_run(paged_pages)
    listings = [
        row
        for page, page_rows in per_page
        for row in page_rows
        if span[0] <= page <= span[1]
    ]
    return listings, span


# The ToC evidence (listings + page span) depends only on the FILE's text
# layer, never on the docling document — but every capture entry point needs
# it: the dispatcher (suppression + recovery), and each per-window docling
# capture the processor worker produces. One bounded memo per file version
# keeps the text-layer scan to a single pass per (path, mtime, size); entries
# churn naturally (maxsize), and a stale entry is impossible for the same
# file version. Keyed on stat stamps (not the Path) so re-written files
# re-scan and a bounded LRU never pins dead paths.
_TOC_EVIDENCE_CACHE_MAX = 8


@lru_cache(maxsize=_TOC_EVIDENCE_CACHE_MAX)
def _cached_toc_evidence(
    path_str: str, mtime_ns: int, size: int
) -> tuple[tuple[TocListing, ...], tuple[int, int] | None]:
    """Memoized :func:`_pdf_toc_listings` keyed on the file's stat stamps."""
    listings, span = _pdf_toc_listings(Path(path_str))
    return tuple(listings), span


def _toc_evidence(
    path: Path,
) -> tuple[list[TocListing], tuple[int, int] | None]:
    """Return the document's ToC listings + page span, scanned once per version.

    Args:
        path: Path to the PDF file.

    Returns
    -------
        ``(listings, toc_page_span)`` as :func:`_pdf_toc_listings` returns.
    """
    try:
        stat = path.stat()
    except OSError:
        return _pdf_toc_listings(path)
    listings, span = _cached_toc_evidence(str(path), stat.st_mtime_ns, stat.st_size)
    return list(listings), span


def _recovery_number_consistent(
    node: StructureNode,
    number: str,
    by_id: dict[str, StructureNode],
    children: dict[str, list[StructureNode]],
    numbers: dict[str, str | None],
) -> bool:
    """Check that assigning *number* to *node* keeps the tree consistent.

    Two guards back the spec's inheritance rule ("a recovered chapter
    number is the leading component of its descendants' recovered section
    numbers") and its no-wrong-number rule:

    * the node's parent — when numbered and not a part (parts restart
      numbering by design, see :func:`_detect_part_openers`) — must equal
      the number or be its leading prefix, and
    * every child already carrying a number (parsed, or recovered earlier
      in this same walk) must sit consistently under the recovered number
      (a chapter whose sections were parsed as "5.x" is never renumbered
      "3").

    An unnumbered parent constrains nothing: the child's ToC-derived number
    stays authoritative even where the parent's row was unmatched.

    Args:
        node: The candidate node.
        number: The candidate recovered number.
        by_id: All tree nodes by ``node_id`` (parent-kind lookup).
        children: ``parent_id`` → child nodes.
        numbers: The live number per ``node_id`` — parsed numbers plus any
            recovered earlier in this walk (parents precede children).

    Returns
    -------
        True when the assignment cannot contradict any existing number.
    """
    parent = by_id.get(node.parent_id) if node.parent_id else None
    parent_number = numbers.get(node.parent_id) if node.parent_id else None
    if (
        parent is not None
        and parent.kind != "part"
        and parent_number is not None
        and number != parent_number
        and not number.startswith(parent_number + ".")
    ):
        return False
    for child in children.get(node.node_id, ()):
        child_number = numbers.get(child.node_id)
        if child_number is None:
            continue
        if child_number != number and not child_number.startswith(number + "."):
            return False
    return True


def _refresh_derived_pages(
    listings: Sequence[TocListing],
    effective_pages: list[int | None],
    offsets: Sequence[int],
) -> None:
    """Fill label-unmapped listings' physical pages from derived offsets (D5).

    In place: every row whose /PageLabels mapping was unusable gets
    ``printed page + median(offsets)`` — the offset the walk has actually
    observed between matched listings' printed pages and their nodes'
    physical pages, never an assumed constant. Rows without a printed page
    stay ``None`` (their bound comes from the neighbors' bracket); rows the
    labels already mapped are never touched — the document's own labels win.

    Args:
        listings: The parsed ToC rows, in document order.
        effective_pages: The working physical page per row (mutated).
        offsets: The observed ``node page - printed page`` samples so far.
    """
    if not offsets:
        return
    offset = int(statistics.median(offsets))
    for index, row in enumerate(listings):
        if effective_pages[index] is None and row.page is not None:
            effective_pages[index] = row.page + offset


def _recovery_number_collides(
    node: StructureNode,
    number: str,
    siblings: dict[str | None, list[str]],
    numbers: dict[str, str | None],
    assignments: dict[str, str],
) -> bool:
    """Whether *number* is already held by one of *node*'s same-scope peers.

    The collision refusal (fix-chat-session-integrity D5): when this walk
    has already recovered *number* for a sibling (same ``parent_id``, root
    included), a second assignment is refused rather than doubled — the
    stored tree never carries two nodes with the same RECOVERED number, even
    where suppression missed a leftover ToC-span ghost and the walk would
    otherwise stamp both. Only recovered-this-pass numbers collide: parsed
    numbers are never overwritten and anthology part-restarts (the parsed
    ``1`` of another part) are not this pass's doing.

    Args:
        node: The candidate node.
        number: The candidate recovered number.
        siblings: ``parent_id`` → child ``node_id`` list (None key = roots).
        numbers: The live number per ``node_id`` (parsed + recovered so far).
        assignments: The ``node_id`` → number assignments made this walk.

    Returns
    -------
        True when assigning would double a recovered number in scope.
    """
    for sibling_id in siblings.get(node.parent_id, ()):
        if sibling_id == node.node_id:
            continue
        if numbers.get(sibling_id) == number and sibling_id in assignments:
            return True
    return False


# Page bound for ToC number recovery (D1 refinement): a listing's printed
# page, mapped through the document's /PageLabels, must land within this
# many physical pages of the node's page_start. Real skew between a ToC row
# and the body heading it describes is 1-2 pages (heading attribution at
# page boundaries, label rounding); the far-ahead jumps the bound exists to
# reject are 100+ pages away, so 3 absorbs the noise and stays decisive.
_TOC_PAGE_BOUND_TOLERANCE = 3

# Printed-page labels that map to physical pages are plain decimal runs
# ("1", "12"); roman ("iii") or lettered ("A-1") labels carry no body pages
# and are ignored (the bound fails open around them).
_TOC_DECIMAL_LABEL_RE = re.compile(r"\d{1,4}")


def _printed_to_physical(
    page_labels: Sequence[PageLabelRange], printed: int
) -> int | None:
    """Map a ToC row's printed page to a physical page via /PageLabels.

    Walks the document's label runs (page_start ascending): a decimal run
    whose first page carries label *L* maps printed page *P* to
    ``page_start + (P - L)`` when that physical page lies inside the run.
    Roman or lettered runs carry no body pages and are skipped.

    Args:
        page_labels: The document's page-label runs.
        printed: The printed (label) page a ToC row advertises.

    Returns
    -------
        The 1-based physical page, or None when no decimal label run covers
        the printed page.
    """
    for label_range in page_labels:
        match = _TOC_DECIMAL_LABEL_RE.fullmatch(str(label_range.label).strip())
        if match is None:
            continue  # roman/lettered front matter carries no body pages
        physical = label_range.page_start + (printed - int(match.group(0)))
        if physical < label_range.page_start:
            continue  # printed page precedes this run's first label
        if physical > label_range.page_end:
            continue  # printed page beyond this run
        return physical
    return None


def _mapped_listing_pages(
    listings: Sequence[TocListing],
    page_labels: Sequence[PageLabelRange] | None,
) -> list[int | None]:
    """Physical page per listing (None where page-less or unmappable).

    Args:
        listings: The parsed ToC rows, in document order.
        page_labels: The document's page-label runs, or None/empty when the
            document carries no /PageLabels (the bound then fails open for
            every listing).

    Returns
    -------
        One entry per listing: the printed page mapped to a physical page,
        or None for a page-less row, a row no decimal label run covers, or
        every row when *page_labels* is empty.
    """
    if not page_labels:
        return [None] * len(listings)
    return [
        _printed_to_physical(page_labels, row.page) if row.page is not None else None
        for row in listings
    ]


def _page_bound_allows(
    mapped_pages: Sequence[int | None],
    index: int,
    node_page: int | None,
    tolerance: int = _TOC_PAGE_BOUND_TOLERANCE,
) -> bool:
    """Whether the listing at *index* may number a node sitting at *node_page*.

    A mapped row allows the match only within *tolerance* physical pages of
    the node. A page-less (or unmappable) row interpolates: its nearest
    mappable ToC neighbors bracket the page it would have carried, so the
    node must lie in ``[prev - tolerance, next + tolerance]`` (a missing
    side stays unbounded). Anything unboundable fails OPEN — a page-less
    node, a document without page labels, a row with no mappable neighbors —
    so recovery never gets worse than the order-only rule it refines.

    Args:
        mapped_pages: Physical page per listing (:func:`_mapped_listing_pages`).
        index: The candidate listing's index.
        node_page: The candidate node's ``page_start`` (None = unboundable).
        tolerance: Allowed ``|physical - page_start|`` distance.

    Returns
    -------
        True when the match may proceed.
    """
    if node_page is None:
        return True  # nothing to bound against — order-only (fail open)
    low = high = mapped_pages[index]
    if low is None:
        # Page-less or unmappable row: bracket it from its nearest mappable
        # ToC neighbors — its position between them pins the page it carries.
        for before in range(index - 1, -1, -1):
            mapped = mapped_pages[before]
            if mapped is not None:
                low = mapped
                break
        for after in range(index + 1, len(mapped_pages)):
            mapped = mapped_pages[after]
            if mapped is not None:
                high = mapped
                break
        if low is None and high is None:
            return True  # nothing mappable nearby — order-only (fail open)
    if low is not None and node_page < low - tolerance:
        return False
    return not (high is not None and node_page > high + tolerance)


def recover_chapter_numbers(
    structure: DocumentStructure,
    listings: Sequence[TocListing],
    *,
    toc_page_span: tuple[int, int] | None = None,
) -> DocumentStructure:
    """Recover missing chapter/section numbers from ToC listings (D1).

    The post-merge numbering pass: number-less nodes are matched against
    the document's own ToC listings and gain the listing's number, so a
    tree captured from a number-less PDF outline comes out fully numbered.
    Matching rules (spec):

    * the normalized title (case-fold + whitespace-squash, plus the
      glued-variant squash for the docling space regression) must match
      exactly ONE unused listing whose nesting level equals the node's
      level and which sits after the last consumed listing — document
      order and nesting level must agree;
    * the match must also sit where the ToC says it does: the listing's
      printed page, mapped through the document's /PageLabels, lies within
      :data:`_TOC_PAGE_BOUND_TOLERANCE` physical pages of the node's
      ``page_start`` — the range-consistency test (D5): the mapped page must
      be consistent with the node's physical page range. Where the labels
      yield no mapping for a row, the printed→physical offset is DERIVED as
      the median offset of the listings already matched in this walk
      (:func:`_refresh_derived_pages`) instead of assuming a constant, and a
      row with neither evidence fails open to the order-only rule
      (:func:`_page_bound_allows`; a page-less row takes an interpolated
      bracket from its nearest mappable ToC neighbors; page-less nodes fail
      open). Without it a generic title ("Configuration") matches a
      far-ahead chapter's identically named row and the cursor jump starves
      every chapter whose listing lies in between;
    * a recovered number this walk already gave a same-scope sibling is
      refused rather than doubled (:func:`_recovery_number_collides`) — the
      tree never carries two nodes with the same recovered number, even
      where a leftover ToC-span ghost escaped suppression;
    * one listing assigns at most one node; ambiguous or unmatched nodes
      stay number-less;
    * parsed numbers always win — numbered nodes are never touched;
    * assignments that would contradict a numbered parent or numbered
      children are rejected (:func:`_recovery_number_consistent`);
    * ``part``/``segment`` nodes never take ToC numbers.

    Re-running the pass over its own output is a no-op: recovered nodes
    carry their numbers (skipped), and the page bound rejects the far-ahead
    re-assignments an order-only search would otherwise produce on the
    leftover number-less nodes. A tree recovery could not fully number keeps
    gaining page-valid numbers across runs until the fixpoint: a node whose
    row was passed by an earlier assignment (e.g. a same-page shallower
    sibling walked first by the storage load order) stays number-less in
    that run, and once the passing node carries its number the cursor no
    longer advances past the passed row, so the next run assigns it.

    Node ids and parent links are unchanged (ids are the stable storage
    keys); ``heading_path`` is recomputed so labels reflect the recovered
    numbers, and ``sources`` gains ``"toc_number_recovery": True`` when at
    least one node was numbered. Nodes whose ``page_start`` lies inside
    *toc_page_span* (the ToC's own physical page span, when known) are
    excluded — headings captured from ToC-page text must never number
    themselves.

    Args:
        structure: The merged structure (nodes in document order); its
            ``page_labels`` map printed ToC pages to physical pages for the
            page bound (empty labels fail open).
        listings: The parsed ToC rows, in document order.
        toc_page_span: Inclusive 1-based physical page span the rows were
            found on, or None when unknown.

    Returns
    -------
        A new :class:`DocumentStructure` with the recovered numbers (the
        input unchanged when no node could be numbered). Pure: no I/O.
    """
    if not listings or not structure.nodes:
        return structure
    nodes = list(structure.nodes)
    by_id = {node.node_id: node for node in nodes}
    children: dict[str, list[StructureNode]] = {}
    for node in nodes:
        if node.parent_id:
            children.setdefault(node.parent_id, []).append(node)
    listing_keys = [
        (_match_key(row.title), _match_squash(row.title)) for row in listings
    ]
    mapped_pages = _mapped_listing_pages(listings, structure.page_labels or None)
    # D5: the label mapping is preferred evidence; where it leaves a row
    # unmapped, the offset the walk itself observes between matched listings'
    # printed pages and their nodes' physical pages fills the gap (median of
    # the samples so far — derived, never assumed).
    effective_pages = list(mapped_pages)
    offsets: list[int] = []
    siblings: dict[str | None, list[str]] = {}
    for node in nodes:
        siblings.setdefault(node.parent_id, []).append(node.node_id)
    span_low, span_high = toc_page_span or (0, 0)
    cursor = -1
    assignments: dict[str, str] = {}
    numbers: dict[str, str | None] = {node.node_id: node.number for node in nodes}
    for node in nodes:
        if node.number is not None or node.kind in ("part", "segment"):
            continue  # parsed numbers always win; parts/segments never match
        page = node.page_start
        if page is None or span_low <= page <= span_high:
            continue  # inside the ToC's own page span, or pageless
        key, squash = _match_key(node.title), _match_squash(node.title)
        candidates = [
            index
            for index in range(cursor + 1, len(listings))
            if listings[index].level == node.level
            and (listing_keys[index][0] == key or listing_keys[index][1] == squash)
            and _page_bound_allows(effective_pages, index, page)
        ]
        if len(candidates) != 1:
            continue  # unmatched or ambiguous — stays number-less (spec)
        index = candidates[0]
        number = listings[index].number
        if _recovery_number_collides(node, number, siblings, numbers, assignments):
            continue  # the walk already recovered this number in scope (D5)
        if not _recovery_number_consistent(node, number, by_id, children, numbers):
            continue
        assignments[node.node_id] = number
        numbers[node.node_id] = number
        printed = listings[index].page
        if printed is not None:
            offsets.append(page - printed)
            _refresh_derived_pages(listings, effective_pages, offsets)
        cursor = index
    if not assignments:
        return structure

    labels = {
        node.node_id: _node_label(
            node.kind, assignments.get(node.node_id, node.number), node.title
        )
        for node in nodes
    }
    new_nodes: list[StructureNode] = []
    for node in nodes:
        final_number: str | None = assignments.get(node.node_id, node.number)
        chain: list[str] = []
        seen: set[str] = set()
        cursor_id: str | None = node.node_id
        while cursor_id is not None and cursor_id not in seen:
            seen.add(cursor_id)
            chain.append(labels[cursor_id])
            parent = by_id.get(cursor_id)
            cursor_id = parent.parent_id if parent is not None else None
        heading_path = " > ".join(reversed(chain))
        if final_number == node.number and heading_path == node.heading_path:
            new_nodes.append(node)
        else:
            new_nodes.append(
                node.model_copy(
                    update={"number": final_number, "heading_path": heading_path}
                )
            )
    return structure.model_copy(
        update={
            "nodes": new_nodes,
            "sources": {**structure.sources, "toc_number_recovery": True},
        }
    )


def _recover_numbers_from_document_toc(
    structure: DocumentStructure,
    path: Path,
    *,
    listings: Sequence[TocListing] | None = None,
    toc_page_span: tuple[int, int] | None = None,
) -> DocumentStructure:
    """Wire the D1 recovery pass into the capture flow (task 1.3).

    Parses the document's ToC listings from its native text layer
    (:func:`_pdf_toc_listings`) and runs :func:`recover_chapter_numbers`
    over the freshly merged tree — the single call site between
    :func:`merge_structures` and persistence. Never raises and never
    degrades the tree: any failure returns the structure unchanged, so
    ingest keeps today's behavior.

    Args:
        structure: The merged structure tree.
        path: Path to the source PDF (its text layer is the ToC source).
        listings: Precomputed ToC rows to reuse (the dispatcher scans once
            and shares the evidence with the D4 ghost-suppression pass);
            scanned here when None.
        toc_page_span: The precomputed ToC page span accompanying *listings*.

    Returns
    -------
        The structure with recovered numbers, or the input unchanged when
        no listings exist or recovery failed.
    """
    try:
        if listings is None:
            listings, toc_page_span = _toc_evidence(path)
        if not listings:
            return structure
        return recover_chapter_numbers(structure, listings, toc_page_span=toc_page_span)
    except Exception as e:
        logger.warning(
            "ToC number recovery failed for %s (%s: %s); keeping captured numbers",
            path,
            type(e).__name__,
            e,
        )
        return structure


# Audio capture (design §5, lane 1b) — ASR timestamps → segment nodes
# ---------------------------------------------------------------------------

# Node titles are whitespace-collapsed excerpt prefixes; a word-aligned cut
# keeps them matching as chunk-text anchors.
_AUDIO_TITLE_MAX_CHARS = 60

_SEGMENT_ID_RE = re.compile(r"^seg(\d+)$")


def _item_time_span(item: Any) -> tuple[float, float] | None:
    """Extract the ``(start, end)`` seconds an ASR item covers, or None.

    Docling ASR output attaches timestamps to each transcribed segment as
    ``TrackSource(start_time, end_time, …)`` entries on the item's
    ``source`` list — not on ``prov`` (verified against docling 2.138.0's
    ``asr_transcriber``). Fabricated/shaped items are read the same way;
    anything without readable numeric bounds yields None.
    """
    sources = getattr(item, "source", None) or []
    starts: list[float] = []
    ends: list[float] = []
    for source in sources:
        start = getattr(source, "start_time", None)
        end = getattr(source, "end_time", None)
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            starts.append(float(start))
            ends.append(float(end))
    if not starts:
        return None
    return (min(starts), max(ends))


def _audio_title(text: str) -> str:
    """Collapse an ASR excerpt into a node title, cut on a word boundary."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _AUDIO_TITLE_MAX_CHARS:
        return collapsed
    cut = collapsed[:_AUDIO_TITLE_MAX_CHARS]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut


def capture_audio_structure(docling_doc: Any, path: Path) -> DocumentStructure | None:
    """Capture audio structure from a docling ASR document (design §5).

    Emits one ``segment`` node per timestamped ASR segment (``seg01``… ids,
    excerpt titles, ``t_start``/``t_end`` in seconds, no pages). Degrades:

    * timestamped segments exist → one node each, ordered by start time;
    * text exists but no item carries timestamps → a single whole-document
      segment (``t_start=0.0``, open end) — ingest must not fail;
    * no text at all, or *docling_doc* is None → ``None``.

    Args:
        docling_doc: Parsed docling ASR document (or any object exposing a
            ``texts`` item list).
        path: Path to the source file (becomes ``source_file``).

    Returns
    -------
        The audio :class:`DocumentStructure`, or ``None`` when nothing
        usable was captured. Never raises.
    """
    try:
        return _capture_audio_structure(docling_doc, path)
    except Exception as e:
        logger.warning(
            "Audio structure capture failed for %s (%s: %s); document has no tree",
            path,
            type(e).__name__,
            e,
        )
        return None


def _capture_audio_structure(docling_doc: Any, path: Path) -> DocumentStructure | None:
    """Build the audio node list (single failure domain, see above)."""
    if docling_doc is None:
        return None
    timestamped: list[tuple[float, float, str]] = []
    untimed: list[str] = []
    for item in getattr(docling_doc, "texts", None) or []:
        text = " ".join(str(getattr(item, "text", "") or "").split())
        if not text:
            continue
        span = _item_time_span(item)
        if span is not None:
            timestamped.append((span[0], span[1], text))
        else:
            untimed.append(text)
    timestamped.sort(key=lambda segment: (segment[0], segment[1]))

    if timestamped:
        nodes = [
            StructureNode(
                node_id=f"seg{index + 1:02d}",
                parent_id=None,
                kind="segment",
                level=1,
                number=None,
                title=_audio_title(text),
                page_start=None,
                page_end=None,
                t_start=start,
                t_end=end,
                heading_path=f"Segment {index + 1:02d}",
            )
            for index, (start, end, text) in enumerate(timestamped)
        ]
    elif untimed:
        # No timestamps anywhere: one whole-document segment, open end.
        nodes = [
            StructureNode(
                node_id="seg01",
                parent_id=None,
                kind="segment",
                level=1,
                number=None,
                title=_audio_title(untimed[0]),
                page_start=None,
                page_end=None,
                t_start=0.0,
                t_end=None,
                heading_path="Segment 01",
            )
        ]
    else:
        return None

    return DocumentStructure(
        source_file=str(path),
        nodes=nodes,
        sources={"audio": True},
    )


# ---------------------------------------------------------------------------
# Audio topic segmentation (design §5) — LLM titles for ≤20 windows
# ---------------------------------------------------------------------------

_TOPIC_WINDOW_TRANSCRIPT_CHARS = 4000
_TOPIC_LINE_CHARS = 400
_TOPIC_TITLE_MAX_CHARS = 80

_TOPIC_PROMPT = (
    "You label topics in a transcribed recording.\n"
    "Below is one window of the transcript with approximate timestamps.\n"
    "Reply with ONLY a short topic title (at most 6 words, no quotes, no "
    "punctuation) for what this part of the recording is about.\n\n"
    "Transcript:\n{transcript}\n"
)


def audio_topic_segments(
    tree: DocumentStructure,
    texts: Sequence[str],
    *,
    llm: Any | None = None,
    max_windows: int = 20,
) -> list[AudioSegment]:
    """Topic-segment an audio tree's timeline with an LLM (design §5).

    Timestamped segment nodes are bucketed — in time order — into at most
    *max_windows* windows; each window's transcript slice (chunk/segment
    texts mapped onto the time axis by proportional character position — a
    documented uniform speech-rate assumption) is sent to the LLM in one
    ``generate`` call, and the reply becomes the title of every
    ``AudioSegment`` row built from that window's nodes.

    Args:
        tree: The captured audio tree (segment nodes with ``t_start``).
        texts: Chunk or segment texts in reading order, mapped onto the
            time axis by cumulative character position.
        llm: LLM provider exposing ``generate(prompt) -> str``; None (or
            any failure below) yields no segments.
        max_windows: Upper bound on LLM calls (design: ≤20).

    Returns
    -------
        One :class:`AudioSegment` per timestamped segment node, in time
        order, with its window's title (None when the window had no
        transcript). Empty when there is nothing to segment, no LLM, or any
        LLM/window failure — ingest never fails here.
    """
    if llm is None or max_windows < 1:
        return []
    timed: list[tuple[StructureNode, float]] = []
    for node in tree.nodes:
        if node.kind == "segment" and node.t_start is not None:
            timed.append((node, node.t_start))
    if not timed:
        return []
    try:
        return _audio_topic_segments(timed, texts, llm, max_windows)
    except Exception as e:
        logger.warning("Audio topic segmentation failed (%s: %s)", type(e).__name__, e)
        return []


def _audio_topic_segments(
    timed: list[tuple[StructureNode, float]],
    texts: Sequence[str],
    llm: Any,
    max_windows: int,
) -> list[AudioSegment]:
    """Bucket the timed nodes, ask the LLM once per window, build the rows.

    *timed* carries ``(node, t_start)`` pairs with the start time already
    narrowed to ``float`` (the public wrapper filtered ``None`` away).
    """
    ordered = sorted(
        timed,
        key=lambda item: (
            item[1],
            item[0].t_end if item[0].t_end is not None else item[1],
        ),
    )
    spans = _map_texts_to_time(ordered, texts)
    window_count = max(1, min(max_windows, len(ordered)))
    bucket_size = -(-len(ordered) // window_count)  # ceil division
    rows: list[AudioSegment] = []
    fallback_id = 0
    for start in range(0, len(ordered), bucket_size):
        bucket = ordered[start : start + bucket_size]
        window_start = bucket[0][1]
        window_end = max(
            node.t_end if node.t_end is not None else t_start
            for node, t_start in bucket
        )
        title = _topic_title(
            llm, _window_transcript(spans, texts, window_start, window_end)
        )
        for node, t_start in bucket:
            fallback_id += 1
            rows.append(
                AudioSegment(
                    seg_id=_parse_segment_id(node.node_id) or fallback_id,
                    t_start=t_start,
                    t_end=node.t_end if node.t_end is not None else t_start,
                    title=title,
                )
            )
    return rows


def _map_texts_to_time(
    timed: Sequence[tuple[StructureNode, float]],
    texts: Sequence[str],
) -> list[tuple[float, float]]:
    """Map texts onto the nodes' overall time span by character position.

    Uniform speech-rate assumption (documented): cumulative character
    position maps linearly onto ``[min t_start, max t_end]``. Good enough to
    place transcript windows; never used for retrieval filters.
    """
    t_min = min(t_start for _, t_start in timed)
    t_max = max(
        node.t_end if node.t_end is not None else t_start for node, t_start in timed
    )
    span = max(t_max - t_min, 1e-6)
    total = sum(len(text) for text in texts)
    if total <= 0:
        return [(t_min, t_min) for _ in texts]
    spans: list[tuple[float, float]] = []
    position = 0
    for text in texts:
        start = t_min + (position / total) * span
        position += len(text)
        end = t_min + (position / total) * span
        spans.append((start, end))
    return spans


def _window_transcript(
    spans: Sequence[tuple[float, float]],
    texts: Sequence[str],
    window_start: float,
    window_end: float,
) -> str:
    """Join the texts overlapping ``[window_start, window_end]`` with stamps."""
    lines: list[str] = []
    used = 0
    for (start, end), text in zip(spans, texts, strict=True):
        if end < window_start or start > window_end:
            continue
        snippet = " ".join(str(text).split())
        if not snippet:
            continue
        line = f"[{start:.1f}s] {snippet[:_TOPIC_LINE_CHARS]}"
        if used + len(line) > _TOPIC_WINDOW_TRANSCRIPT_CHARS:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def _topic_title(llm: Any, transcript: str) -> str | None:
    """One LLM call per window; returns the cleaned title (None when empty)."""
    if not transcript:
        return None
    prompt = _TOPIC_PROMPT.format(transcript=transcript)
    raw = " ".join(
        str(llm.generate(prompt, temperature=0.2, max_tokens=64) or "").split()
    )
    title = raw.strip("\"'“”‘’ .")[:_TOPIC_TITLE_MAX_CHARS]  # noqa: RUF001
    return title or None


def _parse_segment_id(node_id: str) -> int | None:
    """Parse ``segNN`` node ids into their 1-based segment number."""
    match = _SEGMENT_ID_RE.match(node_id or "")
    return int(match.group(1)) if match else None


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _merged_docling_part(
    docling_doc: Any,
    path: Path,
    *,
    toc_listings: Sequence[TocListing] | None = None,
    toc_page_span: tuple[int, int] | None = None,
) -> DocumentStructure | None:
    """Normalize the docling input into one docling structure part.

    Accepts (design §6's ``docling_doc`` is deliberately ``Any``):

    * ``None`` — nothing to capture,
    * a parsed docling document,
    * a sequence of parsed docling documents (page-windowed conversion),
    * an already-captured docling part (:class:`DocumentStructure`), or
    * a sequence of those parts (per-window capture, as the processor worker
      produces).

    Args:
        docling_doc: Any of the shapes above.
        path: Path to the source file (becomes ``source_file``).
        toc_listings: Precomputed ToC rows forwarded to
            :func:`capture_docling_headings` for the D4 ghost-suppression
            pass (raw-doc candidates only; already-captured parts carry
            their own record).
        toc_page_span: The precomputed ToC page span accompanying
            *toc_listings*.

    Returns
    -------
        One merged docling part, or None when nothing was captured.
    """
    if docling_doc is None:
        return None
    candidates: list[Any] = (
        list(docling_doc) if isinstance(docling_doc, (list, tuple)) else [docling_doc]
    )
    parts: list[DocumentStructure] = []
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, DocumentStructure):
            parts.append(candidate)
            continue
        captured = capture_docling_headings(
            candidate,
            path,
            toc_listings=toc_listings,
            toc_page_span=toc_page_span,
        )
        if captured is not None:
            parts.append(captured)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return merge_structures(*parts)


def capture_structure(
    path: Path, docling_doc: Any = None, file_type: str = ""
) -> DocumentStructure | None:
    """Capture one document's structure tree (the single ingest capture point).

    PDFs get the outline + ``/PageLabels`` plus the docling heading merge;
    other parseable documents get docling headings only; audio documents
    are captured from their ASR document when one reaches the dispatcher
    (task 10), degrading to ``None`` without one. **Never raises**: any
    failure is caught, warned, and reported as ``None`` so ingest proceeds
    and the document simply has no tree (design §5 failure posture).

    Args:
        path: Path to the source file (unresolved — ``str(path)`` becomes the
            tree key and MUST equal the qdrant payload ``source_file``).
        docling_doc: Parsed docling document(s) or pre-captured docling
            part(s) — see :func:`_merged_docling_part` for the accepted
            shapes. ``None`` for fast-path extractions with no docling
            document.
        file_type: The ingest file-type hint (``"pdf"``, ``"audio"``, …) as
            produced by ``get_file_type``; inferred from the suffix when
            empty.

    Returns
    -------
        The captured :class:`DocumentStructure`, or ``None`` when nothing
        usable was captured (treeless documents, audio without an ASR
        document, or any failure).
    """
    try:
        resolved_type = (file_type or "").lower()
        suffix = path.suffix.lower()
        is_pdf = resolved_type == "pdf" or (not resolved_type and suffix == ".pdf")
        is_audio = resolved_type == "audio"
        if not resolved_type and suffix in _audio_suffixes():
            is_audio = True
        if is_audio:
            # Lane 1b audio capture (task 10): ASR timestamps → segment
            # nodes. Degrades to None when no ASR document reaches this
            # point (the real ingest wiring releases the ASR document after
            # extraction today) or nothing usable was captured; ingest
            # continues treeless either way.
            return capture_audio_structure(docling_doc, path)

        if is_pdf:
            # One ToC-evidence scan serves BOTH the D4 ghost suppression
            # (inside the docling heading capture) and the D1/D5 number
            # recovery below — the dispatcher precomputes and reuses it.
            toc_listings, toc_page_span = _toc_evidence(path)
            outline_part = capture_pdf_outline(path)
            labels = capture_page_labels(path)
            docling_part = _merged_docling_part(
                docling_doc,
                path,
                toc_listings=toc_listings,
                toc_page_span=toc_page_span,
            )
            merged = merge_structures(outline_part, docling_part)
            # /PageLabels go on BEFORE the recovery pass: its page bound maps
            # ToC printed pages to physical pages through them (D1
            # refinement; label-less documents fail open to order-only).
            merged.page_labels = labels
            merged.sources["page_labels"] = bool(labels)
            # fix-chapter-coverage (D1): recover chapter/section numbers for
            # number-less nodes from the document's own ToC listings, before
            # persistence. Never raises; a no-listing document is unchanged.
            merged = _recover_numbers_from_document_toc(
                merged, path, listings=toc_listings, toc_page_span=toc_page_span
            )
            return merged if (merged.nodes or labels) else None

        docling_part = _merged_docling_part(docling_doc, path)
        if docling_part is None:
            return None
        merged = merge_structures(docling_part)
        return merged if merged.nodes else None
    except Exception as e:
        logger.warning(
            "Structure capture failed for %s (%s: %s); document has no tree",
            path,
            type(e).__name__,
            e,
        )
        return None


def _audio_suffixes() -> frozenset[str]:
    """Resolve the audio suffix set (docling_factory's, with a local fallback).

    Returns
    -------
        The audio file suffixes the ingest pipeline routes to ASR.
    """
    try:
        from secondbrain.document.docling_factory import _AUDIO_SUFFIXES

        return _AUDIO_SUFFIXES
    except Exception:
        return _AUDIO_SUFFIXES_FALLBACK
