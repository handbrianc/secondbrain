"""Shared type definitions for secondbrain.

This module defines TypedDicts used throughout the application for
representing document chunks and search results.
"""

from typing import TypedDict


class ChunkInfo(TypedDict):
    """Typed dictionary for chunk information."""

    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str


class SearchResult(ChunkInfo, total=False):
    """Typed dictionary for search results."""

    score: float
