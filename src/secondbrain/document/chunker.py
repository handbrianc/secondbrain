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
from pathlib import Path
from typing import Any

from typing_extensions import TypedDict


DEFAULT_MIN_SEGMENT_SIZE = 200


class _Segment(TypedDict):
    text: str
    page: int


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

        if len(current_text) < DEFAULT_MIN_SEGMENT_SIZE or is_likely_title:
            if current_text:
                current_text += " " + stripped
            else:
                current_text = stripped
            current_page = page
        else:
            merged_segments.append({"text": current_text, "page": current_page})
            current_text = stripped
            current_page = page

    if current_text:
        merged_segments.append({"text": current_text, "page": current_page})

    chunks: list[_Segment] = []

    for segment in merged_segments:
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        start = 0
        while start < len(text):
            if start + chunk_size >= len(text):
                chunk_text = text[start:].rstrip()
                if chunk_text:
                    chunks.append({"text": chunk_text, "page": page})
                break

            next_start = start + chunk_size
            chunk_end = next_start
            last_space = text.rfind(" ", start, chunk_end)
            if last_space > start:
                chunk_end = last_space

            chunk_text = text[start:chunk_end]
            if chunk_text.strip():
                chunks.append({"text": chunk_text, "page": page})

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
