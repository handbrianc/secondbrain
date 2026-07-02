"""Shared type definitions for secondbrain."""

from typing import Any, TypedDict


class ChunkInfo(TypedDict):
    """Typed dictionary for chunk information."""

    chunk_id: str
    source_file: str
    page_number: int | None
    chunk_text: str


class SearchResult(ChunkInfo, total=False):
    """Typed dictionary for search results."""

    score: float


def _validate_chunk_info(d: dict[str, Any]) -> ChunkInfo:
    """Runtime validation gate at dict→ChunkInfo cast points."""
    for key in ("chunk_id", "source_file", "chunk_text"):
        if key not in d:
            raise TypeError(f"ChunkInfo missing required key: {key!r}")
    if "page_number" not in d:
        raise TypeError("ChunkInfo missing required key: 'page_number'")
    return d  # type: ignore[return-value]


def _validate_search_result(d: dict[str, Any]) -> SearchResult:
    """Runtime validation gate at dict→SearchResult cast points."""
    for key in ("chunk_id", "source_file", "chunk_text"):
        if key not in d:
            raise TypeError(f"SearchResult missing required key: {key!r}")
    if "page_number" not in d:
        raise TypeError("SearchResult missing required key: 'page_number'")
    return d  # type: ignore[return-value]
