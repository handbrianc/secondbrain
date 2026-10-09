"""Behavioral tests for remaining RAG pipeline helper branches.

Covers async flow branches (query_async no-results, chat_async page shortcut,
LIST_SOURCES intents), the ``_agenerate`` sync fallback, page-lookup error
ladders, windowing helpers (``_split_bounded`` / ``_align_window_boundaries``),
section-label filtering, spiral detection, and the reduce-streaming recovery
branches (leak-abort retry, empty-stream retry adoption).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._mixins import _prune_implausible_metric_figures
from tests.unit.rag.test_pipeline_streaming_guards import (
    _CallbackCapture,
    _make_pipeline,
    _StreamedProvider,
)

_PLAUSIBLE = (
    "The overview explains the retrieval pipeline in careful detail here. "
    "It covers embedding queries, ranking candidates, and trimming context. "
    "Each idea appears once with a short example and no repetition at all. "
    "The closing paragraph ties the workflow together cleanly for readers."
)


def _chunk(page: int, text: str, source: str = "a.pdf", score: float = 0.9):
    return {
        "chunk_text": text,
        "page_number": page,
        "source_file": source,
        "score": score,
    }


class TestListSourcesIntent:
    """LIST_SOURCES routing in query() and chat() needs no LLM call."""

    def test_query_routes_list_sources(self) -> None:
        provider = _StreamedProvider()
        searcher = MagicMock()
        searcher.list_source_files.return_value = ["/docs/Beta.pdf", "/docs/alpha.txt"]
        pipeline = RAGPipeline(searcher=searcher, llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        result = pipeline.query("list all sources")
        assert result["list_sources"] is True
        assert "1. /docs/alpha.txt" in result["answer"]
        assert "2. /docs/Beta.pdf" in result["answer"]
        assert provider.generate_calls == []

    def test_list_sources_empty_storage(self) -> None:
        searcher = MagicMock()
        searcher.list_source_files.return_value = []
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline.query("list all sources")
        assert "don't have any documents stored yet" in result["answer"]

    def test_list_sources_failure_notice(self) -> None:
        searcher = MagicMock()
        searcher.list_source_files.side_effect = RuntimeError("boom")
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline.query("list all sources")
        assert "couldn't list the stored sources" in result["answer"]

    def test_chat_routes_list_sources_and_saves_turn(self) -> None:
        searcher = MagicMock()
        searcher.list_source_files.return_value = ["only.pdf"]
        session = MagicMock()
        session.seen_pages = {}
        pipeline = RAGPipeline(
            searcher=searcher, llm_provider=_StreamedProvider(), top_k=5
        )  # type: ignore[arg-type]
        result = pipeline.chat("list all sources", session)
        assert result["list_sources"] is True
        saved = [c.args for c in session.add_message.call_args_list]
        assert ("user", "list all sources") in saved
        assert any("only.pdf" in args[1] for args in saved if args[0] == "assistant")


class TestQueryAsyncBranches:
    """query_async: validation, no-results fallback, and show_sources."""

    @pytest.mark.asyncio
    async def test_empty_query_validation(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        result = await pipeline.query_async("   ")
        assert result["validation_error"] is True

    @pytest.mark.asyncio
    async def test_no_relevant_chunks_falls_back(self) -> None:
        class _S:
            async def search_async(self, query, top_k=5, source_filter=None):
                return [{"chunk_text": "x", "score": 0.01}]

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = _S()
        pipeline._config.rag_llm_fallback_enabled = False
        result = await pipeline.query_async("obscure query")
        assert "couldn't find" in result["answer"]

    @pytest.mark.asyncio
    async def test_success_streams_and_returns_sources(self) -> None:
        class _S:
            async def search_async(self, query, top_k=5, source_filter=None):
                return [_chunk(1, "Body content.")]

        class _P:
            async def stream_chat_async(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ):
                on_chunk("Async answer with enough grounded detail.", None)

        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=_S(), llm_provider=_P(), top_k=5, on_chunk=capture
        )  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = True
        result = await pipeline.query_async("What is the pricing?", show_sources=True)
        assert "Async answer" in result["answer"]
        assert result["sources"]
        assert "Async answer" in capture.text

    @pytest.mark.asyncio
    async def test_generation_failure_returns_error_response(self) -> None:
        class _S:
            async def search_async(self, query, top_k=5, source_filter=None):
                return [_chunk(1, "Body content.")]

        class _P:
            async def agenerate(self, prompt, temperature=0.7, max_tokens=4096):
                raise RuntimeError("llm down")

        pipeline = RAGPipeline(searcher=_S(), llm_provider=_P(), top_k=5)  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = False
        result = await pipeline.query_async("What is the pricing?")
        assert "error" in result["answer"].lower()


class TestChatAsyncBranches:
    """chat_async: page shortcut and empty-history knowledge fallback."""

    @pytest.mark.asyncio
    async def test_page_query_shortcut(self) -> None:
        class _PageStorage:
            def find_chunks(self, source_file=None, printed_page=None, **kwargs):
                if printed_page == 3:
                    return [
                        {
                            "chunk_text": "Page three verbatim body.",
                            "page_number": 3,
                            "printed_page": 3,
                        }
                    ]
                return []

        class _S:
            storage = _PageStorage()

            async def search_async(self, query, top_k=5, source_filter=None):
                return []

        session = MagicMock()
        session.seen_pages = {}
        pipeline = RAGPipeline(searcher=_S(), llm_provider=_StreamedProvider(), top_k=5)  # type: ignore[arg-type]
        result = await pipeline.chat_async("What is on page 3?", session)
        assert "Page three verbatim body." in result["answer"]

    @pytest.mark.asyncio
    async def test_no_results_uses_knowledge_fallback_with_history(self) -> None:
        class _S:
            async def search_async(self, query, top_k=5, source_filter=None):
                return [{"chunk_text": "x", "score": 0.01}]

        session = MagicMock()
        session.seen_pages = {}
        session.get_history.return_value = [
            {"role": "user", "content": "earlier question"}
        ]
        provider = _StreamedProvider(
            generate_responses=["Follow-up fallback answer with detail."]
        )
        pipeline = RAGPipeline(searcher=_S(), llm_provider=provider, top_k=5)  # type: ignore[arg-type]
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_llm_fallback_enabled = True
        result = await pipeline.chat_async("follow up question", session)
        assert "Follow-up fallback answer" in result["answer"]
        assert "earlier question" in provider.generate_calls[0]["prompt"]


class TestAgenerateSyncFallback:
    """_agenerate falls back to sync generate without provider.agenerate."""

    @pytest.mark.asyncio
    async def test_sync_fallback_used(self) -> None:
        class _SyncOnly:
            def generate(self, prompt, temperature=0.7, max_tokens=4096):
                return "Sync-generated answer with plenty of content."

        pipeline = _make_pipeline(None, on_chunk=None)
        pipeline._llm_provider = _SyncOnly()
        answer = await pipeline._agenerate("prompt")
        assert answer == "Sync-generated answer with plenty of content."


class TestPageLookupErrorLadder:
    """Footer-offset and physical-lookup exception/empty branches."""

    def test_footer_nav_fetch_exception_falls_through(self) -> None:
        # find_structural_chunks raising inside the footer lookup makes the
        # offset path return [] (the whole _page_query_chunks still returns
        # its stamped/empty result rather than raising).
        class _NavBroken:
            def find_structural_chunks(self, **kwargs):
                raise RuntimeError("nav down")

            def find_chunks(self, **kwargs):
                return []

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = MagicMock()
        pipeline._searcher.storage = _NavBroken()
        assert pipeline._page_query_chunks("What is on page 5?") == []

    def test_footer_offset_untrusted_returns_empty(self) -> None:
        class _Storage:
            def find_structural_chunks(self, **kwargs):
                return [{"page_number": 3, "chunk_text": "1 / 5"}]

            def find_chunks(
                self,
                source_file=None,
                printed_page=None,
                page_number=None,
                with_text=None,
                **kwargs,
            ):
                if page_number is not None:
                    return []
                if with_text is not None and not with_text:
                    return [{"printed_page": None, "chunk_text": "x"}]
                return []

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = MagicMock()
        pipeline._searcher.storage = _Storage()
        # Single footer sample -> offset untrusted; no printed stamps ->
        # physical fallback finds nothing for page 9 -> empty.
        assert pipeline._page_query_chunks("What is on page 9?") == []

    def test_footer_found_page_missing_returns_empty(self) -> None:
        class _Storage:
            def find_structural_chunks(self, **kwargs):
                return [
                    {"page_number": p, "chunk_text": f"{p - 2} / 5"} for p in (3, 4, 5)
                ]

            def find_chunks(
                self,
                source_file=None,
                printed_page=None,
                page_number=None,
                with_text=None,
                **kwargs,
            ):
                if page_number is not None:
                    return []  # resolved physical page has no chunks
                if with_text is not None and not with_text:
                    return [{"printed_page": None, "chunk_text": "x"}]
                return []

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = MagicMock()
        pipeline._searcher.storage = _Storage()
        assert pipeline._page_query_chunks("What is on page 1?") == []

    def test_footer_chunks_fetch_exception_returns_empty(self) -> None:
        class _Storage:
            def find_structural_chunks(self, **kwargs):
                return [
                    {"page_number": p, "chunk_text": f"{p - 2} / 5"} for p in (3, 4, 5)
                ]

            def find_chunks(
                self,
                source_file=None,
                printed_page=None,
                page_number=None,
                with_text=None,
                **kwargs,
            ):
                if page_number is not None:
                    raise RuntimeError("physical down")
                if with_text is not None and not with_text:
                    return [{"printed_page": None, "chunk_text": "x"}]
                return []

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = MagicMock()
        pipeline._searcher.storage = _Storage()
        assert pipeline._page_query_chunks("What is on page 1?") == []

    def test_no_storage_attribute(self) -> None:
        class _Bare:
            pass

        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        pipeline._searcher = _Bare()
        assert pipeline._page_query_chunks("What is on page 5?") is None


class TestWindowingHelpers:
    """_split_bounded page ordering and _align_window_boundaries repair."""

    def test_split_bounded_orders_by_page_and_caps_chars(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [
            {"chunk_text": "b" * 60, "page_number": 5},
            {"chunk_text": "a" * 60, "page_number": 2},
        ]
        windows = pipeline._split_bounded(chunks, max_chars=70)
        assert len(windows) == 2
        assert windows[0][0]["chunk_text"] == "a" * 60

    def test_split_bounded_keeps_single_chunk_budget(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        windows = pipeline._split_bounded(
            [{"chunk_text": "tiny", "page_number": 1}], max_chars=100
        )
        assert windows == [[{"chunk_text": "tiny", "page_number": 1}]]

    def test_split_bounded_single_window_when_all_fits(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [
            {"chunk_text": "short one", "page_number": 1},
            {"chunk_text": "short two", "page_number": 2},
        ]
        windows = pipeline._split_bounded(chunks, max_chars=1000)
        assert len(windows) == 1

    def test_align_moves_mid_sentence_tail_forward(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        windows = [
            [{"chunk_text": "First sentence ends here. tail frag"}],
            [{"chunk_text": "Next window body."}],
        ]
        aligned = pipeline._align_window_boundaries(windows)
        assert aligned[0][0]["chunk_text"] == "First sentence ends here."
        assert aligned[1][0]["chunk_text"] == "tail frag Next window body."

    def test_align_leaves_sentence_complete_windows(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        windows = [
            [{"chunk_text": "Complete first window text."}],
            [{"chunk_text": "Second window text."}],
        ]
        aligned = pipeline._align_window_boundaries(windows)
        assert aligned[0][0]["chunk_text"] == "Complete first window text."
        assert aligned[1][0]["chunk_text"] == "Second window text."

    def test_align_skips_windows_without_text(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        windows = [
            [{"other": 1}],
            [{"chunk_text": "Second window text."}],
        ]
        assert pipeline._align_window_boundaries(windows) == windows

    def test_align_terminal_free_tail_left_alone(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        windows = [
            [{"chunk_text": "no terminal in this text"}],
            [{"chunk_text": "Second window text."}],
        ]
        aligned = pipeline._align_window_boundaries(windows)
        assert aligned[0][0]["chunk_text"] == "no terminal in this text"


class TestReduceStreamRecovery:
    """Reduce streaming: leak abort to retry, empty-stream retry adoption."""

    def test_leak_aborts_stream_and_low_temp_retry_ships(self) -> None:
        leak = (
            " ".join(f"the count is above {90 + i} percent here" for i in range(5))
            + " enough words follow the leak to reach the minimum length bar."
        )
        provider = _StreamedProvider(
            [(leak, None)],
            generate_responses=[_PLAUSIBLE],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1", ["digest one"], "Write an overview.", parts_are_digests=True
        )
        # The leaked stream aborted; the low-temperature retry shipped.
        assert answer == _PLAUSIBLE
        assert len(provider.generate_calls) == 1

    def test_empty_stream_retries_and_adopts_draft(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1", ["digest one"], "Write an overview.", parts_are_digests=True
        )
        assert answer == _PLAUSIBLE


class TestSpiralDetection:
    """_is_reasoning_spiral hedge density and numeric escalation."""

    def test_hedge_dense_reasoning_detected(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        reasoning = (
            "no wait actually hmm hold on correction let me look again misread "
            "recheck check again let me trace the count of items in the table "
            "here and the values in the chart below the graph lines " * 6
        )
        assert pipeline._is_reasoning_spiral(reasoning) is True

    def test_escalating_percentages_detected(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        base = (
            "the value is above 90 percent, no above 110 percent, wait above "
            "130 percent, actually above 150 percent, hmm above 180 percent"
        )
        reasoning = base + " in the source text about the measured figures. " * 6
        assert pipeline._is_reasoning_spiral(reasoning) is True

    def test_plain_reasoning_not_detected(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert (
            pipeline._is_reasoning_spiral("The chapter covers widgets. " * 30) is False
        )

    def test_short_reasoning_not_detected(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._is_reasoning_spiral("no wait hmm") is False


class TestSectionLabelHelpers:
    """_detect_section_label / _leading_section_chapter / chapter filter."""

    def test_detect_section_label(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert (
            pipeline._detect_section_label("3.1 First section\nbody text", 3) == "3.1"
        )
        # Caption reference before the number suppresses the label.
        assert pipeline._detect_section_label("see figure\n3.4 elsewhere", 3) is None

    def test_leading_section_chapter(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._leading_section_chapter("9.1 CPU hot plugging") == "9"
        assert pipeline._leading_section_chapter("No numbers here") is None

    def test_leading_ignores_caption_numbers(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        assert pipeline._leading_section_chapter("table\n5.2 Widget specs") is None

    def test_filter_drops_later_chapter_opener(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [
            {"chunk_text": "3.1 Target section body", "page_number": 41},
            {"chunk_text": "Chapter 5 Next Chapter Title", "page_number": 80},
        ]
        kept = pipeline._filter_chunks_to_chapter(chunks, 3)
        assert [c["chunk_text"] for c in kept] == ["3.1 Target section body"]

    def test_filter_cuts_at_next_chapter_opener_page(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [
            {"chunk_text": "3.1 Target body", "page_number": 41},
            {"chunk_text": "Chapter 9 The Next One", "page_number": 50},
            {"chunk_text": "3.2 Content after the boundary", "page_number": 51},
        ]
        kept = pipeline._filter_chunks_to_chapter(chunks, 3)
        # Every chunk on or after the page that opens with a later "Chapter N"
        # heading is dropped, including the opener page itself.
        assert [c["page_number"] for c in kept] == [41]

    def test_filter_keeps_unrelated_prose_before_cutoff(self) -> None:
        pipeline = _make_pipeline(_StreamedProvider(), on_chunk=None)
        chunks = [
            {"chunk_text": "Plain target prose without openers", "page_number": 42},
        ]
        kept = pipeline._filter_chunks_to_chapter(chunks, 3)
        assert len(kept) == 1


class TestPruneImplausibleMetricFigures:
    """Impossible correlation values are pruned deterministically."""

    def test_out_of_bound_ic_value_pruned(self) -> None:
        text = "The model reported an average weekly IC of 3.32 and 6.68 in tests."
        out = _prune_implausible_metric_figures(text)
        assert "3.32" not in out and "6.68" not in out
        assert "IC" in out

    def test_in_bound_value_kept(self) -> None:
        text = "The information coefficient of 0.42 held across the years."
        assert _prune_implausible_metric_figures(text) == text

    def test_no_metric_no_change(self) -> None:
        text = "Plain prose with the number 42 but no metric name."
        assert _prune_implausible_metric_figures(text) == text
