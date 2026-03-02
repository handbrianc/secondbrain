"""Shared type definitions for secondbrain."""

from typing import TypedDict


class ChunkInfo(TypedDict):
    """Typed dictionary for chunk information."""

    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str


class SearchResult(TypedDict):
    """Typed dictionary for search results."""

    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str
    score: float
