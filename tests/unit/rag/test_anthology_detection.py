"""Anthology shape detector contract: ``_detect_anthology_parts``.

The detector (add-anthology-aware-chapter-summarization, design §1) claims a
document only on multi-signal agreement: >= 3 part-opener headings AND >= 2
parts whose first numbered section restarts at 1.  Single-book shapes
("Chapter N" banners, bare 1..N numbering) must never satisfy the guard.

These tests are EXPECTED RED (AttributeError) until Lane A lands
``_StructureMixin._detect_anthology_parts``.
"""

from __future__ import annotations

from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag._chapter_fixture_storage import (
    ChapterFixtureStorage,
    load_fixture,
)

SRC_SYNTHETIC = "synthetic-anthology.pdf"

# Document-order (label, start_page) pairs for the 16 sub-reports of
# Consolidated_Knowledge_Compilation.pdf (120 pages), from the change's
# design.md verified failure record.
EXPECTED_COMPILATION_PARTS: list[tuple[str, int]] = [
    ("I.1", 3),
    ("I.2", 13),
    ("I.3", 22),
    ("I.4", 37),
    ("II.1", 61),
    ("II.2", 66),
    ("II.3", 73),
    ("II.4", 77),
    ("II.5", 81),
    ("II.6", 86),
    ("II.7", 91),
    ("II.8", 95),
    ("II.9", 101),
    ("II.10", 106),
    ("II.11", 109),
    ("II.12", 115),
]


class _StubSearcher:
    """Storage host for the pipeline instance; the detector never searches."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    """Provider returning one fixed, plausible sentence (never streamed)."""

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


def _make_pipeline() -> RAGPipeline:
    """Build a pipeline whose mixins host the detector under test."""
    return RAGPipeline(
        searcher=_StubSearcher(None), llm_provider=_CannedProvider(), top_k=5
    )


def _heading(text: str, page: int) -> dict[str, Any]:
    return {
        "chunk_text": text,
        "page_number": page,
        "chunk_role": "heading",
        "source_file": SRC_SYNTHETIC,
    }


def _compilation_headings() -> tuple[list[dict[str, Any]], str]:
    """The compilation fixture's heading-role stream, as the pipeline fetches it."""
    chunks = load_fixture("knowledge-compilation")
    source = chunks[0]["source_file"]
    storage = ChapterFixtureStorage(chunks)
    headings = list(
        storage.find_structural_chunks(chunk_roles=["heading"], source_prefix=source)
    )
    return headings, source


class TestCompilationDetected:
    """Positive: the 16-part compilation satisfies every detector signal."""

    def test_compilation_yields_16_parts_in_document_order(self) -> None:
        headings, source = _compilation_headings()
        parts = _make_pipeline()._detect_anthology_parts(headings, source)

        assert parts is not None, "compilation must be detected as an anthology"
        assert len(parts) == 16
        assert [(p["label"], p["start_page"]) for p in parts] == (
            EXPECTED_COMPILATION_PARTS
        )

    def test_part_titles_come_from_the_opener_text(self) -> None:
        headings, source = _compilation_headings()
        parts = _make_pipeline()._detect_anthology_parts(headings, source)

        assert parts is not None
        assert all(p.get("title") for p in parts), "every part carries a title"
        assert parts[0]["title"] == "From Vague Requirements to Well-Defined Epics"
        assert "Frontend & Web UI Engineering" in parts[15]["title"]

    def test_labels_cover_both_volume_families(self) -> None:
        headings, source = _compilation_headings()
        parts = _make_pipeline()._detect_anthology_parts(headings, source)

        assert parts is not None
        labels = [p["label"] for p in parts]
        assert labels[:4] == ["I.1", "I.2", "I.3", "I.4"]
        assert [f"II.{n}" for n in range(1, 13)] == labels[4:]


class TestSingleBookNotDetected:
    """Negatives: the three corpus books must keep the legacy path."""

    @pytest.mark.parametrize(
        "fixture_name",
        ["user-manual", "pve-admin-guide", "hcd-report"],
    )
    def test_book_fixtures_return_none(self, fixture_name: str) -> None:
        chunks = load_fixture(fixture_name)
        source = chunks[0]["source_file"]
        storage = ChapterFixtureStorage(chunks)
        headings = list(
            storage.find_structural_chunks(
                chunk_roles=["heading"], source_prefix=source
            )
        )
        assert _make_pipeline()._detect_anthology_parts(headings, source) is None, (
            f"{fixture_name} must not be claimed as an anthology"
        )


class TestMultiSignalRule:
    """Synthetic micro-cases for the multi-signal guard (design §1).

    Openers use the corpus shapes ("I.1 · Title"); sections use the corpus
    restart shapes ("1. Executive Summary") and non-restart shapes
    ("2. Fundamentals").  Headings are spread over >= 2 pages per part so a
    heading-page-based scale proxy cannot flip any outcome.
    """

    @staticmethod
    def _two_openers_with_restarts() -> list[dict[str, Any]]:
        return [
            _heading("I.1 · Alpha", 1),
            _heading("1. Executive Summary", 2),
            _heading("2. Fundamentals", 3),
            _heading("I.2 · Beta", 10),
            _heading("1. Executive Summary", 11),
            _heading("2. Fundamentals", 12),
        ]

    @staticmethod
    def _three_openers_without_restarts() -> list[dict[str, Any]]:
        return [
            _heading("I.1 · Alpha", 1),
            _heading("2. Fundamentals", 2),
            _heading("2.1 Vocabulary", 3),
            _heading("I.2 · Beta", 10),
            _heading("2. Fundamentals", 11),
            _heading("2.1 Vocabulary", 12),
            _heading("I.3 · Gamma", 20),
            _heading("2. Fundamentals", 21),
        ]

    @staticmethod
    def _three_openers_with_two_restarts() -> list[dict[str, Any]]:
        return [
            _heading("I.1 · Alpha", 1),
            _heading("1. Executive Summary", 2),
            _heading("2. Fundamentals", 3),
            _heading("I.2 · Beta", 10),
            _heading("1. Executive Summary", 11),
            _heading("2. Fundamentals", 12),
            _heading("I.3 · Gamma", 20),
            _heading("2. Later Sections", 21),
        ]

    def test_two_openers_with_restarts_return_none(self) -> None:
        # Restart signal satisfied (2 parts restart at 1) but only 2 openers:
        # the opener-count signal fails, so nothing is claimed.
        headings = self._two_openers_with_restarts()
        assert _make_pipeline()._detect_anthology_parts(headings, SRC_SYNTHETIC) is None

    def test_three_openers_without_restarts_return_none(self) -> None:
        # Openers >= 3 but no part's first numbered section restarts at 1:
        # the restart signal fails, so nothing is claimed.
        headings = self._three_openers_without_restarts()
        assert _make_pipeline()._detect_anthology_parts(headings, SRC_SYNTHETIC) is None

    def test_three_openers_with_two_restarts_are_detected(self) -> None:
        # Both signals hold (the third part may start at 2 — only >= 2
        # restarts are required) → the document is claimed.
        headings = self._three_openers_with_two_restarts()
        parts = _make_pipeline()._detect_anthology_parts(headings, SRC_SYNTHETIC)

        assert parts is not None
        assert [(p["label"], p["start_page"]) for p in parts] == [
            ("I.1", 1),
            ("I.2", 10),
            ("I.3", 20),
        ]
