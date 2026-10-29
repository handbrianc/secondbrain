"""Pure chunk-assembly transforms — no docling, no I/O, no storage.

Contains the algorithmic core of segment→chunk transformation: merging
small segments, detecting titles, producing overlapping word-aligned chunks,
and deduplicating by SHA256 of normalized text.

Exports:
    DEFAULT_MIN_SEGMENT_SIZE: Minimum characters before a segment stands alone.
    chunk_segments: Transform list[Segment] → list[dict] with overlap.
    deduplicate_segments: Dedupe by SHA256-normalized text, attach metadata.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, NotRequired

from typing_extensions import TypedDict

from secondbrain.document.protocols import Segment

ElementTypeLiteral = Literal[
    "navigation",
    "heading",
    "toc_entry",
    "caption",
    "body",
    "table_row",
    "table_caption",
]


_LABEL_TO_ELEMENT_TYPE: dict[str, ElementTypeLiteral] = {
    "title": "heading",
    "section_header": "heading",
    "document_index": "toc_entry",
    "page_header": "navigation",
    "page_footer": "navigation",
    "caption": "caption",
    "text": "body",
    "paragraph": "body",
    "list_item": "body",
    "footnote": "body",
    "reference": "body",
    "code": "body",
    "formula": "body",
    "chart": "body",
    "form": "body",
    "marker": "body",
    "key_value_region": "body",
    "checkbox_selected": "body",
    "checkbox_unselected": "body",
    "empty_value": "body",
    "field_region": "body",
    "field_heading": "body",
    "field_item": "body",
    "field_key": "body",
    "field_value": "body",
    "field_hint": "body",
    "handwritten_text": "body",
    "grading_scale": "body",
    "picture": "body",
    "table": "body",
}


def docling_item_label(item: object) -> str | None:
    """
    Return the raw docling label string for *item*, if it exposes one.

    Works on any object carrying a ``label`` attribute whose value is either a
    docling ``DocItemLabel`` enum (read via ``.value``) or already a plain
    string. Label-less items (fast-text path, plain-text files) return None so
    callers fall back to the statistical classifier.

    Parameters
    ----------
    item : object
        A docling text item (or any object); never raises on missing label.

    Returns
    -------
        The label string, or None when the item has no usable label.
    """
    label = getattr(item, "label", None)
    if label is None:
        return None
    value = getattr(label, "value", label)
    return value if isinstance(value, str) else None


def label_to_element_type(label: str | None) -> ElementTypeLiteral | None:
    """
    Map a raw docling item label to an :class:`ElementTypeLiteral` role.

    The parser's layout model is authoritative: a label present in the mapping
    decides the role outright. Unknown or missing labels return None so callers
    fall back to :func:`classify_chunk_role` statistics, keeping the mapping
    forward-compatible with future docling label sets.

    Parameters
    ----------
    label : str | None
        Raw docling label value (e.g. ``"section_header"``), or None.

    Returns
    -------
        The element type for the label, or None when unmapped.
    """
    if label is None:
        return None
    return _LABEL_TO_ELEMENT_TYPE.get(label)


def classify_chunk_role(
    text: str,
    seg_count: int,
    total_segs: int,
    is_likely_title: bool,
    *,
    is_merged_segment: bool = False,
    source_text: str | None = None,
) -> ElementTypeLiteral:
    """
    Classify chunk by structural role using only statistical signals.

    Thresholds are document-universal (char density, whitespace ratio, dot-chain density).

    Section-number-prefixed text (e.g. "11.18 Configuring the Autostart
    Service") classifies as ``heading`` only while the chunk is a single
    heading-only segment: the former blanket ``body`` downgrade is gone
    (openspec add-structure-aware-ingestion task 7, design §9 trap 1), but merged
    multi-segment openers (title + body accumulated by the merge policy)
    keep ``body`` so chapter-content consumers (e.g. summarizer.py's
    ``chunk_role in ("body", "caption")`` filter) lose no content — merged
    chunks fall through to the statistical signals below. The chunker's
    merge path passes the provenance recorded by ``_merge_segments``; the
    streaming ingestor paths classify raw single segments. Unlabeled page
    segments must also pass the heading-only check. Roles never affect the
    merge policy, so chunk text streams stay byte-identical (design §7 hard constraint).

    Args:
        text: Chunk text (already stripped).
        seg_count: Zero-based position of the chunk's source segment in the
            segment list (drives the leading-sliver navigation heuristic;
            NOT a merge count).
        total_segs: Total number of segments in the list.
        is_likely_title: Whether the caller's inline heuristic considers the
            text a title (dotted text never qualifies there).
        is_merged_segment: Whether the chunk's source segment was produced by
            merging ≥2 raw extraction segments (``_merge_segments`` joins
            them with a space). ``True`` disables the dotted→``heading``
            guard so merged openers keep ``body``.
        source_text: Full source segment before chunk splitting, when available.
            Prevents a truncated page opener from being treated as a heading.
    """
    if is_likely_title:
        pos = seg_count / max(total_segs, 1)
        if pos < 0.025:
            return "navigation"
        return "heading"

    pos = seg_count / max(total_segs, 1)
    if pos < 0.025:
        return "navigation"

    heading_text = source_text if source_text is not None else text
    if not is_merged_segment and _is_section_heading(heading_text):
        return "heading"

    total = len(text)
    if total == 0:
        return "body"

    alpha = sum(c.isalpha() for c in text)
    char_density = alpha / total

    dot_chain_hits = text.count(" . ")
    dot_chain_density = dot_chain_hits / total
    if dot_chain_density > 0.055:
        return "toc_entry"

    if char_density < 0.48:
        return "caption"

    return "body"


DEFAULT_MIN_SEGMENT_SIZE = 200


class _Segment(TypedDict):
    text: str
    page: int
    chunk_role: NotRequired[str]
    element_type: NotRequired[str]
    label: NotRequired[str]
    merged: NotRequired[bool]
    table_degenerate: NotRequired[bool]
    t_start: NotRequired[float]
    t_end: NotRequired[float]


class _Chunk(TypedDict):
    text: str
    page: int
    chunk_role: str
    element_type: str
    table_degenerate: NotRequired[bool]
    t_start: NotRequired[float]
    t_end: NotRequired[float]


_STRUCTURAL_ROLES: frozenset[ElementTypeLiteral] = frozenset(
    {"heading", "toc_entry", "caption", "navigation"}
)

# Docling's run-in heading label (maps to "heading" above). Only this label
# is demoted by the plausibility gate in _merge_segments (openspec
# fix-chunk-heading-context D1); "title" and the other structural roles keep
# the standalone flush regardless of text shape.
_SECTION_HEADER_LABEL = "section_header"

# Segment label marking a serialized table run (table_serialize.TABLE_LABEL;
# not imported to keep this pure module import-light). Table segments are
# flushed standalone like structural roles — table rows must never be merged
# with surrounding prose — and chunk_segments splits them only at row
# boundaries.
_TABLE_LABEL = "table"


def _flush_accumulation(
    text: str,
    page: int,
    label: str | None,
    merged: bool = False,
    sources: Sequence[Segment] = (),
) -> _Segment:
    segment: _Segment = {"text": text, "page": page, "merged": merged}
    if label is not None:
        segment["label"] = label
    if any(source.get("table_degenerate") for source in sources):
        # A degenerate-table segment is flushed standalone (never merged), so
        # the flag travels from its single source to the flushed segment.
        segment["table_degenerate"] = True
    starts = [source["t_start"] for source in sources if "t_start" in source]
    ends = [source["t_end"] for source in sources if "t_end" in source]
    if starts:
        segment["t_start"] = min(starts)
    if ends:
        segment["t_end"] = max(ends)
    return segment


def _is_section_numbered(text: str) -> bool:
    """Return whether the text is a section-number-prefixed heading.

    Args:
        text: Stripped text to test.

    Returns
    -------
        True when the text starts with a dotted section number followed by
        whitespace (e.g. "11.18 Configuring the Autostart Service").
    """
    return bool(re.match(r"\d+\.\d+(\.\d+)?\s", text))


def _is_section_heading(text: str) -> bool:
    """Require a short, single-line title after the dotted section number."""
    match = re.match(r"\d+(?:\.\d+)+[ \t]+([^\r\n]+)$", text)
    return bool(match and len(text) < 100 and not any(p in match[1] for p in ".!?;"))


def _is_likely_title(text: str) -> bool:
    """Return whether a stripped fragment looks like a section title.

    Short fragments without sentence punctuation are titles.  Section-number
    prefixed headings always count as titles: their section number contains a
    dot, which the punctuation heuristic alone would reject, causing them to
    merge with body content.

    Args:
        text: Stripped text to test.

    Returns
    -------
        True when the fragment should be treated as a title.
    """
    if _is_section_numbered(text):
        return True
    return (
        len(text) < 100
        and not any(p in text for p in [".", ":", "-", "—"])
        and not text.endswith(".")
    )


def is_plausible_heading(text: str) -> bool:
    """Return whether a parser-labeled heading's text plausibly is one.

    Shared gate for structure capture and chunk assembly (openspec
    fix-chunk-heading-context design D1): docling's layout model also marks
    bold run-in labels and "command - description" synopsis lines as
    ``section_header`` items, and every one of them used to become a
    structure-tree node or a standalone heading chunk. A section-number
    prefix (``_is_section_numbered``) always passes; otherwise the text must
    be short, carry no trailing sentence punctuation, and have no synopsis
    shape — the dash rejection mirrors :func:`_is_likely_title`.

    Args:
        text: Stripped text to test (both call sites pass ``text.strip()``).

    Returns
    -------
        True when the text should be treated as a heading.
    """
    if _is_section_numbered(text):
        return True
    return (
        len(text) < 120
        and not text.endswith((".", ":", ",", ";", "—"))
        and " - " not in text
    )


def _merge_segments(segments: Sequence[Segment]) -> list[_Segment]:
    """Merge raw extraction segments into chunkable segments.

    Design decisions mirror those documented in the original _chunk_segments
    (document/__init__.py): MIN_SEGMENT_SIZE merges tiny docling extractions
    before chunking, and title detection lets short punctuation-free
    fragments join the following content.
    ASR bounds are aggregated without changing the text merge policy.
    Labeled structural segments flush standalone — the one exception is a
    docling ``section_header`` whose text fails :func:`is_plausible_heading`
    (openspec fix-chunk-heading-context D1): it is run-in body text, joins
    the accumulation, and its label is dropped on join.

    Args:
        segments: List of extracted text segments.

    Returns
    -------
        Merged segment list ready for size-bound chunking. Each segment
        records ``merged`` — whether ≥2 raw segments were joined into it —
        which :func:`classify_chunk_role` uses to keep merged openers in
        ``body`` (single-segment gate on the dotted→heading guard).
    """
    merged_segments: list[_Segment] = []
    current_text = ""
    current_page = 0
    current_label: str | None = None
    current_sources: list[Segment] = []
    # Whether the current accumulation joined ≥2 raw segments (merge
    # provenance, consumed by classify_chunk_role's single-segment gate).
    current_merged = False

    for _i, segment in enumerate(segments):
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        stripped = text.strip()

        label = segment.get("label")
        if label is not None:
            labeled_role = label_to_element_type(label)
            if (
                labeled_role is not None and labeled_role in _STRUCTURAL_ROLES
            ) or label == _TABLE_LABEL:
                # D1 (openspec fix-chunk-heading-context): docling's layout
                # model also marks run-in labels and synopsis lines as
                # section_header. One failing the plausibility gate is body
                # text: it does NOT flush standalone — it falls through to
                # the accumulation path below with its heading label dropped
                # (a demoted start carries no label; a demoted join keeps the
                # accumulation's earlier label, mirroring the label-less join
                # branch). Plausible headings and every other structural or
                # table label keep the standalone flush.
                if label == _SECTION_HEADER_LABEL and not is_plausible_heading(
                    stripped
                ):
                    label = None
                else:
                    if current_text:
                        merged_segments.append(
                            _flush_accumulation(
                                current_text,
                                current_page,
                                current_label,
                                current_merged,
                                current_sources,
                            )
                        )
                    merged_segments.append(
                        _flush_accumulation(stripped, page, label, sources=[segment])
                    )
                    current_text = ""
                    current_label = None
                    current_sources = []
                    current_merged = False
                    continue

        is_likely_title = _is_likely_title(stripped)

        # Section-number-prefixed titles must START a new chunk rather than
        # merge into the previous accumulation (the default title behaviour
        # appends via the "if len(current_text) < MIN" branch below).
        if is_likely_title and _is_section_numbered(stripped) and current_text:
            merged_segments.append(
                _flush_accumulation(
                    current_text,
                    current_page,
                    current_label,
                    current_merged,
                    current_sources,
                )
            )
            current_text = stripped
            current_page = page
            current_label = label
            current_sources = [segment]
            current_merged = False
            continue

        if len(current_text) < DEFAULT_MIN_SEGMENT_SIZE or is_likely_title:
            if current_text:
                current_text += " " + stripped
                current_sources.append(segment)
                current_merged = True
            else:
                current_text = stripped
                current_label = label
                current_sources = [segment]
                current_merged = False
            current_page = page
        else:
            merged_segments.append(
                _flush_accumulation(
                    current_text,
                    current_page,
                    current_label,
                    current_merged,
                    current_sources,
                )
            )
            current_text = stripped
            current_page = page
            current_label = label
            current_sources = [segment]
            current_merged = False

    if current_text:
        merged_segments.append(
            _flush_accumulation(
                current_text,
                current_page,
                current_label,
                current_merged,
                current_sources,
            )
        )

    return merged_segments


def chunk_segments(
    segments: Sequence[Segment], chunk_size: int, chunk_overlap: int
) -> list[_Chunk]:
    """Chunk segments into smaller pieces respecting size limits.

    Design decisions mirror those documented in the original _chunk_segments
    (document/__init__.py). Key points:

    1. MIN_SEGMENT_SIZE merges tiny docling extractions before chunking.
    2. Title detection: short fragments with no punctuation join following content.
    3. Word-boundary split via rfind(" ") prevents token breaks.
    4. Overlap maintained at chunk boundaries for context continuity.

    Args:
        segments: List of extracted text segments.
        chunk_size: Maximum chunk size in characters.
        chunk_overlap: Overlap between consecutive chunks.

    Returns
    -------
        List of chunked segments.
    """
    merged_segments = _merge_segments(segments)

    total_segs = len(merged_segments)
    seg_counter = 0

    chunks: list[_Chunk] = []

    for segment in merged_segments:
        text = segment["text"]
        page = segment.get("page", 0)
        labeled_role = label_to_element_type(segment.get("label"))

        if not text.strip():
            continue

        is_likely_title_for_seg = (
            len(text.strip()) < 100
            and not any(p in text.strip() for p in [".", ":", "-", "—"])
            and not text.strip().endswith(".")
        )

        # Table segments (serialized table runs, see table_serialize) split
        # ONLY at row boundaries: a row's label and value must never land in
        # different chunks. Row boundaries are the newlines the serializer
        # emits between rows.
        is_table = segment.get("label") == _TABLE_LABEL

        start = 0
        while start < len(text):
            if start + chunk_size >= len(text):
                chunk_text = text[start:].rstrip()
                if chunk_text:
                    chunk_role = (
                        labeled_role
                        if labeled_role is not None
                        else classify_chunk_role(
                            chunk_text,
                            seg_counter,
                            total_segs,
                            is_likely_title_for_seg,
                            is_merged_segment=segment.get("merged", False),
                            source_text=text,
                        )
                    )
                    final_chunk: _Chunk = {
                        "text": chunk_text,
                        "page": page,
                        "chunk_role": chunk_role,
                        "element_type": chunk_role,
                    }
                    if "t_start" in segment:
                        final_chunk["t_start"] = segment["t_start"]
                    if "t_end" in segment:
                        final_chunk["t_end"] = segment["t_end"]
                    if "table_degenerate" in segment:
                        final_chunk["table_degenerate"] = segment["table_degenerate"]
                    chunks.append(final_chunk)
                seg_counter += 1
                break

            next_start = start + chunk_size
            chunk_end = next_start
            row_aligned_split = False
            if is_table:
                row_break = text.rfind("\n", start, chunk_end)
                if row_break > start:
                    # Split at the row boundary; the newline itself is
                    # excluded so the chunk holds complete rows only.
                    chunk_end = row_break
                    row_aligned_split = True
                else:
                    # A single row longer than chunk_size cannot honor both
                    # bounds; fall back to the word-boundary split so the
                    # loop still advances (no row structure was available
                    # to do better — see table_serialize.build_table_run).
                    last_space = text.rfind(" ", start, chunk_end)
                    if last_space > start:
                        chunk_end = last_space
            else:
                last_space = text.rfind(" ", start, chunk_end)
                if last_space > start:
                    chunk_end = last_space

            chunk_text = text[start:chunk_end]
            if chunk_text.strip():
                chunk_role = (
                    labeled_role
                    if labeled_role is not None
                    else classify_chunk_role(
                        chunk_text,
                        seg_counter,
                        total_segs,
                        is_likely_title_for_seg,
                        is_merged_segment=segment.get("merged", False),
                        source_text=text,
                    )
                )
                chunk: _Chunk = {
                    "text": chunk_text,
                    "page": page,
                    "chunk_role": chunk_role,
                    "element_type": chunk_role,
                }
                if "t_start" in segment:
                    chunk["t_start"] = segment["t_start"]
                if "t_end" in segment:
                    chunk["t_end"] = segment["t_end"]
                if "table_degenerate" in segment:
                    chunk["table_degenerate"] = segment["table_degenerate"]
                chunks.append(chunk)
                seg_counter += 1

            if row_aligned_split:
                # Restart at a row start: the overlap window repeats whole
                # rows only (the first row boundary at or after
                # chunk_end + 1 - chunk_overlap), never a partial row.
                candidate = chunk_end + 1 - chunk_overlap
                if candidate <= start:
                    start = chunk_end + 1
                else:
                    boundary = text.find("\n", candidate, chunk_end)
                    new_start = boundary + 1 if boundary != -1 else chunk_end + 1
                    start = new_start if new_start > start else chunk_end + 1
            else:
                new_start = chunk_end - chunk_overlap
                start = chunk_end if new_start <= start else new_start

    return chunks


def deduplicate_segments(
    file_path: Path,
    segments: list[_Segment],
) -> list[dict[str, Any]]:
    """Deduplicate and tag segments with file-path metadata.

    Normalizes text (lowercase, single spaces) before SHA256 hashing to
    detect duplicates. Adds file_path, original_index, and text_hash
    metadata for downstream use.

    Args:
        file_path: Source file path (stored with each chunk).
        segments: List of text segments to process.

    Returns
    -------
        List of chunk dicts with text, page, file_path, original_index, text_hash.
    """
    all_chunks: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    for i, segment in enumerate(segments):
        cleaned = segment["text"].strip()
        if not cleaned:
            continue

        normalized = " ".join(cleaned.lower().split())
        text_hash = hashlib.sha256(normalized.encode()).hexdigest()

        if text_hash not in seen_hashes:
            seen_hashes.add(text_hash)
            all_chunks.append(
                {
                    "file_path": file_path,
                    "original_index": i,
                    "text": cleaned,
                    "page": segment["page"],
                    "text_hash": text_hash,
                    **{
                        key: segment[key]
                        for key in ("t_start", "t_end", "table_degenerate")
                        if key in segment
                    },
                }
            )

    return all_chunks


_chunk_segments = chunk_segments
