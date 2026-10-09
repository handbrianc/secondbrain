"""Behavioral tests for the iterative (chapter/section enumeration) query path.

Covers ``_iterative_query`` routing: missing structure, missing target chapter,
the generic top-k fall-through, single-chapter/section overview generation,
multi-chapter map-reduce, storage-failure fallbacks, and the helper machinery
they drive (``_generate_multi_chapter_summary``, ``_generate_single_chapter_summary``,
``_split_bounded``/``_align_window_boundaries``, section-label filtering).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.rag.intent_parser import IntentDecision, QueryIntent
from secondbrain.rag.pipeline import RAGPipeline
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
