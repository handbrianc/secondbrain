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
    r"""Characterization tests for _derive_chapter_numbers() bugs.

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

    def test_clean_chapter_title(self) -> None:
        """TOC chapter titles lose their dot leader and trailing page number."""
        p = self._make_test_pipeline()
        assert (
            p._clean_chapter_title(
                "The ML4T Workflow ....... 223"
            )
            == "The ML4T Workflow"
        )
        assert (
            p._clean_chapter_title("Machine Learning for Trading - From Idea to Execution 1")
            == "Machine Learning for Trading - From Idea to Execution"
        )
        # A long title is no longer truncated, and its page number is dropped.
        long_title = (
            "Time-Series Models for Volatility Forecasts and Statistical "
            "Arbitrage ....... 289"
        )
        assert (
            p._clean_chapter_title(long_title)
            == "Time-Series Models for Volatility Forecasts and Statistical Arbitrage"
        )

    def test_crlf_toc_title_stops_at_page_number(self) -> None:
        """A CRLF-wrapped TOC row yields the full title, stopped at the page number."""
        # Real shape: "Chapter 9: <title> 255" + CRLF, followed by sub-entries.
        self._assert_joined_chapter9_title(
            text=(
                "Table of Contents\r\n"
                "Chapter 9: Time-Series Models for Volatility Forecasts and \r\n"
                "Statistical Arbitrage 255\r\n"
                "Tools for diagnostics and feature extraction 256\r\n"
            )
        )

    def test_wrapped_toc_title_joins_continuation_line(self) -> None:
        """A line-wrapped TOC chapter title is joined, not truncated at the newline.

        Long TOC entries wrap onto a second line (e.g. a dot-leader page column).
        The title regex must cross that single newline and stop at the dot leader,
        so the returned title is the full "...Forecasts and Statistical Arbitrage"
        instead of being cut at "...Forecasts and".
        """
        self._assert_joined_chapter9_title(
            text=(
                "Chapter 9 Time-Series Models for Volatility Forecasts and\n"
                "Statistical Arbitrage ....... 289"
            )
        )

    def _assert_joined_chapter9_title(self, text: str) -> None:
        pipeline_ = self._make_test_pipeline()
        structure_chunks = [{"chunk_text": text, "source_file": "ch9.pdf"}]
        entries, _, _ = pipeline_._derive_chapter_numbers(structure_chunks)
        assert any(
            n == 9
            and t
            == (
                "Time-Series Models for Volatility Forecasts and "
                "Statistical Arbitrage"
            )
            for n, _s, t in entries
        ), f"wrapped title not joined: {entries!r}"

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
                "chunk_text": "Chapter 3 Introduction\n3.1 Subsection",
                "source_file": "ch1.pdf",
            },
            {
                "chunk_text": "Chapter 29 Related Work\n29.1 Section.\n31.2 Out of range.",
                "source_file": "ch2.pdf",
            },
            {
                "chunk_text": "Chapter 4 Overview\n4.1 Motivation.",
                "source_file": "ch3.pdf",
            },
        ]

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in entries)

        # Chunk 1 contribution
        assert 3 in majors, "chapter 3 from chunk 1 must be in result"
        # Chunk 2 contribution: the out-of-range trigger 31 fires the guard.
        # With break: outer-for loop HALTS here — chunk 3 NEVER PROCESSED.
        # With continue: match is skipped, processing ADVANCES to chunk 3.
        assert 29 in majors, (
            "BUG: chapter 29 from chunk 2 is absent — either the 31-triggered "
            "break stopped chunk processing entirely (outer loop broken), or "
            "chunk 2's own valid entry 29 was never added."
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
        # Mix CHAPTER_N_RE (reliable) and SEC_RE (section headers, now skipped)
        structure_chunks = [
            {
                "chunk_text": (
                    "Chapter 4 Results\n"
                    "4.1 First topic section.\n"
                    "5.1 Second topic section.\n"
                    "Chapter 6 Discussion\n"
                    "6.1 Third topic section.\n"
                    "29.1 Fourth topic section.\n"
                    "Chapter 30 Conclusions\n"
                    "30.1 Fifth topic section.\n"
                    "35.2 Out of range section."
                ),
                "source_file": "chapters.pdf",
            },
        ]

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in entries)

        assert 35 not in majors, "chapter 35 is out of range and must be absent"
        assert 4 in majors, "chapter 4 (CHAPTER_N_RE) must be present"
        assert 5 not in majors, (
            "SEC_RE entry 5.1 is a section header, not a chapter title — "
            "must NOT appear in chapter entries"
        )
        assert 6 in majors, "chapter 6 (CHAPTER_N_RE) must be present"
        assert 30 in majors, "chapter 30 (CHAPTER_N_RE) must be present"

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
                    "Chapter 3 Introduction\n"
                    "3.1 Top-level introduction section.\n"
                    "3.9.11 Deeply nested subsection (SEC_RE, skipped).\n"
                    "Chapter 4 Overview\n"
                    "4.1 Top-level overview section."
                ),
                "source_file": "paper.pdf",
            },
        ]

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in entries)

        # Chapters from CHAPTER_N_RE must be present
        assert 3 in majors, "chapter 3 (CHAPTER_N_RE) must be present"
        assert 4 in majors, "chapter 4 (CHAPTER_N_RE) must be present"

        # SEC_RE adds 3 to seen_sec only — no duplicates in return value
        assert majors == [3, 4], (
            f"Only CHAPTER_N_RE entries (3, 4) expected, got {majors}"
        )

    def test_deeply_nested_section_skipped_as_non_chapter(self) -> None:
        r"""SEC_RE section headers (even deeply nested) are NOT chapter titles.

        SEC_RE = re.compile(r"(\\d+)(?:\\.(\\d+))+(?:\\s+(.+))?") captures only the
        last \\.digit group, so "11.5.3" gives g1=11, g2=3 → section="11.3" with
        dotcount=1.  Even so, the entry is NOT added to the return value because
        SEC_RE entries are section headers, not chapter titles.
        """
        pipeline = self._make_test_pipeline()
        structure_chunks = [
            {
                "chunk_text": "11.5.3 Detailed analysis of edge cases.",
                "source_file": "notes.pdf",
            },
        ]

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = [e[0] for e in entries]

        assert 11 not in majors, (
            "SEC_RE entry '11.5.3' is a section header — must NOT appear "
            "as a chapter title in the return value"
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
                "chunk_text": ("29.1 Related work section.\n30.1 Discussion section."),
                "source_file": "chapter2.pdf",
            },
            {
                "chunk_text": "12.1 References section.",
                "source_file": "misc.pdf",
            },
        ]

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        assert all(len(e) == 3 for e in entries), (
            f"Expected 3-element chapter tuples, got: {entries}"
        )

    def test_sec_re_capped_by_chapter_level_max(self) -> None:
        """SEC_RE within 3 of max, first-word filter catches ch19 downstream.

        CHAPTER_N_RE finds ch15 → seen_max=15 → sec_limit=18.
        SEC_RE adds ch16-18 to seen_sec (prevents phantom chapters), but does
        NOT add them to the return value (they're section headers, not chapter
        titles).  The first-word dup filter in _iterative_query catches ch19
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

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in entries)

        assert 15 in majors, "chapter 15 from CHAPTER_N_RE must be present"
        assert 16 not in majors, (
            "chapter 16 is SEC_RE (section header, not chapter title)"
        )
        assert 17 not in majors, (
            "chapter 17 is SEC_RE (section header, not chapter title)"
        )
        assert 18 not in majors, (
            "chapter 18 is SEC_RE (section header, not chapter title)"
        )
        assert 19 not in majors, "chapter 19 is out of range (19 > 15+3=18)"
        assert majors == [15], f"expected only ch15 (CHAPTER_N_RE), got {majors}"

    def test_sec_re_cap_still_allows_gap_filler_for_proxmox(self) -> None:
        """SEC_RE cap allows gap-filler without polluting chapter title pool.

        CHAPTER_N_RE finds ch19 and ch21 → seen_max=21 → sec_limit=21.
        SEC_RE adds ch20 to seen_sec but NOT to the return value (it's a
        section header, not a chapter title).  The gap-filler concept is
        handled by the seen_sec tracking for sec_limit, not by entries.
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

        entries, _, _ = pipeline._derive_chapter_numbers(structure_chunks)
        majors = sorted(e[0] for e in entries)

        assert 19 in majors, "chapter 19 from CHAPTER_N_RE must be present"
        assert 20 not in majors, (
            "chapter 20 is SEC_RE (section header, not chapter title) — "
            "must NOT appear in return value"
        )
        assert 21 in majors, "chapter 21 from CHAPTER_N_RE must be present"
        assert majors == [19, 21], (
            f"expected only ch19, ch21 (CHAPTER_N_RE), got {majors}"
        )


    def test_module_with_colon_detected(self) -> None:
        """'Module N: Title' is a real structural heading, like 'Chapter N'."""
        pipeline = self._make_test_pipeline()
        text = "Module 7: Completion & Best Practices Transition: \"Final module\""
        entries, good, _ = pipeline._derive_chapter_numbers(
            [{"chunk_text": text, "source_file": "deck.pptx"}]
        )
        assert sorted(e[0] for e in entries) == [7], f"got {entries}"
        assert good == {7}

    def test_module_reference_without_colon_not_a_heading(self) -> None:
        """A bare 'Module 7 Circulate' reference (no colon) is not a heading."""
        pipeline = self._make_test_pipeline()
        text = "\n".join(
            [
                "Module 1: Meet Your AI Assistant Transition: \"Let's start\"",
                "Module 2: The 3-Part Prompt Formula Transition: \"Now the single\"",
                "Module 7 Circulate and check that students verify (step 3) —",
                "Module 3: Working with Everyday Files Transition: \"Now let's\"",
            ]
        )
        entries, _, _ = pipeline._derive_chapter_numbers(
            [{"chunk_text": text, "source_file": "deck.pptx"}]
        )
        nums = sorted(e[0] for e in entries)
        assert nums == [1, 2, 3], f"got {nums}"
        assert 7 not in nums, "bare 'Module 7 Circulate' reference must not add chapter 7"


class TestCodeContentGate:
    """Code-like content must not be treated as a prose chapter structure.

    A bundled/minified HTML/JS file has no chapters; without this gate the
    structural regexes hallucinate chapters from version numbers and
    identifiers (e.g. "8.5", "7.0.0", "25.8").  The code gate must suppress
    both chapter-number derivation and the roster header, while leaving prose
    documents untouched.
    """

    _MINIFIED_BUNDLE = (
        '!function(e,t){"use strict";var r={352:function(e){'
        'e.exports={version:"7.0.0-rc.2"}},762:function(e){'
        'e.exports={core:["es.typed-array.find-last","es7.array.includes"]}}};'
        'var s="8.5",u="9.5",v="25.8";var p={d:"M10 4l3.5 3.5M4 13v2"};'
        'e.version="8.0.0-alpha.0"}(this);'
    )

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

    def _code_chunks(self) -> list[dict[str, Any]]:
        return [{"chunk_text": self._MINIFIED_BUNDLE, "source_file": "index.html"}]

    def test_minified_bundle_flagged_as_code(self) -> None:
        pipeline = self._make_test_pipeline()
        assert pipeline._chunks_are_code_like(self._code_chunks()) is True

    def test_code_bundle_yields_no_chapters_or_roster(self) -> None:
        pipeline = self._make_test_pipeline()
        entries, good, appendix = pipeline._derive_chapter_numbers(self._code_chunks())
        assert entries == []
        assert good == set()
        assert appendix == []
        assert pipeline._derive_chapter_roster(self._code_chunks()) == ""

    def test_prose_not_code_like_and_keeps_roster(self) -> None:
        prose_chunks = [
            {
                "chunk_text": (
                    "Chapter 4 Results\n4.1 First topic section.\n"
                    "Chapter 6 Discussion\n6.1 Third topic section.\n"
                ),
                "source_file": "chapters.pdf",
            }
        ]
        pipeline = self._make_test_pipeline()
        assert pipeline._chunks_are_code_like(prose_chunks) is False
        roster = pipeline._derive_chapter_roster(prose_chunks)
        assert "DOCUMENT STRUCTURE INDEX" in roster


class TestDeriveChapterRosterUnion:
    """Regression: a detected chapter must never vanish from the roster.

    The chapter index was previously built only from recognised subsections, so a
    chapter whose heading was detected (present in ``ch_good``) but whose section
    headers were not seen in the probe chunks was dropped while its neighbours
    survived — e.g. chapters 13 and 17 disappearing from a cookbook index.  It
    must appear regardless, and truncation must never remove a chapter heading.
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

    def test_chapter_without_detected_section_still_in_roster(self) -> None:
        # Chapter 13 has a detected heading but no "13.x" section header in the
        # probe chunks; chapters 12 and 14 have both.  Only 13 may not vanish.
        pipeline = self._make_test_pipeline()
        chunks = [
            {
                "chunk_text": (
                    "Chapter 12 Selection and Assignment\n"
                    "12.1 Basic selection.\n"
                    "Chapter 13 Advanced Selection\n"
                    "Chapter 14 Selection and Assignment\n"
                    "14.1 Label-based selection.\n"
                ),
                "source_file": "cookbook.pdf",
            }
        ]
        roster = pipeline._derive_chapter_roster(chunks)
        assert "[Chapter 12]" in roster
        assert "[Chapter 13]" in roster, f"chapter 13 dropped:\n{roster}"
        assert "[Chapter 14]" in roster

    def test_truncation_never_drops_chapter_headings(self) -> None:
        # Chapters 11-25 have headings but no subsections; chapters 1-10 have
        # enough subsections that a flat 50-line cap would cut the tail.  Every
        # chapter heading (including 25) must survive.
        pipeline = self._make_test_pipeline()
        parts: list[str] = []
        for n in range(1, 11):
            parts.append(f"Chapter {n} Topic {n}")
            parts.append(f"{n}.1 first subsection of {n}.")
            parts.append(f"{n}.2 second subsection of {n}.")
        for n in range(11, 26):
            parts.append(f"Chapter {n} Topic {n}")
        chunks = [{"chunk_text": "\n".join(parts), "source_file": "book.pdf"}]
        roster = pipeline._derive_chapter_roster(chunks)
        assert "[Chapter 25]" in roster, f"tail chapter dropped:\n{roster}"
        assert "[Chapter 11]" in roster


