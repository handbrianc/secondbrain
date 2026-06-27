"""Unit tests for RAGPipeline streaming wiring.

These tests verify that the RAG pipeline correctly routes requests to either
stream_chat or generate based on config.streaming_enabled and provider capabilities.
"""

from collections.abc import Callable, Sequence
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.search import Searcher


class StreamTracker:
    """Tracks streaming method calls and simulates provider behavior.

    Provides clean call tracking without MagicMock complications.
    """

    def __init__(
        self,
        supports_streaming: bool = True,
        stream_raises: bool = False,
        stream_produces_empty: bool = False,
    ) -> None:
        self.generate_called = False
        self.stream_chat_called = False
        self.agenerate_called = False
        self.stream_chat_async_called = False
        self._supports_streaming = supports_streaming
        self._stream_raises = stream_raises
        self._stream_produces_empty = stream_produces_empty

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        self.generate_called = True
        return "Generated answer"

    def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        on_chunk: Callable[[str, Any | None], None],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        self.stream_chat_called = True
        if self._stream_raises:
            raise RuntimeError("simulated stream failure")
        if self._stream_produces_empty:
            return ""
        on_chunk("Streamed ", None)
        on_chunk("answer", None)
        return ""

    async def agenerate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        self.agenerate_called = True
        return "Async generated answer"

    async def stream_chat_async(
        self,
        messages: Sequence[dict[str, str]],
        on_chunk: Callable[[str, Any | None], None],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        self.stream_chat_async_called = True
        if self._stream_raises:
            raise RuntimeError("simulated async stream failure")
        if self._stream_produces_empty:
            return ""
        on_chunk("Async ", None)
        on_chunk("streamed", None)
        return ""


class GenerateOnlyTracker:
    """Provider with only generate(), no streaming."""

    def __init__(self) -> None:
        self.generate_called = False

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        self.generate_called = True
        return "Generated (no streaming available)"


def _make_mock_searcher() -> MagicMock:
    """Create a mock Searcher that returns a dummy chunk."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = [
        {"chunk_text": "Test context", "source_file": "test.pdf", "page": 1}
    ]
    mock.search_async = AsyncMock(
        return_value=[
            {"chunk_text": "Test context", "source_file": "test.pdf", "page": 1}
        ]
    )
    return mock


def _make_pipeline_for_tracker(tracker: StreamTracker | GenerateOnlyTracker) -> RAGPipeline:
    """Create RAGPipeline with given tracker as the LLM provider."""
    return RAGPipeline(
        searcher=_make_mock_searcher(),
        llm_provider=tracker,  # type: ignore
        top_k=5,
        context_window=5,
    )


class TestStreamingEnabledWithStreamChat:
    """Tests for streaming enabled with provider that has stream_chat."""

    def test_streaming_enabled_calls_stream_chat(self) -> None:
        """Test that streaming enabled + provider with stream_chat takes streaming path.

        When config.streaming_enabled=True and provider has stream_chat,
        the pipeline should call stream_chat instead of generate.
        """
        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = pipeline.query("Test query")

        assert tracker.stream_chat_called, "stream_chat should have been called"
        assert not tracker.generate_called, "generate should NOT be called"
        assert "answer" in result

    def test_streaming_enabled_chat_calls_stream_chat(self) -> None:
        """Test that streaming enabled + chat with stream_chat takes streaming path."""
        from secondbrain.conversation import ConversationSession

        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "Hello")

        result = pipeline.chat("Test query", session)

        assert tracker.stream_chat_called, "stream_chat should have been called in chat"
        assert not tracker.generate_called, "generate should NOT be called in chat"
        assert "answer" in result


class TestStreamingEnabledWithoutStreamChat:
    """Tests for streaming enabled but provider lacks stream_chat."""

    def test_streaming_enabled_provider_lacks_stream_chat(self) -> None:
        """Test that streaming enabled but no stream_chat falls back to generate.

        When config.streaming_enabled=True but provider only has generate(),
        the pipeline should call generate().
        """
        tracker = GenerateOnlyTracker()
        pipeline = _make_pipeline_for_tracker(tracker)

        result = pipeline.query("Test query")

        assert tracker.generate_called, "generate should have been called as fallback"
        assert "answer" in result


class TestStreamingEnabledStreamChatRaises:
    """Tests for streaming enabled but stream_chat throws."""

    def test_streaming_enabled_stream_chat_raises_falls_back(self) -> None:
        """Test that stream_chat raising Exception falls back to generate.

        When stream_chat raises any exception, the pipeline should
        catch it and fall back to generate().
        """
        tracker = StreamTracker(supports_streaming=True, stream_raises=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = pipeline.query("Test query")

        assert tracker.stream_chat_called, "stream_chat should have been attempted"
        assert tracker.generate_called, "generate should have been called as fallback"
        assert "answer" in result

    def test_streaming_enabled_chat_stream_chat_raises_falls_back(self) -> None:
        """Test that chat's stream_chat raising falls back to generate."""
        from secondbrain.conversation import ConversationSession

        tracker = StreamTracker(supports_streaming=True, stream_raises=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "Hello")

        result = pipeline.chat("Test query", session)

        assert tracker.stream_chat_called, "stream_chat should have been attempted"
        assert tracker.generate_called, "generate should have been called as fallback"
        assert "answer" in result


class TestStreamingDisabled:
    """Tests for streaming disabled (False)."""

    def test_streaming_disabled_never_calls_stream_chat(self) -> None:
        """Test that streaming disabled calls generate, never stream_chat.

        When config.streaming_enabled=False, the pipeline should
        NOT attempt to call stream_chat, only generate.
        """
        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)

        # Manually disable streaming via config
        pipeline._config.streaming_enabled = False

        result = pipeline.query("Test query")

        assert tracker.generate_called, "generate should have been called"
        assert not tracker.stream_chat_called, "stream_chat should NOT be called when streaming disabled"
        assert "answer" in result

    def test_streaming_disabled_chat(self) -> None:
        """Test that streaming disabled in chat does not call stream_chat."""
        from secondbrain.conversation import ConversationSession

        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)

        pipeline._config.streaming_enabled = False

        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "Hello")

        result = pipeline.chat("Test query", session)

        assert tracker.generate_called, "generate should have been called"
        assert not tracker.stream_chat_called, "stream_chat should NOT be called when disabled"
        assert "answer" in result


