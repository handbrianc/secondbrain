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

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
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

    async def agenerate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
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

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
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


def _make_pipeline_for_tracker(
    tracker: StreamTracker | GenerateOnlyTracker,
) -> RAGPipeline:
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
        assert not tracker.stream_chat_called, (
            "stream_chat should NOT be called when streaming disabled"
        )
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
        assert not tracker.stream_chat_called, (
            "stream_chat should NOT be called when disabled"
        )
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
        assert tracker.generate_called, (
            "generate should have been called as fallback for empty stream"
        )
        assert "answer" in result


class TestAsyncQueryAsyncStreaming:
    """Tests for async query_async streaming wiring."""

    @pytest.mark.asyncio
    async def test_async_query_async_streaming_enabled_calls_stream_chat_async(
        self,
    ) -> None:
        """Test that async query_async with streaming enabled uses stream_chat_async.

        When config.streaming_enabled=True and provider has stream_chat_async,
        the async pipeline should call stream_chat_async.
        """
        tracker = StreamTracker(supports_streaming=True)
        pipeline = _make_pipeline_for_tracker(tracker)
        pipeline._config.streaming_enabled = True

        result = await pipeline.query_async("Test query")

        assert tracker.stream_chat_async_called, (
            "stream_chat_async should have been called"
        )
        assert not tracker.agenerate_called, "agenerate should NOT be called"
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
        assert not tracker.stream_chat_async_called, (
            "stream_chat_async should NOT be called"
        )
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

        assert tracker.stream_chat_async_called, (
            "stream_chat_async should have been attempted"
        )
        assert tracker.agenerate_called, "agenerate should have been called as fallback"
        assert result["answer"] == "Async generated answer"


