"""Behavioral tests for RAG fallback, routing, and page-lookup machinery.

Covers the ``_FallbackMixin`` grounded-retry/contextual-search contract, the
``_RoutingMixin`` page-number lookup ladder (printed stamps → footer offset →
physical index), definition-recall union, and scoped-query alias stripping —
all against hand-rolled storage doubles, no mocks at the domain layer.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag.test_pipeline_streaming_guards import (
    _CallbackCapture,
    _make_pipeline,
    _StreamedProvider,
)


class _PageStorage:
    """Storage double for the printed-page lookup ladder."""

    def __init__(
        self,
        *,
        printed: dict[int, list[dict[str, Any]]] | None = None,
        physical: dict[int, list[dict[str, Any]]] | None = None,
        nav: list[dict[str, Any]] | None = None,
        stamps: bool = True,
    ) -> None:
        self._printed = printed or {}
        self._physical = physical or {}
        self._nav = nav or []
        self._stamps = stamps
        self.printed_calls: list[int] = []
        self.physical_calls: list[int] = []

    def find_chunks(
        self,
        source_file: str | None = None,
        printed_page: int | None = None,
        page_number: Any = None,
        with_text: bool = True,
    ) -> list[dict[str, Any]]:
        if printed_page is not None:
            self.printed_calls.append(printed_page)
            return list(self._printed.get(printed_page, []))
        if page_number is not None:
            if isinstance(page_number, list):
                out: list[dict[str, Any]] = []
                for p in page_number:
                    self.physical_calls.append(p)
                    out.extend(self._physical.get(p, []))
                return out
            self.physical_calls.append(page_number)
            return list(self._physical.get(page_number, []))
        if not with_text:
            return [{"printed_page": 1 if self._stamps else None, "chunk_text": "x"}]
        return []

    def find_structural_chunks(self, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self._nav)


def _page_chunk(page: int, text: str, *, marker: bool = False) -> dict[str, Any]:
    body = f"[ {page} ] {text}" if marker else text
    return {"chunk_text": body, "page_number": page, "printed_page": page}


class TestSaveTurn:
    """_save_turn skips empty answers and persists pairs."""

    def test_saves_user_and_assistant_messages(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        session = MagicMock()
        pipeline._save_turn(session, "the query", "the answer")
        assert [c.args for c in session.add_message.call_args_list] == [
            ("user", "the query"),
            ("assistant", "the answer"),
        ]

    def test_empty_answer_not_saved(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        session = MagicMock()
        pipeline._save_turn(session, "q", "   ")
        session.add_message.assert_not_called()


class TestContextualSearch:
    """Grounded follow-up detection and contextual re-retrieval."""

    def test_no_history_returns_none(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._contextual_search("what now?", None, 5) is None

    def test_unrelated_query_returns_none(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        history = [{"role": "assistant", "content": "Brian Hand wrote the report."}]
        # "Speed of light" shares no tokens with the history entities.
        assert pipeline._contextual_search("speed of light", history, 5) is None

    def test_follow_up_searches_augmented_query(self) -> None:
        provider = _StreamedProvider()
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand climbed the ridge", "score": 0.9}
        ]
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        history = [
            {"role": "assistant", "content": "Brian Hand wrote the ADOS-2 report."}
        ]
        chunks = pipeline._contextual_search("what did brian claim", history, 5)
        assert chunks is not None
        searched = searcher.search.call_args[0][0]
        assert "Brian Hand" in searched
        assert "what did brian claim" in searched

    def test_search_failure_returns_none(self, caplog) -> None:
        searcher = MagicMock()
        searcher.search.side_effect = RuntimeError("down")
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        with caplog.at_level(logging.WARNING):
            assert pipeline._contextual_search("brian follow-up", history, 5) is None
        assert any("re-retrieval failed" in r.message for r in caplog.records)

    def test_irrelevant_chunks_return_none(self) -> None:
        searcher = MagicMock()
        searcher.search.return_value = [{"chunk_text": "x", "score": 0.01}]
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        assert pipeline._contextual_search("brian follow-up", history, 5) is None

    @pytest.mark.asyncio
    async def test_async_follow_up_uses_search_async(self) -> None:
        class _AsyncSearcher:
            def __init__(self) -> None:
                self.calls: list[str] = []

            async def search_async(self, query: str, top_k: int = 5):
                self.calls.append(query)
                return [{"chunk_text": "Brian Hand report body", "score": 0.9}]

        searcher = _AsyncSearcher()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        chunks = await pipeline._contextual_search_async("brian claim", history, 5)
        assert chunks is not None
        assert "Brian Hand" in searcher.calls[0]

    @pytest.mark.asyncio
    async def test_async_falls_back_to_sync_search(self) -> None:
        searcher = MagicMock(spec=["search"])
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand report body", "score": 0.9}
        ]
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        chunks = await pipeline._contextual_search_async("brian claim", history, 5)
        assert chunks is not None
        assert "Brian Hand" in searcher.search.call_args[0][0]


class TestGroundedContextRetry:
    """The grounded retry returns a grounded dict or None."""

    def test_streams_answer_and_marks_grounded(self) -> None:
        provider = _StreamedProvider(
            [("Brian answered from the retrieved context with detail.", None)]
        )
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=provider, top_k=5, on_chunk=capture
        )  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = True
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        result = pipeline._grounded_context_retry("brian claim", history, 5, True)
        assert result is not None
        assert result["grounded_retry"] is True
        assert "Brian answered" in result["answer"]
        assert result["sources"]
        # Streamed content reached the callback; not re-emitted.
        assert "Brian answered" in capture.text

    def test_generation_failure_returns_none(self, caplog) -> None:
        provider = _StreamedProvider([], stream_raise=RuntimeError)
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=provider, top_k=5, on_chunk=capture
        )  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = True
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        with caplog.at_level(logging.WARNING):
            assert (
                pipeline._grounded_context_retry("brian claim", history, 5, False)
                is None
            )
        assert any("Grounded generation failed" in r.message for r in caplog.records)

    def test_empty_answer_returns_none(self) -> None:
        provider = _StreamedProvider([("", None)])
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=provider, top_k=5, on_chunk=capture
        )  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = True
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        assert (
            pipeline._grounded_context_retry("brian claim", history, 5, False) is None
        )

    def test_not_a_follow_up_returns_none(self) -> None:
        searcher = MagicMock()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        assert (
            pipeline._grounded_context_retry("speed of light", None, 5, False) is None
        )
        searcher.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_retry_grounds_via_agenerate(self) -> None:
        provider = _StreamedProvider(
            generate_responses=["Grounded async answer with enough detail to pass."],
        )
        searcher = MagicMock(spec=["search"])
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = False
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        result = await pipeline._grounded_context_retry_async(
            "brian claim", history, 5, True
        )
        assert result is not None
        assert result["grounded_retry"] is True

    @pytest.mark.asyncio
    async def test_async_retry_failure_returns_none(self, caplog) -> None:
        provider = _StreamedProvider(
            generate_responses=["Grounded async answer with enough detail here."],
        )

        async def _boom(
            prompt: str, temperature: float = 0.7, max_tokens: int = 4096
        ) -> str:
            raise RuntimeError("down")

        provider.agenerate = _boom  # type: ignore[method-assign]
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = False
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        with caplog.at_level(logging.WARNING):
            result = await pipeline._grounded_context_retry_async(
                "brian claim", history, 5, False
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_async_retry_empty_answer_returns_none(self) -> None:
        provider = _StreamedProvider(generate_responses=["   "])
        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Brian Hand body text", "score": 0.9}
        ]
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = False
        history = [{"role": "assistant", "content": "Brian Hand wrote it."}]
        assert (
            await pipeline._grounded_context_retry_async(
                "brian claim", history, 5, False
            )
            is None
        )


class TestHandleNoResults:
    """No-results notice plus optional knowledge fallback."""

    def test_notice_without_fallback(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._config.rag_llm_fallback_enabled = False
        out = pipeline._handle_no_results("What is quantum foam?")
        assert "couldn't find relevant documents" in out.lower()
        assert "quantum foam" in out

    def test_knowledge_fallback_appends_answer(self) -> None:
        provider = _StreamedProvider(
            [("Knowledge answer: quantum foam is spacetime turbulence.", None)]
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        pipeline._config.rag_llm_fallback_enabled = True
        out = pipeline._handle_no_results("What is quantum foam?")
        assert "Knowledge answer" in out
        assert "couldn't find" in out
        assert "quantum foam" in provider.stream_calls[0]["prompt"]
        assert "Knowledge answer" in capture.text

    def test_fallback_failure_returns_notice(self, caplog) -> None:
        provider = _StreamedProvider([], stream_raise=RuntimeError)
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        pipeline._config.rag_llm_fallback_enabled = True
        with caplog.at_level(logging.WARNING):
            out = pipeline._handle_no_results("What is quantum foam?")
        assert "Knowledge answer" not in out
        assert "couldn't find" in out
        assert any("knowledge fallback failed" in r.message for r in caplog.records)

    def test_fallback_result_emitted_when_not_streamed(self) -> None:
        provider = _StreamedProvider(
            generate_responses=["A fallback answer with plenty of detail here."],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_llm_fallback_enabled = True
        capture = _CallbackCapture()
        pipeline._on_chunk = capture
        out = pipeline._handle_no_results("What is quantum foam?")
        assert "fallback answer" in out
        assert "fallback answer" in capture.text

    @pytest.mark.asyncio
    async def test_async_fallback_uses_agenerate(self) -> None:
        provider = _StreamedProvider(
            generate_responses=["Async knowledge fallback with a full answer."],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_llm_fallback_enabled = True
        out = await pipeline._handle_no_results_async("What is quantum foam?")
        assert "Async knowledge fallback" in out

    @pytest.mark.asyncio
    async def test_async_fallback_failure_returns_notice(self, caplog) -> None:
        provider = _StreamedProvider(
            generate_responses=["retry generated answer"],
        )

        async def _boom(
            prompt: str, temperature: float = 0.7, max_tokens: int = 4096
        ) -> str:
            raise RuntimeError("down")

        provider.agenerate = _boom  # type: ignore[method-assign]
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_llm_fallback_enabled = True
        with caplog.at_level(logging.WARNING):
            out = await pipeline._handle_no_results_async("What is quantum foam?")
        assert "couldn't find" in out
        assert any("knowledge fallback" in r.message for r in caplog.records)


class TestPageQueryLadder:
    """Printed-page resolution: stamps → footer offset → physical index."""

    def test_non_page_query_returns_none(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = MagicMock()
        assert pipeline._page_query_chunks("what is a widget?") is None

    def test_no_storage_support_returns_none(self) -> None:
        searcher = MagicMock(spec=["search"])  # no .storage attr
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        assert pipeline._page_query_chunks("what is on page 5?") is None

    def test_query_short_circuits_on_page_lookup(self) -> None:
        # A page-number query returns the verbatim page straight from
        # query() — no generation is invoked.
        provider = _StreamedProvider()
        storage = _PageStorage(
            printed={5: [_page_chunk(5, "[ 5 ] Intro line.", marker=False)]}
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        result = pipeline.query("What is on page 5?")
        assert "Intro line." in result["answer"]
        assert result["query"] == "What is on page 5?"
        assert provider.generate_calls == []

    def test_printed_stamp_hit_stitches_page_text(self) -> None:
        storage = _PageStorage(
            printed={
                5: [
                    _page_chunk(5, "[ 5 ] Intro line.", marker=False),
                    _page_chunk(5, "Second chunk body."),
                ]
            }
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 5?")
        assert result is not None
        assert "Intro line." in result["answer"]
        assert "Second chunk body." in result["answer"]
        assert "[ 5 ]" not in result["answer"]
        assert storage.printed_calls == [5]

    def test_page_not_found_notice(self) -> None:
        storage = _PageStorage(printed={})
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 9?")
        assert result is not None
        assert "do not contain a page matching" in result["answer"]
        assert result["sources"] == []

    def test_footer_offset_lookup_resolves_page(self) -> None:
        # Stamped lookup misses; consistent footers ("3 / 5" on physical 3..5
        # implies offset 2) resolve printed 1 -> physical 3.
        storage = _PageStorage(
            printed={},
            physical={
                3: [_page_chunk(3, "Offset page three body.")],
            },
            nav=[
                {"page_number": 3, "chunk_text": "1 / 5"},
                {"page_number": 4, "chunk_text": "2 / 5"},
                {"page_number": 5, "chunk_text": "3 / 5"},
            ],
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 1?")
        assert result is not None
        assert "Offset page three body." in result["answer"]
        assert result["sources"][0].get("page_lookup_offset") == 2

    def test_footer_offset_untrusted_falls_to_physical(self) -> None:
        # Inconsistent footers -> offset rejected; no printed stamps anywhere
        # -> physical index lookup for page 4.
        storage = _PageStorage(
            printed={},
            physical={4: [_page_chunk(4, "Physical page four body.")]},
            nav=[{"page_number": 3, "chunk_text": "1 / 5"}],  # <3 samples
            stamps=False,
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 4?")
        assert result is not None
        assert "Physical page four body." in result["answer"]
        assert result["sources"][0].get("page_lookup_fallback") == "physical"

    def test_physical_lookup_not_used_when_stamps_exist(self) -> None:
        # Stamps exist but page 9 has none: footer offset also misses ->
        # answer is the not-found notice (physical lookup skipped).
        storage = _PageStorage(
            printed={},
            physical={9: [_page_chunk(9, "Should not be reached.")]},
            nav=[{"page_number": 3, "chunk_text": "1 / 5"}],
            stamps=True,
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 9?")
        assert result is not None
        assert "do not contain a page matching" in result["answer"]
        assert "Should not be reached" not in result["answer"]

    def test_lookup_exception_falls_back_to_semantic(self, caplog) -> None:
        class _BrokenStorage(_PageStorage):
            def find_chunks(self, **kwargs: Any) -> list[dict[str, Any]]:
                raise RuntimeError("storage exploded")

        searcher = MagicMock()
        searcher.storage = _BrokenStorage()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        with caplog.at_level(logging.WARNING):
            assert pipeline._page_query_chunks("What is on page 3?") is None
        assert any("Page lookup failed" in r.message for r in caplog.records)

    def test_expand_page_chunks_merges_page_siblings(self) -> None:
        storage = _PageStorage(
            printed={
                2: [_page_chunk(2, "Marker chunk text.", marker=True)],
            },
            physical={
                2: [
                    {"chunk_text": "Marker chunk text.", "page_number": 2},
                    {
                        "chunk_text": "Continuation without marker.",
                        "page_number": 2,
                    },
                ],
            },
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline._answer_page_query("What is on page 2?")
        assert result is not None
        assert "Continuation without marker." in result["answer"]

    def test_footer_lookup_untrusted_and_stamped_present(self) -> None:
        # Footers inconsistent AND printed stamps exist somewhere else: the
        # physical fallback must stay off.
        storage = _PageStorage(
            printed={},
            nav=[{"page_number": 3, "chunk_text": "1 / 5"}],
            stamps=True,
        )
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        assert pipeline._page_query_chunks("What is on page 8?") == []

    @pytest.mark.asyncio
    async def test_async_page_query_returns_page_text(self) -> None:
        storage = _PageStorage(printed={7: [_page_chunk(7, "Page seven body.")]})
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = await pipeline._answer_page_query_async("What is on page 7?")
        assert result is not None
        assert "Page seven body." in result["answer"]

    @pytest.mark.asyncio
    async def test_async_page_query_not_found_notice(self) -> None:
        storage = _PageStorage(printed={})
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = await pipeline._answer_page_query_async("What is on page 12?")
        assert result is not None
        assert "do not contain a page matching" in result["answer"]

    @pytest.mark.asyncio
    async def test_async_non_page_query_returns_none(self) -> None:
        searcher = MagicMock()
        searcher.storage = _PageStorage()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        assert await pipeline._answer_page_query_async("what is a widget?") is None


class TestStitchPageText:
    """Verbatim stitching drops markers, stubs, and footers."""

    def test_empty_chunks_stitch_to_empty(self) -> None:
        chunks = [
            {"chunk_text": ""},
            {"chunk_text": "[ 3 ]"},
            {"chunk_text": "78 / 634"},
        ]
        assert RAGPipeline._stitch_page_text(chunks) == ""

    def test_overlapping_chunks_are_collapsed(self) -> None:
        overlap = "Page two continues the printed text about widgets in detail."
        chunks = [
            {"chunk_text": f"Page two opens here. {overlap}"},
            {"chunk_text": f"{overlap} Extra closing content appears right here."},
        ]
        stitched = RAGPipeline._stitch_page_text(chunks)
        assert "opens here." in stitched
        assert "Extra closing content appears right here." in stitched
        assert stitched.count(overlap) == 1


class TestScopedSearchQuery:
    """Source-reference stripping for scoped retrieval."""

    def _pipeline_with_router(self, name: str, source_file: str) -> RAGPipeline:
        searcher = MagicMock()
        searcher.storage = None
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        pipeline._document_router = MagicMock()
        pipeline._document_router.extract_document_name.return_value = name
        pipeline._document_router.resolve_source_file.return_value = source_file
        return pipeline

    def test_strips_resolved_path(self) -> None:
        pipeline = self._pipeline_with_router(
            "tampa report", "/docs/Tampa International Airport.m4a"
        )
        stripped = pipeline._scoped_search_query("summarize the tampa report please")
        assert "tampa report" not in stripped
        assert "summarize" in stripped and "please" in stripped

    def test_falls_back_to_original_when_strip_empties_query(self) -> None:
        pipeline = self._pipeline_with_router(
            "tampa report", "/docs/Tampa International Airport.m4a"
        )
        assert pipeline._scoped_search_query("tampa report") == "tampa report"


class TestUnionOpenerChunks:
    """Definition-recall union of opener-adjacent body chunks."""

    def test_non_definition_query_unchanged(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [{"chunk_text": "body", "score": 0.8}]
        assert (
            pipeline._union_opener_chunks("list all chapters", chunks, None) is chunks
        )

    def test_no_storage_support_unchanged(self) -> None:
        searcher = MagicMock(spec=["search"])
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        chunks = [{"chunk_text": "body", "score": 0.8}]
        assert pipeline._union_opener_chunks("what is a widget", chunks, None) is chunks

    def test_no_keywords_unchanged(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [{"chunk_text": "body", "score": 0.8}]
        assert pipeline._union_opener_chunks("what is it? 123", chunks, None) is chunks

    def test_opener_body_chunks_appended_and_deduped(self) -> None:
        class _Storage:
            def __init__(self) -> None:
                self.structural_calls: list[dict[str, Any]] = []

            def find_structural_chunks(self, **kwargs: Any):
                self.structural_calls.append(kwargs)
                return [
                    {"chunk_text": "Chapter 1", "page_number": 4, "page_pos": 0},
                    {
                        "chunk_text": "Widgets explained",
                        "page_number": 4,
                        "page_pos": 1,
                    },
                ]

            def get_body_chunks(self, source_file: str | None = None):
                return [
                    {
                        "chunk_text": "A widget is a small device for testing.",
                        "page_number": 4,
                        "page_pos": 2,
                    },
                    {
                        "chunk_text": "Unrelated trailing chapter body text.",
                        "page_number": 9,
                        "page_pos": 0,
                    },
                ]

        storage = _Storage()
        searcher = MagicMock()
        searcher.storage = storage
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        chunks = [
            {
                "chunk_text": "Similarity hit about widgets.",
                "score": 0.9,
                "source_file": "a.pdf",
            }
        ]
        merged = pipeline._union_opener_chunks("what is a widget", chunks, None)
        recall = [c for c in merged if c.get("definition_recall")]
        assert len(recall) == 1
        assert recall[0]["score"] == 0.5
        assert "widget is a small device" in recall[0]["chunk_text"]
        assert merged[0]["score"] == 0.9  # similarity ranking untouched

    def test_structure_fetch_failure_returns_original(self, caplog) -> None:
        class _BadStorage:
            def find_structural_chunks(self, **kwargs: Any):
                raise RuntimeError("boom")

        searcher = MagicMock()
        searcher.storage = _BadStorage()
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        chunks = [
            {"chunk_text": "body about widgets", "score": 0.8, "source_file": "a.pdf"}
        ]
        with caplog.at_level(logging.WARNING):
            assert (
                pipeline._union_opener_chunks("what is a widget", chunks, None)
                is chunks
            )
        assert any("union skipped" in r.message for r in caplog.records)


class TestChapterOpenerPages:
    """Banner + title heading pairs mark opener pages."""

    def test_pair_on_same_page_marks_opener(self) -> None:
        openers = [
            {"chunk_text": "Chapter 1", "page_number": 4, "page_pos": 0},
            {"chunk_text": "Widgets explained", "page_number": 4, "page_pos": 1},
            {"chunk_text": "Chapter 2", "page_number": 5, "page_pos": 0},
            {"chunk_text": "Chapter 3", "page_number": 6, "page_pos": 0},
        ]
        assert RAGPipeline._chapter_opener_pages(openers) == {4}

    def test_banner_adjacent_to_banner_not_marked(self) -> None:
        openers = [
            {"chunk_text": "Chapter 1", "page_number": 4, "page_pos": 0},
            {"chunk_text": "Chapter 2", "page_number": 4, "page_pos": 1},
        ]
        assert RAGPipeline._chapter_opener_pages(openers) == set()


class TestApplyHeadingDiversity:
    """Heading-role caps keep the first few and never empty the set."""

    def test_caps_excess_headings(self) -> None:
        chunks = [
            {"chunk_text": f"Heading {i}", "chunk_role": "heading"} for i in range(5)
        ] + [{"chunk_text": "body", "score": 0.8}]
        capped = RAGPipeline._apply_heading_diversity(chunks)
        assert sum(1 for c in capped if c.get("chunk_role") == "heading") == 2
        assert {"chunk_text": "body", "score": 0.8} in capped

    def test_all_headings_set_is_untouched(self) -> None:
        chunks = [
            {"chunk_text": f"Heading {i}", "chunk_role": "heading"} for i in range(5)
        ]
        assert RAGPipeline._apply_heading_diversity(chunks) == chunks


class TestTrimRehashedTail:
    """A trailing restatement with nothing new is dropped."""

    def test_short_text_unchanged(self) -> None:
        assert RAGPipeline._trim_rehashed_tail("One sentence. Two sentences.") == (
            "One sentence. Two sentences."
        )

    def test_redundant_tail_cut(self) -> None:
        body = (
            "The widget system works. It has three parts. "
            "Part one is the frame. Part two is the motor. "
            "Part three is the blade. The frame holds it. "
        )
        tail = (
            "The widget system works. It has three parts. "
            "Part one is the frame. Part two is the motor. "
            "Part three is the blade."
        )
        trimmed = RAGPipeline._trim_rehashed_tail(body + tail)
        # The trailing restatement (and the single new sentence before it,
        # which only repeats the frame topic) is dropped.
        assert "The frame holds it." not in trimmed
        assert "Part three is the blade." in trimmed

    def test_progressive_tail_kept(self) -> None:
        head = (
            "The widget system works. It has three parts. "
            "Part one is the frame. Part two is the motor. "
            "Part three is the blade. Assembly took one hour. "
        )
        tail = (
            "Safety improved later. The 2019 revision added guards. "
            "Certification followed in 2020. Costs fell by half."
        )
        assert RAGPipeline._trim_rehashed_tail(head + tail) == (head + tail).strip()


class TestRelevanceGateHelpers:
    """_has_relevant_chunks threshold behaviour."""

    def test_score_less_chunks_pass(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._has_relevant_chunks([{"chunk_text": "x"}]) is True

    def test_scored_chunks_gate(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._has_relevant_chunks([{"score": 0.01}], threshold=0.3) is False
        assert pipeline._has_relevant_chunks([{"score": 0.4}], threshold=0.3) is True