class TestStreamChatReturnsEmpty:
    """Tests for stream_chat returning empty/whitespace."""

    def test_stream_chat_returns_empty_falls_back(self) -> None:
        """Test that empty stream_chat output falls back to generate.

        When stream_chat is called but accumulates no content
        (returns empty or whitespace only), the pipeline should
        fall back to generate().
        """
        tracker = StreamTracker(supports_streaming=True, stream_produces_empty=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = pipeline.query("Test query")

        # stream_chat was called but produced no content, so fallback to generate
        assert tracker.stream_chat_called, "stream_chat should have been called"
        assert tracker.generate_called, "generate should have been called as fallback for empty stream"
        assert "answer" in result


class TestAsyncQueryAsyncStreaming:
    """Tests for async query_async streaming wiring."""

    @pytest.mark.asyncio
    async def test_async_query_async_streaming_enabled_calls_stream_chat_async(self) -> None:
        """Test that async query_async with streaming enabled uses stream_chat_async.

        When config.streaming_enabled=True and provider has stream_chat_async,
        the async pipeline should call stream_chat_async.
        """
        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = await pipeline.query_async("Test query")

        assert tracker.stream_chat_async_called, "stream_chat_async should have been called"
        assert not tracker.agenerate_called, "agenerate should NOT have been called"
        assert "answer" in result
        # The streamed content should be accumulated
        assert result["answer"] == "Async streamed"

    @pytest.mark.asyncio
    async def test_async_query_async_streaming_disabled_uses_agenerate(self) -> None:
        """Test that async query_async with streaming disabled uses agenerate.

        When config.streaming_enabled=False, the async pipeline should
        call agenerate instead of stream_chat_async.
        """
        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)

        # Disable streaming
        pipeline._config.streaming_enabled = False

        result = await pipeline.query_async("Test query")

        assert tracker.agenerate_called, "agenerate should have been called"
        assert not tracker.stream_chat_async_called, "stream_chat_async should NOT be called"
        assert result["answer"] == "Async generated answer"

    @pytest.mark.asyncio
    async def test_async_query_async_stream_chat_async_raises_falls_back(self) -> None:
        """Test that stream_chat_async raising falls back to agenerate.

        When stream_chat_async raises an exception, the async pipeline
        should catch it and fall back to agenerate().
        """
        tracker = StreamTracker(supports_streaming=True, stream_raises=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = await pipeline.query_async("Test query")

        assert tracker.stream_chat_async_called, "stream_chat_async should have been attempted"
        assert tracker.agenerate_called, "agenerate should have been called as fallback"
        assert result["answer"] == "Async generated answer"
