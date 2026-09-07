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
    text: str, seg_count: int, total_segs: int, is_likely_title: bool
) -> ElementTypeLiteral:
    """
    Classify chunk by structural role using only statistical signals.

    Thresholds are document-universal (char density, whitespace ratio, dot-chain density).
    """
    if is_likely_title:
        pos = seg_count / max(total_segs, 1)
        if pos < 0.025:
            return "navigation"
        # Section-number-prefixed headers (e.g. "11.18 Configuring the Autostart
        # Service") are inline section markers within chapters, not document-level
        # headings.  Classify as body so the retrieval pipeline can match them
        # via SEC_HEADER_RE during bucket collection.
        if re.match(r"\d+\.\d+(\.\d+)?\s", text):
            return "body"
        return "heading"

    pos = seg_count / max(total_segs, 1)
    if pos < 0.025:
        return "navigation"

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


class _Chunk(TypedDict):
    text: str
    page: int
    chunk_role: str
    element_type: str


_STRUCTURAL_ROLES: frozenset[ElementTypeLiteral] = frozenset(
    {"heading", "toc_entry", "caption", "navigation"}
)


def _flush_accumulation(text: str, page: int, label: str | None) -> _Segment:
    segment: _Segment = {"text": text, "page": page}
    if label is not None:
        segment["label"] = label
    return segment


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
    merged_segments: list[_Segment] = []
    current_text = ""
    current_page = 0
    current_label: str | None = None
    seg_counter = 0

    for _i, segment in enumerate(segments):
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        stripped = text.strip()

        label = segment.get("label")
        if label is not None:
            labeled_role = label_to_element_type(label)
            if labeled_role is not None and labeled_role in _STRUCTURAL_ROLES:
                if current_text:
                    merged_segments.append(
                        _flush_accumulation(current_text, current_page, current_label)
                    )
                    seg_counter += 1
                merged_segments.append({"text": stripped, "page": page, "label": label})
                current_text = ""
                current_label = None
                continue

        is_likely_title = (
            len(stripped) < 100
            and not any(p in stripped for p in [".", ":", "-", "—"])
            and not stripped.endswith(".")
        )
        # Section-number-prefixed headings like "11.18 Configuring the Autostart
        # Service" contain a dot in the section number and would be rejected by
        # the "." check above, causing them to merge with body content.
        if not is_likely_title and re.match(r"\d+\.\d+(\.\d+)?\s", stripped):
            is_likely_title = True

        # Section-number-prefixed titles must START a new chunk rather than
        # merge into the previous accumulation (the default title behaviour
        # appends via the "if is_likely_title" branch below).
        if (
            is_likely_title
            and re.match(r"\d+\.\d+(\.\d+)?\s", stripped)
            and current_text
        ):
            merged_segments.append(
                _flush_accumulation(current_text, current_page, current_label)
            )
            seg_counter += 1
            current_text = stripped
            current_page = page
            current_label = label
            continue

        if len(current_text) < DEFAULT_MIN_SEGMENT_SIZE or is_likely_title:
            if current_text:
                current_text += " " + stripped
            else:
                current_text = stripped
                current_label = label
            current_page = page
        else:
            merged_segments.append(
                _flush_accumulation(current_text, current_page, current_label)
            )
            seg_counter += 1
            current_text = stripped
            current_page = page
            current_label = label

    if current_text:
        merged_segments.append(
            _flush_accumulation(current_text, current_page, current_label)
        )
        seg_counter += 1

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
                        )
                    )
                    chunks.append(
                        {
                            "text": chunk_text,
                            "page": page,
                            "chunk_role": chunk_role,
                            "element_type": chunk_role,
                        }
                    )
                seg_counter += 1
                break

            next_start = start + chunk_size
            chunk_end = next_start
            last_space = text.rfind(" ", start, chunk_end)
            if last_space > start:
                chunk_end = last_space

            chunk_text = text[start:chunk_end]
            if chunk_text.strip():
                chunk_role = (
                    labeled_role
                    if labeled_role is not None
                    else classify_chunk_role(
                        chunk_text, seg_counter, total_segs, is_likely_title_for_seg
                    )
                )
                chunks.append(
                    {
                        "text": chunk_text,
                        "page": page,
                        "chunk_role": chunk_role,
                        "element_type": chunk_role,
                    }
                )
                seg_counter += 1

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
                }
            )

    return all_chunks


_chunk_segments = chunk_segments