class TestAuthoritativeChapterSpan:
    """Regression: bare-number noise must not fabricate chapters.

    When a document labels its chapters explicitly ("Chapter N"),
    those headings define the authoritative chapter span.  Looser
    heuristics (bare_chapter_re / ft_catch / section_re) must not invent
    chapters beyond that span from body text or dataframe output —
    e.g. a book with 11 real chapters must never gain fabricated
    "Chapter 12…30" entries (and thus appear to "miss" 13 and 17).
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

    def test_no_fabricated_chapters_beyond_authoritative_span(self) -> None:
        pipeline = self._make_test_pipeline()
        chunks = [
            {
                "chunk_text": (
                    "Chapter 1 Foundations\n1.1 Intro.\n"
                    "Chapter 2 Selection\n2.1 Basics.\n"
                    "Chapter 3 Data Types\n"
                    "12 Selection and Assignment\n"
                    "14.167143 0.0 0.0\n"
                    "17.952 we see in the first bin\n"
                    "25 Jack 24\n"
                ),
                "source_file": "cookbook.pdf",
            }
        ]
        entries, good, _ = pipeline._derive_chapter_numbers(chunks)
        majors = sorted(e[0] for e in entries)
        assert majors == [1, 2, 3], f"fabricated chapters detected: {majors}"
        assert good == {1, 2, 3}
        roster = pipeline._derive_chapter_roster(chunks)
        assert "[Chapter 1]" in roster and "[Chapter 3]" in roster
        for ghost in (12, 14, 17, 25):
            assert f"[Chapter {ghost}]" not in roster, (
                f"fabricated chapter {ghost} in roster:\n{roster}"
            )

    def test_bare_numbered_document_still_enumerates_via_sections(self) -> None:
        # No explicit "Chapter N" headings anywhere: ch_good is empty, so the
        # roster falls back to section-derived enumeration (must not disappear).
        pipeline = self._make_test_pipeline()
        chunks = [
            {
                "chunk_text": "1.1 Introduction.\n2.1 Setup.\n3.1 Configuration.",
                "source_file": "manual.pdf",
            }
        ]
        roster = pipeline._derive_chapter_roster(chunks)
        assert "[Chapter 1]" in roster, roster
        assert "[Chapter 2]" in roster, roster
        assert "[Chapter 3]" in roster, roster


class TestFilterChaptersByTarget:
    """Tests for filter_chapters_by_target() — a pure function, no mocking needed.

    Tests the production code from rag/pipeline.py directly instead of a mirror
    implementation.  If the production signature or semantics change, these tests
    catch the breakage.
    """

    def test_target_11_keeps_only_chapter_11(self) -> None:
        chapters = [
            (10, "book.pdf", "Networking"),
            (11, "book.pdf", "Advanced Topics"),
            (12, "book.pdf", "Performance Tuning"),
        ]
        good_titles = {10, 11, 12}

        from secondbrain.rag.pipeline import filter_chapters_by_target

        filtered, filtered_titles = filter_chapters_by_target(
            chapters, good_titles, "11"
        )

        assert len(filtered) == 1, f"Expected 1, got {len(filtered)}: {filtered}"
        assert filtered[0][0] == 11, f"Expected ch11, got ch{filtered[0][0]}"
        assert filtered_titles == {11}, f"Expected {{11}}, got {filtered_titles}"

    def test_target_none_keeps_all_chapters(self) -> None:
        chapters = [
            (1, "book.pdf", "Introduction"),
            (2, "book.pdf", "Setup"),
            (11, "book.pdf", "Advanced Topics"),
        ]
        good_titles = {1, 2, 11}

        from secondbrain.rag.pipeline import filter_chapters_by_target

        filtered, filtered_titles = filter_chapters_by_target(
            chapters, good_titles, None
        )

        assert filtered == chapters, "target=None must not change chapters"
        assert filtered_titles == good_titles, "target=None must not change titles"

    def test_target_not_found_produces_empty(self) -> None:
        chapters = [(10, "book.pdf", "Networking"), (11, "book.pdf", "Advanced Topics")]
        good_titles = {10, 11}

        from secondbrain.rag.pipeline import filter_chapters_by_target

        filtered, filtered_titles = filter_chapters_by_target(
            chapters, good_titles, "99"
        )

        assert len(filtered) == 0, f"Expected empty, got {filtered}"
        assert len(filtered_titles) == 0, f"Expected empty, got {filtered_titles}"

    def test_invalid_target_falls_back(self) -> None:
        chapters = [(1, "book.pdf", "Introduction"), (2, "book.pdf", "Setup")]
        good_titles = {1, 2}

        from secondbrain.rag.pipeline import filter_chapters_by_target

        filtered, filtered_titles = filter_chapters_by_target(
            chapters, good_titles, "abc"
        )

        assert filtered == chapters, (
            "Invalid target with matching chapter must fall back"
        )
        assert filtered_titles == good_titles, "Invalid target must fall back"

    def test_empty_chapters_list_with_target(self) -> None:
        from secondbrain.rag.pipeline import filter_chapters_by_target

        filtered, filtered_titles = filter_chapters_by_target([], set(), "11")
        assert filtered == []
        assert filtered_titles == set()


class TestIterativeQueryNoChaptersFallThrough:
    """Broad-coverage query with no detected chapters and no chapter target.

    must fall through to generic search rather than error on a chapter.
    """

    def test_broad_coverage_no_target_empty_chapters_falls_through(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from secondbrain.rag.intent_parser import IntentDecision, QueryIntent

        pipeline = _make_pipeline_for_tracker(GenerateOnlyTracker())
        pipeline._config.streaming_enabled = False

        monkeypatch.setattr(
            pipeline,
            "_probe_document_structure",
            lambda top_k, source_filter=None: [
                {
                    "chunk_text": "Introduction",
                    "chunk_role": "heading",
                    "source_file": "a.pdf",
                    "page": 1,
                }
            ],
        )
        monkeypatch.setattr(
            pipeline, "_derive_chapter_numbers", lambda structure: ([], set(), [])
        )
        monkeypatch.setattr(
            pipeline._intent_parser,
            "parse",
            lambda q: IntentDecision(
                intent=QueryIntent.BROAD_COVERAGE,
                confidence=0.5,
                target=None,
                reason="test",
                suggested_pipeline="structural",
            ),
        )

        result = pipeline._iterative_query(
            "summarize the state of AI 2026 by chapter",
            top_k=5,
            show_sources=False,
        )

        assert "I couldn't find" not in result["answer"]
        assert result["answer"] == "Generated (no streaming available)"


class _SequenceProvider:
    """Provider returning scripted generate() responses in order.

    For deterministic behaviour under parallel map-reduce threads, ``by_key`` maps
    a heading/section key (matched against the prompt) to the response for that
    window, so results do not depend on thread scheduling order.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        by_key: dict[str, str] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.by_key = by_key or {}
        self.calls: list[dict[str, Any]] = []

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.calls.append({"prompt": prompt, "temperature": temperature})
        # Deterministic per-window response (thread-safe, order-independent).
        for key, response in self.by_key.items():
            if key in prompt:
                return response
        if self.responses:
            return self.responses.pop(0)
        return f"answer {len(self.calls)}"


