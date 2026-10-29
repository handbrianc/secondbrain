"""Read-only storage double backed by exported chapter-map fixtures.

Used by the chapter-map characterization tests and by
``scripts/export_chapter_fixtures.py --baselines`` so pre-change baselines and
post-change test runs execute against byte-identical data.

Mirrors the subset of ``QdrantVectorStorage`` semantics the chapter
enumeration path relies on:

- ``get_body_chunks``: exact ``source_file`` + ``chunk_role == "body"``,
  optional ``page_gte`` applied before ``limit``, ordered by
  ``(page_number, page_pos)`` with a missing/None ``page_pos`` sorting last
  — the same document-order guarantee ``QdrantVectorStorage.get_body_chunks``
  makes (fix-chapter-bucket-sampling D3, layer 1).
- ``find_structural_chunks``: OR of ``element_types`` / ``chunk_roles``; when
  both are empty every chunk matches (the "all chunks" fallback); prefix
  match on ``source_file``; ordered by page.
- ``count_chunks``: exact-match counts.

Ordering here is ``(page_number, page_pos)`` — deterministic within a page,
matching the live store's document-order reads.  Baselines are
captured through this same helper, so comparisons stay self-consistent.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "chapter_map"


def _document_order_key(chunk: dict[str, Any]) -> tuple[int, float]:
    """Reading-order key ``(page_number, page_pos)`` with None ``page_pos`` last.

    Mirrors the storage layer's document-order rule (D3).
    """
    pos = chunk.get("page_pos")
    return (
        int(chunk.get("page_number") or 0),
        float(pos) if pos is not None else float("inf"),
    )


# Intended bucket-window diffs, verified per book by running the sampler
# over these fixtures.  Two deliberate mechanisms move window page lists:
#
# (1) fix-summary-fidelity D1 — the range-faithful admission filter refuses
#     foreign material on a chapter's speculative "minus one" start page,
#     so the window slides onto the chapter's own in-range pages.
# (2) fix-chapter-bucket-sampling D4 — the per-page admission bound scales
#     with the page's in-range body-chunk density,
#     cap_pg = min(PAGE_CAP_MAX, max(page_cap, ceil(PAGE_DENSITY_FACTOR * n)))
#     (constants in ``_pipeline.py``; base 3, factor 0.6, max 6), so every
#     page holding 6+ such chunks contributes more than the flat 3-chunk
#     bound and each window pulls toward its earlier dense pages.  These
#     books are dense nearly everywhere, so almost every chapter's list
#     moves; the lists below are the post-D4 windows.
#
# Ranges, pins, enumeration, and every other bucket stay byte-identical to
# ``baselines.json`` (the pre-change record); only these page lists move.
BASELINE_WINDOW_OVERRIDES: dict[str, dict[str, list[int]]] = {
    "user-manual": {
        # (50, 87): @50 holds only ch4's closing install prose (D1 slide).
        # D4: @51 holds 10 body chunks -> cap 6 (was 3), @52 holds 7 -> cap 5.
        "5": [51, 51, 51, 51, 51, 51, 52, 52],
        # (468, 474): @468 holds only ch15's closing vboximg-mount material
        # (D1 slide).  D4: @469 holds 13 body chunks -> cap 6 (was 5 via
        # header promotion).
        "16": [469, 469, 469, 469, 469, 469, 470, 470],
        # (480, inf): @480 holds only ch17's closing change-log links
        # (D1 slide).  D4: @481 holds 8 body chunks -> cap 5.
        "18": [481, 481, 481, 481, 481, 482, 482, 482],
        # D4-only moves: dense opener pages contribute up to 6 chunks
        # (n >= 10 -> cap 6) before the window spills onto the next page.
        # ch12's pages hold <= 5 chunks, so its window keeps its baseline.
        "1": [21, 21, 21, 21, 21, 22, 22, 22],
        "2": [29, 29, 29, 29, 29, 30, 30, 30],
        "3": [43, 43, 43, 43, 43, 44, 44, 44],
        "4": [47, 47, 47, 47, 47, 47, 48, 48],
        "6": [89, 89, 89, 89, 89, 90, 90, 90],
        "7": [103, 103, 103, 103, 103, 103, 104, 104],
        "8": [125, 125, 125, 125, 125, 125, 126, 126],
        "9": [143, 143, 143, 143, 143, 144, 144, 144],
        "10": [161, 161, 161, 161, 161, 161, 162, 162],
        "11": [175, 175, 175, 175, 175, 176, 176, 176],
        "13": [237, 237, 237, 237, 237, 237, 238, 238],
        "14": [263, 263, 263, 263, 263, 264, 264, 264],
        "15": [271, 271, 271, 271, 271, 272, 272, 272],
        "17": [475, 475, 475, 475, 475, 475, 476, 476],
    },
    "pve-admin-guide": {
        # (433, 448): @433 holds only ch15's 15.12 affinity-rule bleed
        # bullets; ch16's opener heading sits @434 (D1 slide).  D4: @434
        # holds 7 body chunks -> cap 5 (was 3), @435 holds 9 -> cap 6.
        "16": [434, 434, 434, 434, 434, 435, 435, 435],
        # (449, 460): @449 holds only ch16's closing 16.13 examples (D1
        # slide).  D4: @450 holds 6 body chunks -> cap 4.
        "17": [450, 450, 450, 451, 451, 451, 451, 451],
        # (162, ...): @162 holds only ch6's closing HA-recovery prose (D1
        # slide).  D4: @163 holds 7 body chunks -> cap 5.
        "7": [163, 163, 163, 163, 163, 164, 164, 164],
        # D4-only moves: dense pages contribute up to 6 chunks (n >= 10 ->
        # cap 6) or their density-scaled share (n = 6..9 -> cap 4..6)
        # before the window spills onto the next page.
        "1": [23, 23, 23, 24, 24, 24, 24, 24],
        "2": [32, 32, 32, 32, 32, 33, 33, 33],
        "3": [49, 49, 49, 49, 50, 50, 50, 51],
        "4": [119, 119, 119, 119, 120, 120, 121, 121],
        "5": [132, 132, 132, 133, 133, 133, 133, 133],
        "6": [158, 158, 158, 159, 159, 159, 159, 159],
        "8": [195, 195, 195, 196, 196, 196, 196, 196],
        "9": [221, 221, 221, 221, 221, 222, 222, 222],
        "10": [225, 225, 225, 225, 225, 226, 226, 226],
        "11": [309, 309, 309, 309, 309, 310, 310, 310],
        "12": [340, 340, 340, 340, 340, 341, 341, 341],
        "13": [367, 367, 367, 367, 367, 368, 368, 368],
        "14": [386, 386, 386, 387, 387, 387, 387, 388],
        "15": [409, 409, 409, 409, 409, 409, 410, 410],
        "18": [461, 461, 461, 461, 462, 462, 462, 462],
        "19": [467, 467, 467, 467, 467, 467, 468, 468],
        "20": [469, 469, 469, 470, 470, 470, 470, 470],
    },
    "hcd-report": {
        # D4-only moves: dense pages (6-8 body chunks) now contribute up to
        # 5 chunks before the window spills onto the next page; chapters
        # whose pages hold <= 5 in-range chunks keep their baseline windows
        # (6, 10, 13, 15, 16 are not overridden).
        "7": [6, 6, 6, 6, 6, 7, 7, 7],
        "8": [9, 9, 9, 9],
        "9": [10, 10, 10, 10, 10],
        "11": [11, 11, 11, 11, 11],
        "12": [12, 12, 12, 12],
        "14": [13, 13, 13, 13],
        "17": [16, 16, 16, 16, 16, 17, 17, 17],
        "18": [19, 19, 19, 19, 19],
        "19": [20, 20, 20, 20, 21, 21, 21, 21],
        "20": [22, 22, 22, 22],
        "21": [23, 23, 23, 23, 23, 24, 24, 24],
    },
}


def load_fixture(name: str) -> list[dict[str, Any]]:
    """Load an exported fixture by short name (e.g. ``"user-manual"``)."""
    path = _FIXTURE_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


class ChapterFixtureStorage:
    """Minimal fake storage serving one fixture's chunks to the pipeline."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = sorted(chunks, key=_document_order_key)

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
