"""Segment definitions and chunking utilities for document processing."""

from __future__ import annotations

from typing_extensions import TypedDict


class Segment(TypedDict):
    """Text segment extracted from a document."""

    text: str
    page: int


def chunk_segments(
    segments: list[Segment], chunk_size: int, chunk_overlap: int
) -> list[Segment]:
    """Chunk segments into smaller pieces respecting size limits."""
    chunks: list[Segment] = []

    for segment in segments:
        text = segment["text"]
        page = segment.get("page", 0)

        if not text.strip():
            continue

        start = 0
        while start < len(text):
            # If remaining text fits in one chunk, take it all
            remaining = len(text) - start
            if remaining <= chunk_size:
                chunk_text = text[start:].strip()
                if chunk_text:
                    chunks.append({"text": chunk_text, "page": page})
                break

            # Otherwise, find the last space within chunk_size
            next_start = start + chunk_size
            last_space = text.rfind(" ", start, next_start)
            chunk_end = last_space if last_space > start else next_start
            chunk_text = text[start:chunk_end].strip()
            if chunk_text:
                chunks.append({"text": chunk_text, "page": page})

            new_start = chunk_end - chunk_overlap
            if new_start >= len(text) or new_start <= start:
                break
            start = new_start

    return chunks
