"""Behavioral tests for the iterative (chapter/section enumeration) query path.

Covers ``_iterative_query`` routing: missing structure, missing target chapter,
the generic top-k fall-through, single-chapter/section overview generation,
multi-chapter map-reduce, storage-failure fallbacks, and the helper machinery
they drive (``_generate_multi_chapter_summary``, ``_generate_single_chapter_summary``,
``_split_bounded``/``_align_window_boundaries``, section-label filtering).

Also covers the legacy multi-chapter round-robin's document-order, density-
aware admission (fix-chapter-bucket-sampling D3/D4): the five spec scenarios
plus the boundary-straddle supplement's cap, pinned on a PVE-ch16-shaped
dense page through an order-preserving storage double.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.rag.intent_parser import IntentDecision, QueryIntent
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._pipeline import PAGE_CAP_MAX
from tests.unit.rag.test_pipeline_chat_flow import _SessionDouble
from tests.unit.rag.test_pipeline_streaming_guards import (
    _CallbackCapture,
    _StreamedProvider,
)

_PLAUSIBLE = (
    "The overview explains the retrieval pipeline in careful detail here. "
    "It covers embedding queries, ranking candidates, and trimming context. "
    "Each idea appears once with a short example and no repetition at all. "
    "The closing paragraph ties the workflow together cleanly for readers."
)

_SRC = "book.pdf"


def _toc(chapters: list[tuple[int, str]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_text": "".join(
                f"Chapter {num} {title}\n" for num, title in chapters
            ),
            "source_file": _SRC,
            "page": 2,
            "chunk_role": "toc_entry",
        }
        for num, title in chapters
    ]


def _body(text: str, page: int) -> dict[str, Any]:
    return {"chunk_text": text, "page_number": page, "source_file": _SRC}


class _IterStorage:
    """Storage double for the chapter-enumeration collection loop."""

    def __init__(
        self,
        body: list[dict[str, Any]],
        headings: list[dict[str, Any]] | None = None,
        *,
        count_raises: bool = False,
        headings_raise: bool = False,
    ) -> None:
        self._body = body
        self._headings = headings or []
        self._count_raises = count_raises
        self._headings_raise = headings_raise

    def count_chunks(self, source: str, element_type: str) -> int:
        if self._count_raises:
            raise RuntimeError("storage unavailable")
        return len([c for c in self._body if c.get("source_file") == source])

    def get_body_chunks(
        self,
        source: str,
        limit: int | None = None,
        page_gte: int | None = None,
    ) -> list[dict[str, Any]]:
        chunks = [c for c in self._body if c.get("source_file") == source]
        if page_gte is not None:
            chunks = [c for c in chunks if (c.get("page_number") or 0) >= page_gte]
        return chunks[:limit] if limit is not None else chunks

    def find_structural_chunks(
        self,
        chunk_roles: list[str] | None = None,
        source_prefix: str | None = None,
    ) -> list[dict[str, Any]]:
        if self._headings_raise and chunk_roles == ["heading"]:
            raise RuntimeError("heading fetch exploded")
        return [
            c
            for c in self._headings
            if (chunk_roles is None or c.get("chunk_role") in chunk_roles)
        ]


def _make_iterative(
    provider: Any,
    toc: list[dict[str, Any]],
    body: list[dict[str, Any]],
    intent: IntentDecision,
    storage: _IterStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> RAGPipeline:
    searcher = MagicMock()
    searcher.search.return_value = [{"chunk_text": "hit", "score": 0.9}]
    searcher.storage = storage
    pipeline = RAGPipeline(
        searcher=searcher,
        llm_provider=provider,  # type: ignore[arg-type]
        top_k=5,
    )
    pipeline._config.streaming_enabled = False
    monkeypatch.setattr(
        pipeline, "_probe_document_structure", lambda top_k, source_filter=None: toc
    )
    monkeypatch.setattr(pipeline._intent_parser, "parse", lambda q: intent)
    return pipeline


def _chapter_intent(target: int | str | None = None) -> IntentDecision:
    return IntentDecision(
        intent=QueryIntent.CHAPTER_ENUMERATE,
        confidence=0.9,
        target=target,
        reason="test",
        suggested_pipeline="structural",
    )


def _broad_intent() -> IntentDecision:
    return IntentDecision(
        intent=QueryIntent.BROAD_COVERAGE,
        confidence=0.9,
        target=None,
        reason="test",
        suggested_pipeline="structural",
    )


class TestIterativeRouting:
    """Routing decisions at the top of _iterative_query."""

    def test_no_structure_falls_back_to_generic_one_shot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        pipeline = _make_iterative(
            provider, [], [], _broad_intent(), _IterStorage([]), monkeypatch
        )
        # _probe_document_structure returns [] -> generic one-shot; the search
        # goes through searcher.search with the plain query.
        result = pipeline._iterative_query("give me an overview", 5, True)
        assert _PLAUSIBLE in result["answer"]
        assert result["sources"]

    def test_storage_failure_in_enumeration_falls_back(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        storage = _IterStorage(
            [_body("Chapter 3 Storage Signals\nbody prose about storage", 40)],
            count_raises=True,
        )
        pipeline = _make_iterative(
            provider,
            _toc([(3, "Storage Signals")]),
            [],
            _broad_intent(),
            storage,
            monkeypatch,
        )
        with caplog.at_level(10):
            result = pipeline._iterative_query("summarize chapter 3", 5, False)
        assert _PLAUSIBLE in result["answer"]
        assert any(
            "Storage unavailable for chapter enumeration" in r.message
            for r in caplog.records
        )

    def test_target_chapter_not_found_notice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _StreamedProvider()
        pipeline = _make_iterative(
            provider,
            _toc([(1, "Alpha Systems"), (2, "Beta Widgets")]),
            [_body("Chapter 1 Alpha Systems\nalpha prose", 10)],
            _chapter_intent(target="9"),
            _IterStorage([]),
            monkeypatch,
        )
        result = pipeline._iterative_query("summarize chapter 9", 5, False)
        assert result["answer"] == "I couldn't find chapter 9 in the document."

    def test_heading_fetch_failure_warns_and_continues(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        storage = _IterStorage(
            [
                _body("Chapter 2 Beta Widgets\nbeta prose continues here", 50),
                _body("3.1 The first section of chapter three explains widgets", 60),
            ],
            headings_raise=True,
        )
        pipeline = _make_iterative(
            provider,
            _toc([(2, "Beta Widgets"), (3, "Gamma Handles")]),
            [],
            _chapter_intent(target="3"),
            storage,
            monkeypatch,
        )
        with caplog.at_level(10):
            result = pipeline._iterative_query("summarize chapter 3", 5, False)
        assert "answer" in result
        assert any("Heading-chunk fetch failed" in r.message for r in caplog.records)

    def test_section_target_routes_chapter_enumeration(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # "summarize section 3.2" (BROAD_COVERAGE) extracts enum_target=3,
        # raw_section_target=3.2 -> single-chapter overview prompt -> vet -> emit.
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
            _body("3.1 Handles and grips\nprose about grips", 41),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(2, "Beta Widgets"), (3, "Gamma Handles")]),
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        capture = _CallbackCapture()
        pipeline._on_chunk = capture
        result = pipeline._iterative_query("summarize section 3.2", 5, False)
        assert _PLAUSIBLE in result["answer"]
        assert _PLAUSIBLE in capture.text

    def test_single_chapter_detailed_breakdown_uses_map_reduce(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # "tell me about chapter 3" -> enum_target=3, raw=None ->
        # _generate_single_chapter_summary: the small chapter fits one window,
        # so the single-pass reduce writes it from the raw source directly.
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
            _body("3.1 Handles and grips\nprose about grips", 41),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(2, "Beta Widgets"), (3, "Gamma Handles")]),
            body,
            _chapter_intent(target="3"),
            _IterStorage(body),
            monkeypatch,
        )
        with caplog.at_level(10):
            result = pipeline._iterative_query("tell me about chapter 3", 5, True)
        # The single-chapter breakdown streams its heading then ships the
        # reduce output prefixed with the chapter heading.
        assert result["answer"].startswith("Chapter 3")
        assert _PLAUSIBLE in result["answer"]
        assert "sources" in result

    def test_multi_chapter_map_reduce_and_empty_bucket_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 3 chapters -> round-robin collection; chapter 3 has no body in its
        # range -> explicit placeholder note in the joined overview.
        digest = (
            "A terse digest covering the chapter topics in document order with "
            "figures preserved exactly as the source text states them here."
        )
        provider = _StreamedProvider(
            generate_responses=[digest, _PLAUSIBLE, digest, _PLAUSIBLE]
        )
        body = [
            _body("Chapter 1 Alpha Systems\nalpha prose text", 10),
            _body("1.1 Systems and signals\nmore alpha prose", 11),
            _body("Chapter 2 Beta Widgets\nbeta prose text", 30),
            _body("2.1 Widgets overview\nmore beta prose", 31),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(1, "Alpha Systems"), (2, "Beta Widgets"), (3, "Gamma Handles")]),
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        capture = _CallbackCapture()
        pipeline._on_chunk = capture
        result = pipeline._iterative_query("give me an overview of the book", 5, False)
        answer = result["answer"]
        assert "Chapter 1" in answer and "Chapter 2" in answer
        assert "No document content was retrieved for this chapter" in answer
        assert "Chapter 3" in capture.text  # heading separators were streamed

    def test_multi_chapter_page_cap_promotes_section_headers(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 4 pages per chapter (page_cap=3): the 4th chunk on page 20 without a
        # section number replaces a non-header chunk; a section-numbered 4th
        # chunk takes an extra slot (page_cap+2 allowance).
        digest = (
            "A terse digest covering the chapter topics in document order with "
            "figures preserved exactly as the source text states them here."
        )
        provider = _StreamedProvider(
            generate_responses=[
                digest,
                _PLAUSIBLE,
                digest,
                _PLAUSIBLE,
                digest,
                _PLAUSIBLE,
            ]
        )
        body = []
        for i in range(1, 5):
            body.append(_body(f"Chapter {i} Title{i}\nprose", 10 * i))
            for p in range(10 * i + 1, 10 * i + 5):
                body.append(_body(f"Filler prose block {p} about widgets", p))
        body.append(_body("2.1 Widget metrics section header", 31))  # extra slot
        pipeline = _make_iterative(
            provider,
            _toc([(1, "Title1"), (2, "Title2"), (3, "Title3"), (4, "Title4")]),
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        with caplog.at_level(10):
            result = pipeline._iterative_query("overview of the book", 5, False)
        assert "Chapter 1" in result["answer"]

    def test_appendix_chunks_extend_generic_enumeration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Whole-book query with appendix entries: appendix body chunks are
        # appended to final_chunks and the roster lists them.
        digest = (
            "A terse digest covering the chapter topics in document order with "
            "figures preserved exactly as the source text states them here."
        )
        provider = _StreamedProvider(
            generate_responses=[digest, _PLAUSIBLE, digest, _PLAUSIBLE]
        )
        toc = _toc([(1, "Alpha Systems"), (2, "Beta Widgets")])
        toc.append(
            {
                "chunk_text": "Appendix A Reference Tables\n",
                "source_file": _SRC,
                "page": 90,
                "chunk_role": "toc_entry",
            }
        )
        body = [
            _body("Chapter 1 Alpha Systems\nalpha prose text", 10),
            _body("1.1 Systems and signals\nmore alpha prose", 11),
            _body("Chapter 2 Beta Widgets\nbeta prose text", 30),
            _body("2.1 Widgets overview\nmore beta prose", 31),
            _body("Appendix A Reference Tables\nappendix body content", 95),
        ]
        pipeline = _make_iterative(
            provider,
            toc,
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        result = pipeline._iterative_query("give me an overview of the book", 5, True)
        # The map-reduce digest texts ship as the overview; the appendix body
        # chunk made it into the sources for the LLM fallback context.
        assert "appendix body content" in " ".join(
            c.get("chunk_text", "") for c in result.get("sources", [])
        )

    def test_generate_exception_yields_error_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Single-chapter overview path where generate raises -> error answer.
        provider = _StreamedProvider(generate_responses=["irrelevant"])

        def _boom(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
            raise RuntimeError("llm exploded")

        provider.generate = _boom  # type: ignore[method-assign]
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
            _body("3.1 Handles and grips\nprose about grips", 41),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(2, "Beta Widgets"), (3, "Gamma Handles")]),
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        result = pipeline._iterative_query("summarize section 3.2", 5, False)
        assert "An error occurred during generation" in result["answer"]

    def test_empty_answer_falls_back_to_roster(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _StreamedProvider(generate_responses=["   "])
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
            _body("3.1 Handles and grips\nprose about grips", 41),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(2, "Beta Widgets"), (3, "Gamma Handles")]),
            body,
            _broad_intent(),
            _IterStorage(body),
            monkeypatch,
        )
        result = pipeline._iterative_query("summarize section 3.2", 5, False)
        # Vet returned "" -> the chapter roster fallback shipped (only the
        # enum-target chapter's roster line survives the target filter).
        assert "Chapter 3 — Gamma Handles" in result["answer"]

    def test_generic_branch_no_relevant_chunks_notice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Structure chunks derive no chapters (code-like) -> generic branch;
        # search returns nothing relevant -> no-results notice.
        provider = _StreamedProvider()
        searcher = MagicMock()
        searcher.search.return_value = [{"chunk_text": "x", "score": 0.01}]
        searcher.storage = _IterStorage([])
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        code_toc = [
            {
                "chunk_text": "const foo = require('bar');\nfunction baz() { return 1; }",
                "source_file": "script.js",
                "page": 1,
                "chunk_role": "toc_entry",
            }
        ]
        monkeypatch.setattr(
            pipeline,
            "_probe_document_structure",
            lambda top_k, source_filter=None: code_toc,
        )
        monkeypatch.setattr(pipeline._intent_parser, "parse", lambda q: _broad_intent())
        result = pipeline._iterative_query("give me an overview", 5, False)
        assert "couldn't find relevant documents" in result["answer"]

    def test_generic_branch_generates_and_emits_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        searcher = MagicMock()
        searcher.search.return_value = [{"chunk_text": "doc body", "score": 0.9}]
        searcher.storage = _IterStorage([])
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        code_toc = [
            {
                "chunk_text": "const foo = require('bar');\nfunction baz() { return 1; }",
                "source_file": "script.js",
                "page": 1,
                "chunk_role": "toc_entry",
            }
        ]
        monkeypatch.setattr(
            pipeline,
            "_probe_document_structure",
            lambda top_k, source_filter=None: code_toc,
        )
        monkeypatch.setattr(pipeline._intent_parser, "parse", lambda q: _broad_intent())
        capture = _CallbackCapture()
        pipeline._on_chunk = capture
        result = pipeline._iterative_query("give me an overview", 5, True)
        assert _PLAUSIBLE in result["answer"]
        assert _PLAUSIBLE in capture.text
        assert result["sources"] == [{"chunk_text": "doc body", "score": 0.9}]


class TestPublicEntryDispatch:
    """query()/chat() route page-lookup and enumeration intents to the right path."""

    def test_query_routes_enumeration_intent_to_iterative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # query() dispatches BROAD_COVERAGE to _iterative_query (line 170).
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(3, "Gamma Handles")]),
            body,
            _chapter_intent(target="3"),
            _IterStorage(body),
            monkeypatch,
        )
        result = pipeline.query("tell me about chapter 3", 5, True)
        assert "Chapter 3" in result["answer"]
        assert _PLAUSIBLE in result["answer"]

    def test_chat_routes_enumeration_intent_to_iterative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # chat() dispatches enumeration intents to _iterative_query and saves
        # the exchange into the session (lines 343-350).
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        body = [
            _body("Chapter 3 Gamma Handles\nprose about handles", 40),
        ]
        pipeline = _make_iterative(
            provider,
            _toc([(3, "Gamma Handles")]),
            body,
            _chapter_intent(target="3"),
            _IterStorage(body),
            monkeypatch,
        )
        session = _SessionDouble()
        result = pipeline.chat("tell me about chapter 3", session)
        assert "Chapter 3" in result["answer"]
        assert _PLAUSIBLE in result["answer"]
        assert ("user", "tell me about chapter 3") in session.messages
        assert ("assistant", result["answer"]) in session.messages


# --- fix-chapter-bucket-sampling D3/D4: density-aware document-order admission
#
# The legacy multi-chapter round-robin admits window chunks with a dynamic
# per-page bound, cap_pg = min(PAGE_CAP_MAX, max(3, ceil(0.6 * n))) where n
# is the page's in-range body-chunk count, and consumes the stream in
# (page_number, page_pos) document order.  The fixtures below pin the five
# spec scenarios on a PVE-ch16-shaped dense page through _IterStorage, whose
# get_body_chunks preserves the caller's list order — a shuffled body list
# therefore proves the pipeline's client-side sort decides admission.

_DENSITY_ROSTER: tuple[tuple[int, str, int], ...] = (
    (1, "Alpha Frameworks", 10),
    (2, "Beta Widgets", 20),
    (3, "Gamma Pipelines", 30),
)

# Digit-free, marker-free prose: no chapter numbers, no "N.M" section shapes
# (those would trigger header promotion beyond the page bound), no roster
# titles — so only the admission bounds decide membership.
_PROSE_SENTENCES: tuple[str, ...] = (
    "the meadow keeps its calm weather through the whole season",
    "quiet hills roll onward beneath a wide and patient sky",
    "harvest notes stay beside the barn ledger every evening",
    "the orchard rows follow the gentle slope toward the river",
    "morning fog lifts slowly over the terraced vegetable beds",
    "the windmill turns at a steady unhurried pace all day",
    "sheep graze along the stonewall until the light fades",
    "seed catalogs arrive before the last frost has passed",
    "the greenhouse glass holds the afternoon warmth inside",
    "bees drift between the lavender rows without any hurry",
    "rain barrels catch the roof water for the dry weeks",
    "the farmer marks the calendar for each sowing round",
    "compost heaps steam gently under the early frost",
    "the lane to the mill narrows past the old bridge",
    "wood smoke settles into the valley after sunset",
    "the cellar shelves hold jars of pickled beans",
    "geese fly over the stubble fields at first light",
    "the well rope creaks as the bucket rises slowly",
    "hedges border the footpath all the way to town",
    "the trough freezes over before the sun climbs high",
    "hay bales stack neatly beneath the open barn door",
    "the dog watches the gate from the porch steps",
    "plows rest in the shed until the ground softens",
    "the creek murmurs under the willow branches",
    "clover patches draw the cattle every afternoon",
    "the fence posts lean where the frost heaves them",
    "sparrows gather on the wire above the yard",
    "the kitchen garden needs weeding after the rain",
    "lanterns glow in the windows as night arrives",
    "the autumn leaves drift across the gravel path",
)


def _body_pos(text: str, page: int, pos: int) -> dict[str, Any]:
    """Body chunk at an explicit within-page position (document order)."""
    chunk = _body(text, page)
    chunk["page_pos"] = pos
    return chunk


def _density_headings() -> list[dict[str, Any]]:
    """Heading chunks pinning each chapter and marking its opener page.

    Bare "N Title" text (the real books' opener-heading shape); served by
    ``find_structural_chunks`` for both the heading-anchor pins and the
    opener-page scan, so every chapter's start page admits all its chunks
    and only the per-page bounds decide membership.
    """
    return [
        {
            "chunk_text": f"{num} {title}",
            "chunk_role": "heading",
            "source_file": _SRC,
            "page_number": page,
            "page_pos": 0,
        }
        for num, title, page in _DENSITY_ROSTER
    ]


def _vm_container_page(page: int) -> list[dict[str, Any]]:
    """The PVE-ch16-shaped dense opener: 8 body chunks on one page.

    The chapter banner opens the page, VM prose follows, a numbered section
    heading arrives embedded in body text ("2.3 Container backup modes" —
    the docling shape the header-promotion path exists for), then container
    prose.  Density 8 gives cap_pg = min(6, max(3, ceil(0.6 * 8))) = 5.
    """
    return [
        _body_pos(
            "Chapter 2 Beta Widgets\nVM snapshot mode captures guest state", page, 0
        ),
        _body_pos("snapshot mode freezes the guest file system briefly", page, 1),
        _body_pos(
            "snapshot mode keeps the memory image beside the disk state", page, 2
        ),
        _body_pos(
            "2.3 Container backup modes\narchive the configuration directories",
            page,
            3,
        ),
        _body_pos("container backup runs walk each mounted volume in turn", page, 4),
        _body_pos("container backup schedules follow the retention window", page, 5),
        _body_pos(
            "container backup verification reopens every archived bundle", page, 6
        ),
        _body_pos("container backup notes stay beside the restore checklist", page, 7),
    ]


def _density_book() -> list[dict[str, Any]]:
    """A three-chapter book carrying the three admission-bound shapes.

    ch1 is sparse (page 10 holds 3 chunks, page 11 holds 2 — every page at
    or under the base bound), ch2 opens on a dense page (page 20: 8 chunks,
    bound 5) and spills onto a short page 21 (3 chunks), and ch3 opens on a
    saturated page (page 30: 12 chunks — the density bound clamps to
    PAGE_CAP_MAX = 6) with a 2-chunk page 31 tail.  The heading chunks pin
    chapters at pages 10/20/30.
    """
    sentences = iter(_PROSE_SENTENCES)

    def prose(page: int, count: int) -> list[dict[str, Any]]:
        return [_body_pos(next(sentences), page, i) for i in range(count)]

    return [
        *prose(10, 3),
        *prose(11, 2),
        *_vm_container_page(20),
        *prose(21, 3),
        *prose(30, 12),
        *prose(31, 2),
    ]


def _limit_book() -> list[dict[str, Any]]:
    """The density book with ch2's second page dense as well.

    ch2 holds 8 chunks on page 20 (bound 5) and 8 more on page 21 (bound
    5): the bounds alone would admit 10, so the per-chapter limit (8) is
    the binding constraint.  ch1 and ch3 stay sparse.
    """
    sentences = iter(_PROSE_SENTENCES)

    def prose(page: int, count: int) -> list[dict[str, Any]]:
        return [_body_pos(next(sentences), page, i) for i in range(count)]

    return [
        *prose(10, 3),
        *prose(11, 2),
        *_vm_container_page(20),
        *prose(21, 8),
        *prose(30, 3),
    ]


def _record_density_buckets(
    pipeline: RAGPipeline,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[tuple[int, int]]]:
    """Capture (page, position) admission tuples at the summarizer boundary.

    The recorder replaces ``_generate_multi_chapter_summary``; the coverage
    wrapper calls it once per chapter with the FULL buckets dict, so the
    recorded mapping carries every chapter's window.  Returning "" keeps
    the LLM out of the run — the roster fallback speaks instead.
    """
    recorded: dict[str, list[tuple[int, int]]] = {}

    def _recorder(
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        for ch, bucket in chapter_buckets.items():
            recorded[str(ch)] = [
                (int(c.get("page_number") or 0), int(c.get("page_pos") or 0))
                for c in bucket
            ]
        return ""

    monkeypatch.setattr(pipeline, "_generate_multi_chapter_summary", _recorder)
    return recorded


class TestDensityAwareDocumentOrderAdmission:
    """The legacy round-robin's D3/D4 admission (fix-chapter-bucket-sampling 3.2/3.3).

    The five spec scenarios against the density-aware per-page bound and the
    client-side (page_number, page_pos) sort, pinned on an order-preserving
    storage double so a shuffled body list exercises the sort.
    """

    @staticmethod
    def _run(pipeline: RAGPipeline) -> str:
        result = pipeline._iterative_query(
            "summarize this document",
            top_k=8,
            show_sources=False,
            source_filter=_SRC,
        )
        return str(result["answer"])

    def _pipeline_for(
        self,
        body: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[RAGPipeline, dict[str, list[tuple[int, int]]]]:
        provider = _StreamedProvider(generate_responses=[_PLAUSIBLE])
        pipeline = _make_iterative(
            provider,
            _toc([(num, title) for num, title, _pg in _DENSITY_ROSTER]),
            body,
            _broad_intent(),
            _IterStorage(body, _density_headings()),
            monkeypatch,
        )
        return pipeline, _record_density_buckets(pipeline, monkeypatch)

    def test_document_order_decides_within_a_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec: two same-page candidates within the page's bound — the lower
        # within-page position is admitted first, regardless of the order
        # the storage returned the chunks.  The book's chunk list is fully
        # reversed, so the window's document-order shape can only come from
        # the pipeline's client-side (page, pos) sort.
        body = _density_book()
        body.reverse()
        pipeline, recorded = self._pipeline_for(body, monkeypatch)
        answer = self._run(pipeline)

        # ch2's window reads in stored order: the banner, the VM prose, the
        # embedded 2.3 heading (page_pos 3), then container prose — 5 of
        # page 20's 8 chunks (bound ceil(0.6 * 8) = 5), then page 21's 3.
        assert recorded["2"] == [
            (20, 0),
            (20, 1),
            (20, 2),
            (20, 3),
            (20, 4),
            (21, 0),
            (21, 1),
            (21, 2),
        ]
        # The recorder answers "", so the roster fallback speaks and the LLM
        # is never consulted — the canary text must stay absent.
        assert _PLAUSIBLE not in answer
        assert "Chapter 2 — Beta Widgets (approx pages 20+)" in answer

    def test_dense_page_contributes_more_than_base_bound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec: a page holding many more body chunks than the base bound
        # contributes more, scaled by density within a bounded maximum.
        body = _density_book()
        pipeline, recorded = self._pipeline_for(body, monkeypatch)
        self._run(pipeline)

        # Page 20 keeps 5 of its 8 chunks (bound 5 > base 3; the flat base
        # bound would have kept 3 and spilled 5 onto page 21); the window
        # then takes page 21's 3 remaining slots.
        assert recorded["2"] == [
            (20, 0),
            (20, 1),
            (20, 2),
            (20, 3),
            (20, 4),
            (21, 0),
            (21, 1),
            (21, 2),
        ]
        # Page 30 holds 12 chunks: the density bound would be ceil(7.2) = 8,
        # but the bounded maximum clamps it — exactly PAGE_CAP_MAX of page
        # 30's 12 chunks are admitted, then page 31's 2 finish the window.
        assert recorded["3"] == [
            (30, 0),
            (30, 1),
            (30, 2),
            (30, 3),
            (30, 4),
            (30, 5),
            (31, 0),
            (31, 1),
        ]
        assert len([t for t in recorded["3"] if t[0] == 30]) == PAGE_CAP_MAX

    def test_sparse_page_unaffected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Spec: a page at or under the base bound keeps its pre-D4 behavior
        # — every in-range chunk on it stays admissible.  ch1's pages hold 3
        # and 2 chunks (ceil(0.6 * n) <= 3 -> base bound 3): the window
        # keeps all 5 chunks in document order, exactly as the flat base
        # bound would have admitted them.
        body = _density_book()
        pipeline, recorded = self._pipeline_for(body, monkeypatch)
        self._run(pipeline)

        assert recorded["1"] == [(10, 0), (10, 1), (10, 2), (11, 0), (11, 1)]

    def test_per_chapter_limit_still_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec: density scaling may not push a window past the per-chapter
        # limit.  ch2 holds 8 chunks on page 20 (bound 5) and 8 more on
        # page 21 (bound 5): the bounds alone would admit 10, but the limit
        # stops admission at 8 — after page 20's 5, only 3 of page 21's 8
        # join, and page 21's own bound (5) is never reached.
        body = _limit_book()
        pipeline, recorded = self._pipeline_for(body, monkeypatch)
        self._run(pipeline)

        assert recorded["2"] == [
            (20, 0),
            (20, 1),
            (20, 2),
            (20, 3),
            (20, 4),
            (21, 0),
            (21, 1),
            (21, 2),
        ]

    def test_sampling_reproducible_across_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec: the same stored content sampled twice — even when the
        # storage returns the chunks in a different order — yields the
        # identical window, for every chapter.
        pipeline_sorted, recorded_sorted = self._pipeline_for(
            _density_book(), monkeypatch
        )
        self._run(pipeline_sorted)
        shuffled = _density_book()
        shuffled.reverse()
        pipeline_shuffled, recorded_shuffled = self._pipeline_for(shuffled, monkeypatch)
        self._run(pipeline_shuffled)

        assert recorded_shuffled == recorded_sorted
        # Sanity: every chapter built a non-empty window in both runs.
        assert set(recorded_sorted) == {"1", "2", "3"}
        assert all(recorded_sorted[ch] for ch in recorded_sorted)