class TestDeriveChapterNumbers:
    """Characterization tests for _derive_chapter_numbers() bugs.

    SEC_RE = re.compile(r"(\\d+)(?:\\.(\\d+))+(?:\\s+(.+))?") requires:
      - \\d+\\.\\d+ (digit.digit) minimum for a match
      - dot count of 1 = top-level section (chapter candidate)
      - dot count of 2+ = subordinate section (must be filtered)

    Fix 1: guard at line 726 —  break  →  continue
            When the guard fires (out-of-range or already-seen major),
            continue skips that match and keeps scanning within the chunk.

    Fix 2: depth-guard added after  major = int(m.group(1)):
            if m.group(0).count(".") > 1: continue
            Entries with 2+ dot-separated components are subordinate
            sections, NOT chapter headers.
    """

    def _make_test_pipeline(self) -> RAGPipeline:
        mock_searcher = MagicMock(spec=Searcher)
        mock_searcher.search.return_value = []
        mock_searcher.search_async = AsyncMock(return_value=[])
        return RAGPipeline(
            searcher=mock_searcher,
            llm_provider=MagicMock(),
            top_k=5,
            context_window=5,
        )

    def test_break_instead_of_continue_allows_later_chunks_when_early_chunk_has_out_of_range(
        self,
    ) -> None:
        """Bug 1: guard 'break' in _derive_chapter_numbers() skips processing remaining chunks.

        The function iterates chunks in order.  Each chunk yields ONE entry
        (the first SEC_RE match that passes the guards).  After collecting
        entries, the outer loop continues to the next chunk.

        BUG: In the guard section, 'break' (instead of 'continue') halts
        the outer-for chunk loop entirely, skipping ALL remaining chunks —
        not just the current chunk.  With 'continue', only the current
        chunk's match is rejected; processing proceeds to the next chunk.

        Setup: 3 chunks, each with one valid 1-dot entry.
        Chunk 2 also has an out-of-range (31+) section — forces a guard hit.
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": "3.1 Introduction to the topic.",
                "source_file": "ch1.pdf",
            },
            {
                "chunk_text": "29.1 Related work section.\n31.2 Out of range subsection.",
                "source_file": "ch2.pdf",
            },
            {
                "chunk_text": "4.1 Overview and motivation.",
                "source_file": "ch3.pdf",
            },
        ]

        majors = sorted(e[0] for e in pipeline._derive_chapter_numbers(structure_chunks))

        # Chunk 1 contribution
        assert 3 in majors, "chapter 3 from chunk 1 must be in result"
        # Chunk 2 contribution: the out-of-range trigger 31 fires the guard.
        # With break: outer-for loop HALTS here — chunk 3 NEVER PROCESSED.
        # With continue: match is skipped, processing ADVANCES to chunk 3.
        assert 29 in majors, (
            "BUG: chapter 29 from chunk 2 is absent — either the 31-triggered "
            "break stopped chunk processing entirely (outer loop broken), or "
            "chunk 2's own valid entry 29.1 was never added."
        )
        # Chunk 3 contribution — only reachable with 'continue'
        assert 4 in majors, (
            "BUG: chapter 4 from chunk 3 is absent — 'break' in the guard "
            "halted the outer chunk loop when the 31 guard fired in chunk 2, "
            "preventing chunk 3 from ever being processed.  'continue' fixes "
            "this by rejecting only the bad match within chunk 2, letting the "
            "outer for loop advance to chunk 3."
        )

    def test_break_instead_of_continue_drops_multiple_valid_entries_after_bad_match(
        self,
    ) -> None:
        """Bug 1 manifesting: ALL valid entries after the bad match are lost."""
        pipeline = self._make_test_pipeline()
        # Each line: "N.1 Title" — matches SEC_RE as N and 1
        structure_chunks = [
            {
                "chunk_text": (
                    "4.1 First topic section.\n"
                    "5.1 Second topic section.\n"
                    "6.1 Third topic section.\n"
                    "29.1 Fourth topic section.\n"
                    "30.1 Fifth topic section.\n"
                    "35.2 Out of range section."
                ),
                "source_file": "chapters.pdf",
            },
        ]

        majors = sorted(e[0] for e in pipeline._derive_chapter_numbers(structure_chunks))

        assert 35 not in majors, "chapter 35 is out of range and must be absent"
        assert 4 in majors, "chapter 4 must be present"
        assert 5 in majors, (
            "BUG: chapter 5 is absent — 'break' on 35 (>30) prevented "
            "processing of all later valid entries (5, 6, 29, 30)"
        )
        assert 6 in majors, "BUG: chapter 6 is absent — same root cause"
        assert 29 in majors, "BUG: chapter 29 is absent — same root cause"
        assert 30 in majors, "BUG: chapter 30 is absent — same root cause"

    def test_subsections_not_treated_as_chapter_headers(self) -> None:
        """Bug 2: first-digit extraction inflates chapter count.

        "3.9.11" has 2 dots — subordinate section, NOT a chapter header.
        Without depth-guard: m.group(1)=3, major=3, added as chapter entry.
        With depth-guard (count(".")>1): skipped correctly.
        Also "3.1" has 1 dot — valid chapter entry, must appear once.
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": (
                    "3.1 Top-level introduction section.\n"
                    "3.9.11 Deeply nested subsection.\n"
                    "4.1 Top-level overview section."
                ),
                "source_file": "paper.pdf",
            },
        ]

        majors = sorted(e[0] for e in pipeline._derive_chapter_numbers(structure_chunks))

        # Chapters with 1 dot must be present
        assert 3 in majors, "chapter 3 (1-dot '3.1') must be present"
        assert 4 in majors, "chapter 4 (1-dot '4.1') must be present"

        # Subordinate sections (2+ dots) must NOT inflate chapter count
        chapter_3_count = sum(1 for m in majors if m == 3)
        assert chapter_3_count == 1, (
            f"BUG: chapter 3 appears {chapter_3_count} times in majors={majors}. "
            "The 2-dot entry '3.9.11' is erroneously added via first-digit "
            "extraction (major=3) when it should be filtered by the "
            "depth-guard (m.group(0).count('.') > 1)."
        )

    def test_deeply_nested_section_produces_known_limitation(self) -> None:
        """Known limitation: SEC_RE can't distinguish 1-dot from 2-dot section numbers.

        SEC_RE = re.compile(r"(\\d+)(?:\\.(\\d+))+(?:\\s+(.+))?") captures only the
        last \\.digit group, so "11.5.3" gives g1=11, g2=3 → section="11.3" with
        dotcount=1.  The depth-guard cannot be correctly implemented with this
        regex alone; a proper tokenizer would be needed.

        This test documents the KNOWN LIMITATION: the current implementation
        DOES include 11.5.3 (major=11) despite the 2-dot section number.
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": "11.5.3 Detailed analysis of edge cases.",
                "source_file": "notes.pdf",
            },
        ]

        majors = [e[0] for e in pipeline._derive_chapter_numbers(structure_chunks)]

        # Currently: "11.5.3" IS added (major=11) despite being a deep subsection.
        # The fix (break->continue) does not address this specific limitation.
        # A proper depth-guard requires a custom section tokenizer (Phase 2).
        assert 11 in majors, (
            "CURRENT BEHAVIOR: 11.5.3 maps to major=11 and is added. "
            "This is the KNOWN LIMICATION of the SEC_RE approach — "
            "regex g1 captures only the FIRST digit group, not the full "
            "section hierarchy.  This test PASSES with the break->continue "
            "fix but documents that multi-dot filtering awaits Phase 2."
        )

    def test_tuple_arity_preserved_after_fix(self) -> None:
        """Downstream at pipeline.py:826 requires exactly 3-element tuples.

        for chap_num, source, clean_title in chapters_to_cover:
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": (
                    "3.1 Introduction section.\n"
                    "3.2 Background details.\n"
                    "4.1 Conclusions section."
                ),
                "source_file": "chapter1.pdf",
            },
            {
                "chunk_text": (
                    "29.1 Related work section.\n"
                    "30.1 Discussion section."
                ),
                "source_file": "chapter2.pdf",
            },
            {
                "chunk_text": "12.1 References section.",
                "source_file": "misc.pdf",
            },
        ]

        result = pipeline._derive_chapter_numbers(structure_chunks)

        for idx, entry in enumerate(result):
            assert len(entry) == 3, (
                f"tuple #{idx} has len {len(entry)} but must be exactly 3 "
                f"(major, source, clean_title); entry={entry}"
            )
            major, source, clean_title = entry
            assert isinstance(major, int), f"major should be int, got {type(major)}"
            assert isinstance(source, str), f"source should be str, got {type(source)}"
            assert isinstance(clean_title, str), (
                f"clean_title should be str, got {type(clean_title)}"
            )

    def test_sec_re_capped_by_chapter_level_max(self) -> None:
        """SEC_RE within 3 of max, first-word filter catches ch19 downstream.

        CHAPTER_N_RE finds ch15 → seen_max=15 → sec_limit=18.
        SEC_RE adds ch16-18 (within limit), rejects ch19 (19 > 18).
        The first-word dup filter in _iterative_query catches ch19
        in case it enters through another path (Phase 2 body scan).
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": (
                    "Chapter 15 VBoxManage\n"
                    "16.1 Reference\n"
                    "17.1 Change Log\n"
                    "18.1 Licensing Information\n"
                    "19.1 VBoxManage Command Reference"
                ),
                "source_file": "vbox.pdf",
            },
        ]

        result = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in result)

        assert 15 in majors, "chapter 15 from CHAPTER_N_RE must be present"
        assert 16 in majors, "chapter 16 (within sec_limit=18) must be present"
        assert 17 in majors, "chapter 17 (within sec_limit=18) must be present"
        assert 18 in majors, "chapter 18 (within sec_limit=18) must be present"
        assert 19 not in majors, (
            f"BUG: chapter 19 is present in {majors} but sec_limit=18 "
            "should have rejected it (19 > 15+3=18)"
        )

    def test_sec_re_cap_still_allows_gap_filler_for_proxmox(self) -> None:
        """SEC_RE cap must NOT block gap-fillers like Proxmox ch20.

        CHAPTER_N_RE finds ch19 and ch21 → seen_max=21 → sec_limit=21.
        SEC_RE should still add ch20 (20 <= 21, fills gap between 19 and 21).
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": (
                    "Chapter 19 Performance\n"
                    "Chapter 21 Bibliography\n"
                    "20.1 High Availability Requirements\n"
                    "20.2 HA Network Configuration"
                ),
                "source_file": "proxmox.pdf",
            },
        ]

        result = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in result)

        assert 19 in majors, "chapter 19 from CHAPTER_N_RE must be present"
        assert 20 in majors, (
            f"BUG: chapter 20 absent from {majors} — sec_limit should be "
            "21+3=24, allowing 20 as a gap-filler"
        )
        assert 21 in majors, "chapter 21 from CHAPTER_N_RE must be present"