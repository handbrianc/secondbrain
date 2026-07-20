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
from pathlib import Path
from typing import Any, Literal

from typing_extensions import NotRequired, TypedDict

ElementTypeLiteral = Literal[
    "navigation",
    "heading",
    "toc_entry",
    "caption",
    "body",
    "table_row",
    "table_caption",
]


# TODO(element_type-migration): once migrated, return ElementTypeLiteral
def classify_chunk_role(text: str, seg_count: int, total_segs: int, is_likely_title: bool) -> str:
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


def chunk_segments(
    segments: list[_Segment], chunk_size: int, chunk_overlap: int
) -> list[_Segment]:
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
    seg_counter = 0
    last_is_likely_title = False

    for _i, segment in enumerate(segments):
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        stripped = text.strip()

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
        if is_likely_title and re.match(r"\d+\.\d+(\.\d+)?\s", stripped) and current_text:
            merged_segments.append({"text": current_text, "page": current_page})
            seg_counter += 1
            current_text = stripped
            current_page = page
            last_is_likely_title = True
            continue

        if len(current_text) < DEFAULT_MIN_SEGMENT_SIZE or is_likely_title:
            if current_text:
                current_text += " " + stripped
            else:
                current_text = stripped
            current_page = page
            last_is_likely_title = is_likely_title
        else:
            merged_segments.append({"text": current_text, "page": current_page})
            seg_counter += 1
            current_text = stripped
            current_page = page
            last_is_likely_title = is_likely_title

    if current_text:
        merged_segments.append({"text": current_text, "page": current_page})
        seg_counter += 1

    total_segs = len(merged_segments)
    seg_counter = 0

    chunks: list[_Segment] = []

    for segment in merged_segments:
        text = segment["text"]
        page = segment.get("page", 0)

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
                    chunks.append({
                        "text": chunk_text,
                        "page": page,
                        "chunk_role": classify_chunk_role(
                            chunk_text, seg_counter, total_segs, is_likely_title_for_seg
                        ),
                    })
                seg_counter += 1
                break

            next_start = start + chunk_size
            chunk_end = next_start
            last_space = text.rfind(" ", start, chunk_end)
            if last_space > start:
                chunk_end = last_space

            chunk_text = text[start:chunk_end]
            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "page": page,
                    "chunk_role": classify_chunk_role(
                        chunk_text, seg_counter, total_segs, is_likely_title_for_seg
                    ),
                })
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


# Backward-compatibility alias — original __init__.py used _chunk_segments
_chunk_segments = chunk_segments
