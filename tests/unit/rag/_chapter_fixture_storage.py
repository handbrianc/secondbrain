"""Read-only storage double backed by exported chapter-map fixtures.

Used by the chapter-map characterization tests and by
``scripts/export_chapter_fixtures.py --baselines`` so pre-change baselines and
post-change test runs execute against byte-identical data.

Mirrors the subset of ``QdrantVectorStorage`` semantics the chapter
enumeration path relies on:

- ``get_body_chunks``: exact ``source_file`` + ``chunk_role == "body"``,
  optional ``page_gte`` applied before ``limit``, ordered by page.
- ``find_structural_chunks``: OR of ``element_types`` / ``chunk_roles``; when
  both are empty every chunk matches (the "all chunks" fallback); prefix
  match on ``source_file``; ordered by page.
- ``count_chunks``: exact-match counts.

Ordering here is ``(page_number, page_pos)`` — deterministic within a page,
unlike the live store's unspecified within-page scroll order.  Baselines are
captured through this same helper, so comparisons stay self-consistent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "chapter_map"


def load_fixture(name: str) -> list[dict[str, Any]]:
    """Load an exported fixture by short name (e.g. ``"user-manual"``)."""
    path = _FIXTURE_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class ChapterFixtureStorage:
    """Minimal fake storage serving one fixture's chunks to the pipeline."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = sorted(
            chunks,
            key=lambda c: (c.get("page_number") or 0, c.get("page_pos") or 0),
        )

    @classmethod
    def from_fixture(cls, name: str) -> ChapterFixtureStorage:
        return cls(load_fixture(name))

    # -- storage surface used by the chapter enumeration path -------------

    def get_body_chunks(
        self,
        source_file: str,
        *,
        limit: int | None = None,
        page_gte: int | None = None,
        with_text: bool = True,
    ) -> Sequence[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for chunk in self._chunks:
            if chunk.get("source_file") != source_file:
                continue
            if chunk.get("chunk_role") != "body":
                continue
            page = chunk.get("page_number") or 0
            if page_gte is not None and page < page_gte:
                continue
            out.append(dict(chunk))
        if limit is not None:
            out = out[:limit]
        return out

    def find_structural_chunks(
        self,
        element_types: list[str] | None = None,
        chunk_roles: list[str] | None = None,
        source_prefix: str | None = None,
        limit: int | None = None,
    ) -> Sequence[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for chunk in self._chunks:
            if source_prefix and not str(chunk.get("source_file", "")).startswith(
                source_prefix
            ):
                continue
            if element_types or chunk_roles:
                if (chunk.get("element_type") in (element_types or [])) or (
                    chunk.get("chunk_role") in (chunk_roles or [])
                ):
                    out.append(dict(chunk))
            else:
                out.append(dict(chunk))
        if limit is not None:
            out = out[:limit]
        return out

    def count_chunks(
        self,
        source_file: str | None = None,
        chunk_role: str | None = None,
    ) -> int:
        return sum(
            1
            for chunk in self._chunks
            if (source_file is None or chunk.get("source_file") == source_file)
            and (chunk_role is None or chunk.get("chunk_role") == chunk_role)
        )

    def validate_connection(self) -> bool:
        return True
