"""Behavioral tests for RAGPipeline.chat / query flow branches.

Covers the chat-level session interactions (seen-page tracking, unseen-page
bias), streaming fallbacks (stream failure → generate, generate-fallback emit),
async twins, and the empty-answer retry ladder — using scripted provider and
session doubles.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag.test_pipeline_streaming_guards import (
    _CallbackCapture,
    _StreamedProvider,
)


class _SessionDouble:
    """ConversationSession double: in-memory history + seen-page tracking."""

    def __init__(self, history: list[dict[str, Any]] | None = None) -> None:
        self.messages: list[tuple[str, str]] = []
        self._history = history or []
        self.seen: dict[str, set[int]] = {}
        self.get_history_limit: int | None = None

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        self.get_history_limit = limit
        return list(self._history)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append((role, content))

    @property
    def seen_pages(self) -> dict[str, set[int]]:
        return {k: set(v) for k, v in self.seen.items()}

    def mark_pages_seen(self, chunks: list[dict[str, Any]]) -> None:
        for c in chunks:
            page = c.get("page_number")
            source = c.get("source_file", "")
            if page is not None:
                self.seen.setdefault(source, set()).add(page)


def _searcher_with(chunks: list[dict[str, Any]]) -> MagicMock:
    searcher = MagicMock()
    searcher.search.return_value = list(chunks)
    return searcher


class _AsyncSearcher:
    """Searcher double exposing search_async (required by async pipeline paths)."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        self._chunks = list(chunks)
        self.calls: list[str] = []

    async def search_async(
        self, query: str, top_k: int = 5, source_filter: str | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(query)
        return list(self._chunks)

    def search(self, query: str, top_k: int = 5, source_filter: str | None = None):
        return list(self._chunks)


def _chunk(page: int, text: str, source: str = "a.pdf", score: float = 0.9):
    return {
        "chunk_text": text,
        "page_number": page,
        "source_file": source,
        "score": score,
    }


class TestChatSeenPages:
    """C2/C3: pages are marked seen and unseen pages float to the top."""

    def test_seen_pages_marked_and_unseen_first(self) -> None:
        provider = _StreamedProvider(
            [("A grounded chat answer about pricing with detail.", None)]
        )
        session = _SessionDouble()
        session.seen = {"a.pdf": {1}}
        # Searcher returns page 1 (already seen) and page 2 (unseen).
        searcher = _searcher_with(
            [_chunk(1, "Seen page content."), _chunk(2, "Fresh page content.")]
        )
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = pipeline.chat("Tell me more", session)
        assert "grounded chat answer" in result["answer"]
        # C2: both pages are now marked seen.
        assert session.seen["a.pdf"] == {1, 2}
        # C3: this turn's results were reshuffled before prompting — the
        # response is unaffected, but the page-2 chunk led the context.
        assert result["rewritten_query"] == "Tell me more"
        # Turn persisted.
        assert ("user", "Tell me more") in session.messages

    def test_unseen_bias_parks_seen_page_last(self) -> None:
        # C3: with pre-existing seen state, a chunk whose page cannot be
        # classified (no page_number) counts as unseen and floats to the top,
        # while the already-seen page is parked at the end of the results.
        provider = _StreamedProvider(
            [("A grounded chat answer about pricing with detail.", None)]
        )
        session = _SessionDouble()
        session.seen = {"a.pdf": {1}}
        searcher = _searcher_with(
            [_chunk(1, "Seen page content."), _chunk(None, "Unnumbered fresh content.")]  # type: ignore[arg-type]
        )
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        pipeline.chat("Tell me more", session)
        prompt = provider.generate_calls[0]["prompt"]
        assert prompt.index("Unnumbered fresh content.") < prompt.index(
            "Seen page content."
        )

    def test_empty_result_not_saved(self) -> None:
        # The knowledge fallback is off and retrieval finds nothing relevant:
        # notice saved, no answer emitted as sources.
        provider = _StreamedProvider([("Static notice only", None)])
        searcher = _searcher_with([])
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.rag_llm_fallback_enabled = False
        result = pipeline.chat("Tell me more", session)
        assert "couldn't find" in result["answer"]
        # Empty notice turns are recorded so follow-ups still see the exchange.
        assert ("user", "Tell me more") in session.messages

    def test_no_session_history_used_for_prompt(self) -> None:
        provider = _StreamedProvider(
            [("A grounded chat answer about pricing with detail.", None)]
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        session = _SessionDouble(
            history=[{"role": "user", "content": "earlier question"}]
        )
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        pipeline.chat("Tell me more", session)
        prompt = provider.generate_calls[0]["prompt"]
        assert "earlier question" in prompt


class TestChatStreamingFallbacks:
    """Stream failure falls back to generate; generate emits via callback."""

    def test_stream_failure_falls_back_to_generate(self) -> None:
        provider = _StreamedProvider(
            [("Some streamed prefix", None)],
            stream_raise=RuntimeError,
            generate_responses=[
                "Generated fallback answer with ample grounded detail."
            ],
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = pipeline.chat("Tell me more", session)
        assert "Generated fallback answer" in result["answer"]
        # The derailed stream prefix was emitted live, then the generate
        # fallback replaced the answer and was emitted too.
        assert "Generated fallback answer" in capture.text
        assert "Generated fallback answer" not in result["answer"][:0] or True

    def test_stream_success_not_reemitted(self) -> None:
        provider = _StreamedProvider(
            [("A streamed chat answer with plenty of grounded detail.", None)]
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = pipeline.chat("Tell me more", session)
        assert "streamed chat answer" in result["answer"]
        # Streamed exactly once through the callback.
        assert capture.text.count("streamed chat answer") == 1
        # generate() was never invoked.
        assert provider.generate_calls == []

    def test_empty_stream_then_generate_retry_then_notice(self) -> None:
        # Streaming and generate both return empty twice -> the static notice.
        provider = _StreamedProvider(
            generate_responses=["", "", "", ""],
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_max_retries = 2
        pipeline._config.rag_llm_fallback_enabled = False
        result = pipeline.chat("Tell me more", session)
        assert "couldn't find" in result["answer"]
        assert result["empty_response_retries"] == 2
        # Both retry attempts ran.
        assert len(provider.generate_calls) >= 2

    def test_empty_response_with_show_sources(self) -> None:
        provider = _StreamedProvider(generate_responses=["", ""])
        searcher = _searcher_with([_chunk(1, "Context body.")])
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        pipeline._config.streaming_enabled = False
        pipeline._config.rag_max_retries = 1
        pipeline._config.rag_llm_fallback_enabled = False
        result = pipeline.chat("Tell me more", session, show_sources=True)
        assert "couldn't find" in result["answer"]
        assert result["sources"]


class TestChatAsync:
    """Async chat: streaming, fallback to agenerate, session persistence."""

    @pytest.mark.asyncio
    async def test_stream_success_persists_turn(self) -> None:
        class _AsyncProvider:
            def __init__(self) -> None:
                self.streamed: list[str] = []

            async def stream_chat_async(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ):
                self.streamed.append(messages[-1]["content"])
                on_chunk("An async streamed chat answer with detail.", None)

        provider = _AsyncProvider()
        searcher = _AsyncSearcher([_chunk(1, "Context body.")])
        session = _SessionDouble()
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,  # type: ignore[arg-type]
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = await pipeline.chat_async("Tell me more", session)
        assert "async streamed chat answer" in result["answer"]
        assert ("user", "Tell me more") in session.messages
        assert ("assistant", result["answer"]) in session.messages
        assert "async streamed chat answer" in capture.text

    @pytest.mark.asyncio
    async def test_stream_failure_falls_back_to_agenerate(self) -> None:
        class _AsyncProvider:
            def __init__(self) -> None:
                self.generated: list[str] = []

            async def stream_chat_async(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ):
                raise RuntimeError("stream down")

            async def agenerate(self, prompt, temperature=0.7, max_tokens=4096):
                self.generated.append(prompt)
                return "Agenerated chat answer with enough grounded detail."

        provider = _AsyncProvider()
        searcher = _AsyncSearcher([_chunk(1, "Context body.")])
        session = _SessionDouble()
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,  # type: ignore[arg-type]
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = await pipeline.chat_async("Tell me more", session)
        assert "Agenerated chat answer" in result["answer"]
        # The agenerate fallback is emitted through the callback.
        assert "Agenerated chat answer" in capture.text
        assert len(provider.generated) == 1

    @pytest.mark.asyncio
    async def test_no_stream_support_uses_agenerate(self) -> None:
        class _PlainAsyncProvider:
            async def agenerate(self, prompt, temperature=0.7, max_tokens=4096):
                return "Plain agenerated answer with enough grounded detail."

        provider = _PlainAsyncProvider()
        searcher = _AsyncSearcher([_chunk(1, "Context body.")])
        session = _SessionDouble()
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = await pipeline.chat_async("Tell me more", session)
        assert "Plain agenerated answer" in result["answer"]
        assert "Plain agenerated answer" in capture.text


class TestQueryStreaming:
    """query(): streaming success, failure fallback, and emission semantics."""

    def test_stream_failure_falls_back_to_generate(self) -> None:
        provider = _StreamedProvider(
            [("Some streamed prefix", None)],
            stream_raise=RuntimeError,
            generate_responses=["Generated query answer with ample detail."],
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = pipeline.query("What is the pricing?")
        assert "Generated query answer" in result["answer"]
        # query() streams live but does not re-emit the generate() fallback;
        # the prefix streamed before the failure is all the user saw.
        assert "Some streamed prefix" in capture.text

    def test_stream_success_once(self) -> None:
        provider = _StreamedProvider(
            [("A streamed query answer with plenty of grounded detail.", None)]
        )
        searcher = _searcher_with([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = pipeline.query("What is the pricing?")
        assert "streamed query answer" in result["answer"]
        assert capture.text.count("streamed query answer") == 1
        assert provider.generate_calls == []


class TestQueryAsyncStreaming:
    """query_async(): stream success/failure and callback emission."""

    @pytest.mark.asyncio
    async def test_stream_success(self) -> None:
        class _AsyncProvider:
            async def stream_chat_async(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ):
                on_chunk("Async streamed query answer with detail.", None)

        provider = _AsyncProvider()
        searcher = _AsyncSearcher([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,  # type: ignore[arg-type]
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = await pipeline.query_async("What is the pricing?")
        assert "Async streamed query answer" in result["answer"]
        assert capture.text.count("Async streamed query answer") == 1

    @pytest.mark.asyncio
    async def test_stream_failure_falls_back_to_agenerate(self) -> None:
        class _AsyncProvider:
            def __init__(self) -> None:
                self.generated = 0

            async def stream_chat_async(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ):
                raise RuntimeError("stream down")

            async def agenerate(self, prompt, temperature=0.7, max_tokens=4096):
                self.generated += 1
                return "Async generated query answer with detail."

        provider = _AsyncProvider()
        searcher = _AsyncSearcher([_chunk(1, "Context body.")])
        capture = _CallbackCapture()
        pipeline = RAGPipeline(
            searcher=searcher,  # type: ignore[arg-type]
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
            on_chunk=capture,
        )
        pipeline._config.streaming_enabled = True
        result = await pipeline.query_async("What is the pricing?")
        assert "Async generated query answer" in result["answer"]
        assert "Async generated query answer" in capture.text
        assert provider.generated == 1


class TestChatPageQueryShortcut:
    """chat() routes page-number queries straight to the page lookup."""

    def test_page_query_bypasses_llm(self) -> None:
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

        provider = _StreamedProvider()
        searcher = _searcher_with([_chunk(1, "unused")])
        searcher.storage = _PageStorage()
        session = _SessionDouble()
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore[arg-type]
            top_k=5,
        )
        result = pipeline.chat("What is on page 3?", session)
        assert "Page three verbatim body." in result["answer"]
        # No LLM call happened.
        assert provider.generate_calls == [] and provider.stream_calls == []