class TestMultiChapterMapReduce:
    """Tests for the per-chapter map-reduce guard on broad-coverage queries."""

    # Distinct, rare, content-only words (none are function words) used to build a
    # high-diversity "word-salad" that the repetition-based guard alone would let
    # through.
    _SALAD_WORDS = (
        "zebra", "giraffe", "trampoline", "sapphire", "bakelite", "vertebra",
        "compass", "harbor", "syringe", "enamel", "abacus", "scaffold", "pilgrim",
        "turbine", "torrent", "sampler", "beetle", "carnival", "monograph",
        "espresso", "necklace", "paradigm", "kettle", "octopus", "verdict",
        "meadow", "glacier", "bundle", "flask", "compartment", "lantern",
        "gyroscope", "basketball", "garrison", "numeral", "meridian", "splinter",
        "reassembly", "soil", "oracle", "basin", "quiver", "anvil", "badger",
        "cilantro", "donkey", "eclipse", "falcon", "granite", "hedgehog", "iguana",
        "jasmine", "kayak", "lagoon", "magnolia", "narwhal", "obsidian", "panther",
        "quagga", "rhinoceros", "satchel", "tapestry", "umbrella", "vulture",
        "walnut", "xylophone", "yak", "zinnia", "amaranth", "bramble", "cinder",
        "deluge", "esker", "fjord", "goblet", "hummock", "isthmus", "juniper",
        "katydid", "lichen", "monsoon", "nectar", "opossum", "paddock", "quarry",
        "runnel", "silt", "tundra", "urchin", "verdant", "wattle", "yonder",
        "zephyr",
    )

    def _make_pipeline(self, provider: _SequenceProvider) -> RAGPipeline:
        return RAGPipeline(
            searcher=_make_mock_searcher(),
            llm_provider=provider,  # type: ignore
            top_k=5,
            context_window=5,
        )

    def _chunk(self, text: str) -> dict[str, Any]:
        return {"chunk_text": text, "source_file": "a.pdf", "page": 1}

    def test_is_plausible_summary_rejects_repetitive(self) -> None:
        p = self._make_pipeline(_SequenceProvider([]))
        assert p._is_plausible_summary(
            "This is a well structured and varied answer about the topic."
        )
        assert not p._is_plausible_summary("la la la la la la la la")
        assert not p._is_plausible_summary("short")

    def test_generate_guarded_retries_on_implausible(self) -> None:
        provider = _SequenceProvider([
            "garbage garbage garbage garbage garbage garbage",
            "A coherent final answer about convolutional networks.",
        ])
        p = self._make_pipeline(provider)
        result = p._generate_guarded("prompt")
        assert result == "A coherent final answer about convolutional networks."
        assert len(provider.calls) == 2
        assert provider.calls[1]["temperature"] == 0.1

    def test_generate_guarded_returns_empty_when_both_bad(self) -> None:
        provider = _SequenceProvider([
            "garg garbage garbage garbage garbage garbage garbage",
            "more garbage more garbage more garbage more garbage",
        ])
        p = self._make_pipeline(provider)
        assert p._generate_guarded("prompt") == ""
        assert len(provider.calls) == 2

    def test_generate_guarded_single_call_when_plausible(self) -> None:
        provider = _SequenceProvider(["A good plausible answer that is long enough."])
        p = self._make_pipeline(provider)
        result = p._generate_guarded("prompt")
        assert result == "A good plausible answer that is long enough."
        assert len(provider.calls) == 1

    def test_multi_chapter_summary_generates_per_chapter(self) -> None:
        provider = _SequenceProvider([
            "Chapter one introduces the core concepts with clear examples.",
            "Chapter two covers the methods and their practical application.",
        ])
        p = self._make_pipeline(provider)
        buckets = {
            1: [self._chunk("chapter one body text here")],
            2: [self._chunk("chapter two body text here")],
        }
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "Intro", 2: "Methods"}
        )
        assert "Chapter 1 — Intro" in result
        assert "Chapter 2 — Methods" in result
        assert "Chapter one introduces the core concepts" in result
        assert len(provider.calls) == 2

    def test_multi_chapter_summary_skips_bad_per_chapter(self) -> None:
        # Keyed responses make the parallel threads deterministic: chapter 1 sees
        # garbage (both its first try and the retry are dropped), chapter 2 gets
        # a clean summary.
        provider = _SequenceProvider(
            by_key={
                "Chapter 1": "garbage garbage garbage garbage garbage garbage",
                "Chapter 2": "A clean summary of chapter two with enough detail to pass.",
            }
        )
        p = self._make_pipeline(provider)
        buckets = {
            1: [self._chunk("chapter one body")],
            2: [self._chunk("chapter two body")],
        }
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "One", 2: "Two"}
        )
        # Chapter 1's output is garbage and is dropped (incl. its retry).
        assert "Chapter 1" not in result
        assert "Chapter 2 — Two" in result
        assert "A clean summary of chapter two" in result
        assert len(provider.calls) == 3

    def test_multi_chapter_summary_empty_bucket_skipped(self) -> None:
        provider = _SequenceProvider(by_key={"Chapter 2": "Summary for chapter two with enough detail here."})
        p = self._make_pipeline(provider)
        buckets = {1: [], 2: [self._chunk("chapter two body")]}
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "One", 2: "Two"}
        )
        assert "Chapter 1" not in result
        assert "Chapter 2 — Two" in result
        assert len(provider.calls) == 1

    def test_single_chapter_groups_by_section(self) -> None:
        provider = _SequenceProvider(
            by_key={
                "Section 18.1": "A detailed summary of section one with enough length to pass.",
                "Section 18.2": "A detailed summary of section two with enough length to pass.",
            }
        )
        p = self._make_pipeline(provider)
        chunks = [
            self._chunk("18.1 First section content here for chapter eighteen."),
            self._chunk("18.1 More first section content."),
            self._chunk("18.2 Second section content here for chapter eighteen."),
            self._chunk("18.2 More second section content."),
        ]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs for Trading")
        assert "Section 18.1" in result
        assert "Section 18.2" in result
        assert "A detailed summary of section one" in result
        # Two section groups → two guarded LLM calls.
        assert len(provider.calls) == 2

    def test_single_chapter_drops_garbage_section(self) -> None:
        provider = _SequenceProvider(
            by_key={
                "Section 18.1": "garbage garbage garbage garbage garbage garbage",
                "Section 18.2": "A clean detailed summary of section two with enough length.",
            }
        )
        p = self._make_pipeline(provider)
        chunks = [
            self._chunk("18.1 First section content for chapter eighteen."),
            self._chunk("18.2 Second section content for chapter eighteen."),
        ]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # Section 18.1's garbage (and its retry) are dropped.
        assert "Section 18.1" not in result
        assert "Section 18.2" in result
        assert "A clean detailed summary of section two" in result

    def test_multi_chapter_streams_each_window(self) -> None:
        streamed: list[str] = []

        class _StreamingKeyedProvider(_SequenceProvider):
            def stream_chat(
                self,
                messages,
                on_chunk,
                temperature=0.7,
                max_tokens=4096,
            ) -> str:
                prompt = messages[0]["content"]
                for key, response in self.by_key.items():
                    if key in prompt:
                        # Emit the response word-by-word to simulate streaming.
                        for word in response.split():
                            on_chunk(word + " ", None)
                        return response
                return ""

        provider = _StreamingKeyedProvider(
            by_key={
                "Chapter 1": "Chapter one streams a clean summary sentence here.",
                "Chapter 2": "Chapter two streams its own summary sentence too.",
            }
        )
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: streamed.append(content or "")

        buckets = {
            1: [self._chunk("chapter one body text")],
            2: [self._chunk("chapter two body text")],
        }
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "Intro", 2: "Methods"}
        )
        # Both headings were streamed to the callback.
        assert "Chapter 1 — Intro" in "".join(streamed)
        assert "Chapter 2 — Methods" in "".join(streamed)
        assert "Chapter one streams a clean summary" in "".join(streamed)
        # Concatenated result still contains both chapters.
        assert "Chapter 2 — Methods" in result

    def test_streaming_window_degenerate_dropped_via_retry(self) -> None:
        """A streamed window whose answer degenerates is retried / dropped."""
        streamed: list[str] = []

        class _StreamingProbProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                return self.by_key.get("garbage", "")

            def generate(
                self, prompt, temperature=0.7, max_tokens=4096
            ) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                # Retry at low temperature returns a clean answer.
                if temperature == 0.1:
                    return "A clean retried summary that is long enough here."
                return "garbage garbage garbage garbage garbage garbage"

        provider = _StreamingProbProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: streamed.append(content or "")
        chunks = [self._chunk("18.1 First section content here.")]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # The streamed garbage is not surfaced; the clean retry is.
        assert "A clean retried summary that is long enough here." in "".join(streamed)
        assert "garbage" not in "".join(streamed)
        assert "A clean retried summary" in result

    def test_streaming_forwards_reasoning_and_content_live(self) -> None:
        """Both reasoning and content reach _on_chunk live as the window streams."""
        reasoning_seen: list[str] = []
        word_seen: list[str] = []

        class _ThinkProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                on_chunk("", "thinking about chapter content...")
                response = "A final plausible summary with enough length to pass."
                for word in response.split():
                    on_chunk(word + " ", None)
                return response

        provider = _ThinkProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True

        streamed: list[str] = []

        def on_chunk(content: str, reasoning: str | None) -> None:
            if reasoning:
                reasoning_seen.append(reasoning)
            if content:
                word_seen.append(content)
            streamed.append(content or "")

        p._on_chunk = on_chunk
        chunks = [self._chunk("18.1 Some section content here.")]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "thinking about chapter content" in "".join(reasoning_seen)
        # Content streams live word-by-word (not dumped as one buffered block).
        assert len(word_seen) > 1
        assert "A final plausible summary" in "".join(streamed)
        assert "Section 18.1" in "".join(streamed)
        assert "A final plausible summary with enough length to pass." in result

    def test_streaming_suppresses_degenerate_flood_mid_stream(self) -> None:
        """Once a streamed window degenerates, the tail is not forwarded."""
        emitted: list[str] = []

        class _FloodProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                for _ in range(300):
                    on_chunk("garbage ", None)
                return "garbage " * 300

        provider = _FloodProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: emitted.append(content or "")
        result = p._generate_window_guarded(
            "prompt", "Chapter 1", temperature=0.3, max_tokens=6000
        )
        # The degenerate tail is suppressed; the window's returned answer is empty.
        assert result == ""
        visible = "".join(emitted)
        assert "Chapter 1" in visible
        assert len(visible) < 900  # far below the 300*8 chars it would otherwise flood

    def test_streaming_suppresses_high_diversity_word_salad(self) -> None:
        """High-diversity word-salad is aborted mid-stream, not streamed unbounded."""
        emitted: list[str] = []
        salad = " ".join(self._SALAD_WORDS) * 8

        class _SaladProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                for word in salad.split()[:200]:
                    on_chunk(word + " ", None)
                return salad

        provider = _SaladProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: emitted.append(content or "")
        result = p._generate_window_guarded("prompt", "Chapter 1")
        # Salad passes the repetition check but is caught by the low-function-word
        # signal, so the returned answer is empty and the tail stops streaming.
        assert len(result) < 200
        assert len("".join(emitted)) < len(salad)

    def test_mid_stream_degradation_retries_for_complete_summary(self) -> None:
        """A chapter that degrades mid-stream is retried, not returned truncated."""
        emitted: list[str] = []
        salad_words = self._SALAD_WORDS

        class _MidDegradeProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                clean_prefix = (
                    "Chapter 18 introduces CNNs for financial time series and "
                    "satellite images, covering convolution and pooling stages."
                )
                for word in clean_prefix.split():
                    on_chunk(word + " ", None)
                # Then the model degenerates into high-diversity word-salad.
                for word in " ".join(salad_words).split()[:120]:
                    on_chunk(word + " ", None)
                return clean_prefix + " " + " ".join(salad_words)

            def generate(
                self, prompt, temperature=0.7, max_tokens=4096
            ) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                # Low-temperature retry returns the complete, stable chapter.
                if temperature == 0.1:
                    return (
                        "Chapter 18 complete summary covering convolutions, pooling, "
                        "transfer learning, satellite imaging, and a CNN trading "
                        "strategy in full, without any degeneration or truncation."
                    )
                return "garbage " * 40

        provider = _MidDegradeProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: emitted.append(content or "")
        result = p._generate_window_guarded("prompt", "Chapter 18 (overview)")
        # The truncated clean prefix is replaced by the low-temperature full retry.
        assert "complete summary covering" in result
        assert "satellite imaging" in result
        # The returned summary is the clean retry: no salad survives into it.
        assert not any(w in result for w in salad_words[:10])
        # The live stream is bounded (a short derailed burst only, never a runaway),
        # then the complete retry is emitted in its place.
        assert len("".join(emitted)) < 1500

    def test_is_acceptable_rejects_word_salad_that_repetition_misses(self) -> None:
        """High-diversity word-salad is rejected even though nothing repeats."""
        p = self._make_pipeline(_SequenceProvider([]))
        salad = " ".join(self._SALAD_WORDS)
        # Proves the old repetition-only check would have let it through.
        assert p._is_plausible_summary(salad) is True
        assert p._looks_derailed(salad) is True
        assert p._is_acceptable(salad) is False

    def test_looks_derailed_catches_novel_salad_with_function_words(self) -> None:
        """Salad that sneaks in function words is caught by the novel-word signal."""
        p = self._make_pipeline(_SequenceProvider([]))
        fns = ["and", "the", "of", "to", "with", "for", "on", "is", "a", "in"]
        tokens: list[str] = []
        for i in range(160):
            tokens.append(f"term{i}x")
            if i % 8 == 0:
                tokens.append(fns[(i // 8) % len(fns)])
        text = " ".join(tokens)
        # Function-word share stays above the ratio threshold (so that signal alone
        # would pass it), but the near-unanimous novelty trips the type-token one.
        assert p._looks_derailed(text) is True
        assert p._is_acceptable(text) is False

    def test_dense_technical_summary_not_truncated_by_flood_guard(self) -> None:
        """A legitimate dense summary streams to completion, not truncated.

        Regression: the streaming flood guard used to also consult the
        word-salad diversity heuristic on the partial buffer, which
        false-positives on dense technical text (lists of PCA/ICA/model names
        spike the type-token ratio) and truncated good summaries mid-sentence.
        Now the mid-stream guard only aborts on repetition, so a dense summary
        is returned in full.
        """
        dense = (
            "Chapter 13 focuses on unsupervised learning for trading applications: "
            "dimensionality reduction and clustering. These techniques learn "
            "informative representations of data without an outcome variable, "
            "unlike the supervised learning covered in prior chapters. The "
            "chapter details how linear methods like principal component analysis "
            "(PCA) and independent component analysis (ICA) reduce feature spaces, "
            "and how k-means and hierarchical clustering group similar assets. "
            "The chapter covers evaluating these models on financial data."
        )
        streamed: list[str] = []
        retried: list[bool] = []

        class _DenseProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                for word in dense.split():
                    on_chunk(word + " ", None)
                return dense

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                retried.append(True)
                return dense

        provider = _DenseProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: streamed.append(content or "")
        result = p._generate_window_guarded("prompt", "Section 18.1")
        # The full dense summary is returned — not a truncated clean prefix.
        assert not retried
        assert "dimensionality reduction and clustering" in result
        assert "hierarchical clustering group similar assets" in result
        # The whole body streamed to its end across the live `_on_chunk` feed.
        assert "on financial data." in "".join(streamed)

    def test_trim_rehashed_tail_drops_restated_duplicate(self) -> None:
        """A re-worded restatement of the same section content is dropped."""
        p = self._make_pipeline(_SequenceProvider([]))
        head = (
            "Section 18.12 builds a one-dimensional CNN to forecast returns. "
            "It stacks a Conv1D layer with 32 filters, kernel size 4, ReLU and "
            "causal padding, followed by max pooling and batch normalization. "
            "The architecture yields 449 trainable parameters. It uses momentum "
            "and trend indicators WMA, EMA, ROC, CMO, ADOSC and ADX. It computes "
            "rolling Fama-French five-factor betas via statsmodels RollingOLS."
        )
        tail = (
            "The model stacks a Conv1D layer with 32 filters, kernel size 4, "
            "ReLU and causal padding, then batch normalization and a dense "
            "output of 449 trainable parameters. It relies on momentum and "
            "trend indicators WMA, EMA, ROC, CMO, ADOSC and ADX. It also "
            "computes rolling Fama-French betas from RollingOLS on French data."
        )
        trimmed = p._trim_rehashed_tail(head + " " + tail)
        assert trimmed == head
        assert "The model stacks" not in trimmed

    def test_trim_rehashed_tail_keeps_progressive_summary(self) -> None:
        """A summary whose later sentences add new content is left intact."""
        p = self._make_pipeline(_SequenceProvider([]))
        prog = (
            "Chapter 13 introduces unsupervised learning for trading, covering "
            "dimensionality reduction and clustering. The main tasks are PCA and "
            "ICA for linear reduction and t-SNE for manifold learning. It covers "
            "k-means, hierarchical, and density-based clustering. These identify "
            "data-driven risk factors and eigenportfolios from asset returns. "
            "They also build robust portfolios via hierarchical risk parity."
        )
        assert p._trim_rehashed_tail(prog) == prog

    def test_trim_rehashed_tail_catches_reworded_restatement(self) -> None:
        """A fully re-worded second pass over the same entities is still dropped."""
        p = self._make_pipeline(_SequenceProvider([]))
        head = (
            "Chapter 18 profiles LeNet5 on MNIST at 99.2 percent and AlexNet, "
            "the 2012 ILSVRC winner. Transfer learning reuses ImageNet models "
            "like VGG16. Applications classify EuroSat satellite images and "
            "predict daily returns."
        )
        tail = (
            "Here is an overview synthesized from the document. It reviews "
            "LeNet5 (99.2 percent on MNIST) and AlexNet of ILSVRC 2012. "
            "Transfer learning uses pretrained ImageNet backbones such as VGG16 "
            "for features. CNNs are applied to EuroSat satellite classification "
            "and daily return forecasting."
        )
        result = p._trim_rehashed_tail(head + " " + tail)
        assert "Here is an overview" not in result
        assert "profiles LeNet5" in result

    def test_summary_path_uses_summary_temperature_and_max_tokens(self) -> None:
        """Summary windows use llm_summary_temperature, independent of llm_temperature."""
        captured: list[dict[str, Any]] = []

        class _CaptureProvider(_SequenceProvider):
            def generate(
                self, prompt, temperature=0.7, max_tokens=4096
            ) -> str:
                captured.append({"temperature": temperature, "max_tokens": max_tokens})
                return "A plausible summary sentence that is long enough here."

        provider = _CaptureProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = False  # force the guarded sync path
        p._config.llm_temperature = 1.0
        p._config.llm_summary_temperature = 0.7
        p._config.llm_max_tokens = 384000
        chunks = [self._chunk("18.1 Section content here.")]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "A plausible summary sentence" in result
        # The summary window runs at the summary-specific temperature, not the
        # global chat temperature (stability for long comprehensive summaries).
        # The first generate call is the summary window (0.7); a later call is the
        # figure-refinement pass.
        assert captured[0].get("temperature") == 0.7
        assert captured[0].get("max_tokens") == 384000

    def test_figure_refinement_corrects_confabulated_numbers(self) -> None:
        """The post-pass re-grounds misstated figures against the source."""
        draft = (
            "AlexNet won the 2021 ILSVRC with a top-5 error of 42 percent versus 53, "
            "using around 71 million parameters. This overview has enough distinct "
            "words to appear plausible and pass validation checks for length."
        )
        corrected = (
            "AlexNet won the 2012 ILSVRC with a top-5 error of 16 percent versus 26, "
            "using around 60 million parameters. This corrected overview reflects the "
            "exact source figures and remains a coherent, plausible summary."
        )

        class _RefineProvider(_SequenceProvider):
            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"temperature": temperature})
                if temperature == 0.2:  # the figure-refinement pass
                    return corrected
                return draft

        provider = _RefineProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = False
        chunks = [self._chunk("CNN chapter content covering AlexNet architecture.")]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "2012" in result and "16 percent" in result
        assert "2021" not in result and "42 percent" not in result
        # The refinement ran at low temperature.
        assert any(c["temperature"] == 0.2 for c in provider.calls)

    def test_implausible_metric_values_pruned(self) -> None:
        """Provably impossible metric values are stripped from the final summary."""
        draft = (
            "The multivariate experiment reported an average weekly IC of 3.32 and "
            "6.68, while the S&P forecast showed an information coefficient of "
            "0.9889. This overview is plausible and has enough distinct words to "
            "pass validation here."
        )

        class _BadMetricProvider(_SequenceProvider):
            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"temperature": temperature})
                return draft

        provider = _BadMetricProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = False
        chunks = [self._chunk("RNN chapter on multivariate weekly return forecasting.")]
        result = p._generate_single_chapter_summary(chunks, 19, "RNNs")
        # Impossible IC values (> 1) are dropped; the metric name is retained.
        assert "3.32" not in result and "6.68" not in result
        assert "IC" in result or "coefficient" in result
        # An in-range value (<= 1) is not provably wrong, so it is kept.
        assert "0.9889" in result

    def test_single_chapter_sections_ordered_numerically(self) -> None:
        """Sections are emitted in numeric order even when chunks arrive scrambled."""
        by_key = {
            f"Section 18.{n}": f"Full summary for section {n} with enough detail to pass."
            for n in (2, 10, 5, 3)
        }
        provider = _SequenceProvider(by_key=by_key)
        p = self._make_pipeline(provider)
        # Chunks arrive out of order: 18.10, 18.2, 18.5, 18.3.
        chunks = [
            self._chunk("18.10 Tenth section content for chapter eighteen with extra padding here."),
            self._chunk("18.2 Second section content for chapter eighteen with extra padding here."),
            self._chunk("18.5 Fifth section content for chapter eighteen with extra padding here."),
            self._chunk("18.3 Third section content for chapter eighteen with extra padding here."),
        ]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # Sections appear in ascending numeric order: 18.2, 18.3, 18.5, 18.10.
        ix2 = result.index("Section 18.2")
        ix3 = result.index("Section 18.3")
        ix5 = result.index("Section 18.5")
        ix10 = result.index("Section 18.10")
        assert ix2 < ix3 < ix5 < ix10

    def test_section_label_detected_when_header_is_mid_chunk(self) -> None:
        """A section header deep in a chunk (past the old 120-char window) is found."""
        p = self._make_pipeline(_SequenceProvider([]))
        text = "Sentence padding repeats. " * 30 + "\n18.4 Advanced Convolutional Architectures\nContent."
        assert p._detect_section_label(text, 18) == "18.4"

    def test_section_label_ignores_figure_and_table_references(self) -> None:
        """Figure/Table/Equation/Listing "18.N" references do not fabricate sections."""
        p = self._make_pipeline(_SequenceProvider([]))
        for text in [
            "Figure 18.9 shows the accuracy reached 97.89 percent after 22 epochs.",
            "See Table 18.2 for the parameter counts.",
            "Equation 18.3 defines the convolution operation.",
            "Listing 18.7 builds the model.",
            # A wrapped figure reference lands "18.2" at a line start — still not a header.
            "In the example depicted in Figure \r\n18.2, the layer receives input.",
            "Figure\n18.5 presents the results on a new line.",
        ]:
            assert p._detect_section_label(text, 18) is None, text
        # A genuine line-start header is still detected.
        assert p._detect_section_label("\n18.4 Advanced Convolutional Architectures\n", 18) == "18.4"

    def test_single_chapter_header_mid_chunk_not_skipped(self) -> None:
        """A section whose header sits deep in its chunk is still summarized."""
        by_key = {
            "Section 18.4": "Full summary for section four with enough detail to pass."
        }
        provider = _SequenceProvider(by_key=by_key)
        p = self._make_pipeline(provider)
        # The 18.4 heading appears only after ~300 chars, on its own line — under
        # the old first-120-chars scan this section was silently skipped.
        chunks = [
            self._chunk(
                "Sentence padding repeats. " * 30
                + "\n18.4 Advanced Convolutional Architectures\nContent here."
            )
        ]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "Section 18.4" in result
        assert "Full summary for section four" in result

    def test_multi_chapter_processes_more_than_old_window_cap(self) -> None:
        """A book with 12 chapters is summarized in full, not truncated at 8."""
        by_key = {
            f"Chapter {n} — Title {n}": f"Full summary for chapter number {n} with enough detail to pass."
            for n in range(1, 13)
        }
        provider = _SequenceProvider(by_key=by_key)
        p = self._make_pipeline(provider)
        buckets = {n: [self._chunk(f"chapter {n} body text")] for n in range(1, 13)}
        result = p._generate_multi_chapter_summary(
            list(range(1, 13)), buckets, {n: f"Title {n}" for n in range(1, 13)}
        )
        # Every chapter 1..12 is present (regression: previously capped at 8).
        for n in range(1, 13):
            assert f"Chapter {n}" in result
            assert f"Full summary for chapter number {n}" in result
        assert len(provider.calls) == 12


