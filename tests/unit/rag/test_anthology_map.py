"""Per-part chapter map contract: ``_enrich_anthology_parts``.

Boundaries follow the design (add-anthology-aware-chapter-summarization §2):
part *i* spans ``[opener_i, opener_{i+1} - 1]`` and the last part runs to the
end of the document.  Each part carries the body chunks of its range and the
per-part section roster pinned from heading-role chunks inside the part.

These tests are EXPECTED RED (AttributeError) until Lane A lands
``_enrich_anthology_parts`` (and ``_detect_anthology_parts`` for the
fixture-derived inputs).
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import Any

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag._chapter_fixture_storage import (
    ChapterFixtureStorage,
    load_fixture,
)

SRC_SYNTHETIC = "synthetic-anthology.pdf"
_COMPILATION = "knowledge-compilation"
_COMPILATION_PAGES = 120

# Exact part ranges implied by the opener pages (opener_i .. opener_{i+1}-1,
# last part to page 120); the asserted subset pins both families' edges.
EXPECTED_RANGES: dict[str, tuple[int, int]] = {
    "I.1": (3, 12),
    "I.2": (13, 21),
    "I.3": (22, 36),
    "II.12": (115, 120),
}


class _StubSearcher:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return (
            "The document presents its material as a sequence of focused "
            "sections, each developing one theme with concrete examples and "
            "practical guidance. Recurring ideas are introduced early and "
            "then applied to specific cases, so the reader can follow the "
            "argument without losing the overall thread."
        )


def _make_pipeline(storage: Any = None) -> RAGPipeline:
    return RAGPipeline(
        searcher=_StubSearcher(storage), llm_provider=_CannedProvider(), top_k=5
    )


def _compilation_context() -> tuple[
    RAGPipeline,
    list[dict[str, Any]] | None,
    dict[int, list[dict[str, Any]]],
    list[dict[str, Any]],
    str,
]:
    """Detect compilation parts and gather the enrichment inputs."""
    chunks = load_fixture(_COMPILATION)
    source = chunks[0]["source_file"]
    storage = ChapterFixtureStorage(chunks)
    pipeline = _make_pipeline(storage)

    headings = list(
        storage.find_structural_chunks(chunk_roles=["heading"], source_prefix=source)
    )
    body_by_page: dict[int, list[dict[str, Any]]] = {}
    for chunk in storage.get_body_chunks(source, limit=None):
        body_by_page.setdefault(int(chunk.get("page_number") or 0), []).append(chunk)

    parts = pipeline._detect_anthology_parts(headings, source)
    return pipeline, parts, body_by_page, headings, source


def _collect_numbers(obj: Any, out: set[int] | None = None) -> set[int]:
    """Collect every numeric value inside a (possibly nested) section entry.

    Walks dict values, list/tuple items, and numeric strings — key names and
    prose text are skipped — so the assertion survives the concrete section
    dict shape Lane A chooses ({"num": ..., "page": ...} or equivalent).
    """
    if out is None:
        out = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, int):
        out.add(obj)
    elif isinstance(obj, float):
        out.add(int(obj))
    elif isinstance(obj, str):
        if obj.isdigit():
            out.add(int(obj))
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_numbers(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_numbers(item, out)
    return out


class TestCompilationPartBoundaries:
    """Part boundaries derive from opener pages (design §2)."""

    def test_exact_ranges_for_asserted_parts(self) -> None:
        pipeline, parts, body_by_page, headings, _source = _compilation_context()
        assert parts is not None, "precondition: compilation detected"
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings, _COMPILATION_PAGES
        )

        assert enriched is not None
        assert len(enriched) == 16
        by_label = {p["label"]: p for p in enriched}
        for label, (start, end) in EXPECTED_RANGES.items():
            part = by_label[label]
            assert (part["start_page"], part["end_page"]) == (start, end), (
                f"part {label} must span pages {start}-{end}"
            )

    def test_ranges_are_contiguous_and_cover_the_document(self) -> None:
        pipeline, parts, body_by_page, headings, _source = _compilation_context()
        assert parts is not None
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings, _COMPILATION_PAGES
        )

        assert enriched is not None
        assert enriched[0]["start_page"] == 3
        assert enriched[-1]["end_page"] == _COMPILATION_PAGES
        for current, nxt in pairwise(enriched):
            assert current["end_page"] == nxt["start_page"] - 1, (
                f"part {current['label']} must end right before {nxt['label']} opens"
            )

    def test_labels_and_titles_survive_enrichment(self) -> None:
        pipeline, parts, body_by_page, headings, _source = _compilation_context()
        assert parts is not None
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings, _COMPILATION_PAGES
        )

        assert enriched is not None
        assert [p["label"] for p in enriched] == [p["label"] for p in parts]
        assert enriched[0]["title"] == "From Vague Requirements to Well-Defined Epics"


class TestCompilationPartContent:
    """Every part is backed by body chunks and a per-part section roster."""

    def test_every_part_has_body_chunks(self) -> None:
        pipeline, parts, body_by_page, headings, _source = _compilation_context()
        assert parts is not None
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings, _COMPILATION_PAGES
        )

        assert enriched is not None
        empty = [p["label"] for p in enriched if not p.get("chunks")]
        assert empty == [], f"parts without body chunks: {empty}"

    def test_part_sections_pin_at_their_own_heading_page(self) -> None:
        # Part I.1 (pages 3-12) carries the section heading "5 Step 3 — Story
        # Mapping: The Engine That Removes Vagueness" on page 7; the section
        # roster must pin it at its own heading page.
        pipeline, parts, body_by_page, headings, _source = _compilation_context()
        assert parts is not None
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings, _COMPILATION_PAGES
        )

        assert enriched is not None
        part_i1 = enriched[0]
        assert part_i1["label"] == "I.1"
        assert part_i1.get("sections"), "part I.1 must roster its sections"

        story_entry = None
        for section in part_i1["sections"]:
            if "Story Mapping" in json.dumps(section, default=str):
                story_entry = section
                break
        assert story_entry is not None, (
            "part I.1's sections must include the page-7 Story Mapping heading"
        )
        assert 7 in _collect_numbers(story_entry), (
            f"the Story Mapping section must be pinned at page 7: {story_entry!r}"
        )


class TestScaleGuard:
    """``_enrich_anthology_parts`` refuses documents without body support."""

    def test_part_without_body_chunks_fails_the_scale_check(self) -> None:
        # Three parts, but part I.2's page range holds no body chunks at all:
        # the scale signal (>= body-bearing pages per part) fails → the
        # enrichment must return None so the legacy path keeps the document.
        pipeline = _make_pipeline()
        parts = [
            {"label": "I.1", "title": "Alpha", "start_page": 1},
            {"label": "I.2", "title": "Beta", "start_page": 5},
            {"label": "I.3", "title": "Gamma", "start_page": 9},
        ]
        body_by_page: dict[int, list[dict[str, Any]]] = {
            1: [{"chunk_text": "alpha one", "page_number": 1}],
            2: [{"chunk_text": "alpha two", "page_number": 2}],
        }
        enriched = pipeline._enrich_anthology_parts(
            parts, body_by_page, headings=[], total_pages=16
        )
        assert enriched is None, (
            "a parts list with a body-less part must fail the scale check"
        )
