"""Unit tests for RAGPipeline streaming wiring.

These tests verify that the RAG pipeline correctly routes requests to either
stream_chat or generate based on config.streaming_enabled and provider capabilities.
"""

from collections.abc import Callable, Sequence
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._mixins import (
    _OVERVIEW_MAX_WORDS,
    _SUMMARY_REDUCE_MAX_TOKENS,
    SUMMARY_TEMPERATURE,
    _contains_reasoning_leak,
    _ground_figures,
    _is_stream_leak,
    _prune_implausible_metric_figures,
    _scrub_self_correction,
    _strip_numeric_self_correction,
    _trim_to_sentence_end,
)
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
            p._clean_chapter_title("The ML4T Workflow ....... 223")
            == "The ML4T Workflow"
        )
        assert (
            p._clean_chapter_title(
                "Machine Learning for Trading - From Idea to Execution 1"
            )
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
            == ("Time-Series Models for Volatility Forecasts and Statistical Arbitrage")
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
        text = 'Module 7: Completion & Best Practices Transition: "Final module"'
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
                'Module 1: Meet Your AI Assistant Transition: "Let\'s start"',
                'Module 2: The 3-Part Prompt Formula Transition: "Now the single"',
                "Module 7 Circulate and check that students verify (step 3) —",
                'Module 3: Working with Everyday Files Transition: "Now let\'s"',
            ]
        )
        entries, _, _ = pipeline._derive_chapter_numbers(
            [{"chunk_text": text, "source_file": "deck.pptx"}]
        )
        nums = sorted(e[0] for e in entries)
        assert nums == [1, 2, 3], f"got {nums}"
        assert 7 not in nums, (
            "bare 'Module 7 Circulate' reference must not add chapter 7"
        )


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
        "zebra",
        "giraffe",
        "trampoline",
        "sapphire",
        "bakelite",
        "vertebra",
        "compass",
        "harbor",
        "syringe",
        "enamel",
        "abacus",
        "scaffold",
        "pilgrim",
        "turbine",
        "torrent",
        "sampler",
        "beetle",
        "carnival",
        "monograph",
        "espresso",
        "necklace",
        "paradigm",
        "kettle",
        "octopus",
        "verdict",
        "meadow",
        "glacier",
        "bundle",
        "flask",
        "compartment",
        "lantern",
        "gyroscope",
        "basketball",
        "garrison",
        "numeral",
        "meridian",
        "splinter",
        "reassembly",
        "soil",
        "oracle",
        "basin",
        "quiver",
        "anvil",
        "badger",
        "cilantro",
        "donkey",
        "eclipse",
        "falcon",
        "granite",
        "hedgehog",
        "iguana",
        "jasmine",
        "kayak",
        "lagoon",
        "magnolia",
        "narwhal",
        "obsidian",
        "panther",
        "quagga",
        "rhinoceros",
        "satchel",
        "tapestry",
        "umbrella",
        "vulture",
        "walnut",
        "xylophone",
        "yak",
        "zinnia",
        "amaranth",
        "bramble",
        "cinder",
        "deluge",
        "esker",
        "fjord",
        "goblet",
        "hummock",
        "isthmus",
        "juniper",
        "katydid",
        "lichen",
        "monsoon",
        "nectar",
        "opossum",
        "paddock",
        "quarry",
        "runnel",
        "silt",
        "tundra",
        "urchin",
        "verdant",
        "wattle",
        "yonder",
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
        provider = _SequenceProvider(
            [
                "garbage garbage garbage garbage garbage garbage",
                "A coherent final answer about convolutional networks.",
            ]
        )
        p = self._make_pipeline(provider)
        result = p._generate_guarded("prompt")
        assert result == "A coherent final answer about convolutional networks."
        assert len(provider.calls) == 2
        assert provider.calls[1]["temperature"] == 0.1

    def test_generate_guarded_returns_empty_when_both_bad(self) -> None:
        provider = _SequenceProvider(
            [
                "garg garbage garbage garbage garbage garbage garbage",
                "more garbage more garbage more garbage more garbage",
            ]
        )
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
        provider = _SequenceProvider(
            [
                "Chapter one introduces the core concepts with clear examples.",
                "Chapter two covers the methods and their practical application.",
            ]
        )
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
        provider = _SequenceProvider(
            by_key={"Chapter 2": "Summary for chapter two with enough detail here."}
        )
        p = self._make_pipeline(provider)
        buckets = {1: [], 2: [self._chunk("chapter two body")]}
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "One", 2: "Two"}
        )
        assert "Chapter 1" not in result
        assert "Chapter 2 — Two" in result
        assert len(provider.calls) == 1

    def test_single_chapter_splits_into_bounded_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        provider = _SequenceProvider(
            by_key={
                "Part 1 of": (
                    "The first window covers convolutional layers, weight sharing, "
                    "and pooling in clear detail, long enough to pass the check."
                ),
                "Part 2 of": (
                    "The second window covers transfer learning and satellite "
                    "imagery, also written clearly and long enough to pass."
                ),
                "terse digests": (
                    "The chapter overview weaves both window digests into one "
                    "coherent narrative with adequate length to pass checks."
                ),
            }
        )
        p = self._make_pipeline(provider)
        # Two ~4000-char chunks exceed the ~6000-char window budget -> two windows.
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs for Trading")
        # Two map digests feed one reduce call that writes the final overview.
        assert len(provider.calls) == 3
        assert "Part 1 of 2" in provider.calls[0]["prompt"]
        assert "Part 2 of 2" in provider.calls[1]["prompt"]
        assert "The chapter overview weaves" in result

    def test_single_chapter_drops_garbage_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        provider = _SequenceProvider(
            by_key={
                "Part 1 of": "garbage garbage garbage garbage garbage garbage",
                "Part 2 of": "A clean detailed summary of the second window with enough length.",
                "terse digests": (
                    "The overview covers the surviving digest content coherently "
                    "with adequate length to pass the plausibility check."
                ),
            }
        )
        p = self._make_pipeline(provider)
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # Window 1's garbage digest is dropped; only window 2 reaches the reduce call.
        assert "garbage" not in result
        reduce_prompt = provider.calls[-1]["prompt"]
        assert "A clean detailed summary" in reduce_prompt
        assert reduce_prompt.count("--- Part") == 1
        assert "The overview covers the surviving" in result

    def test_multi_chapter_emits_completed_sections(self) -> None:
        """Each chapter's summary is emitted as it completes (progressive output)."""
        streamed: list[str] = []
        by_key = {
            "Chapter 1": "Chapter one summary sentence with enough detail to pass here.",
            "Chapter 2": "Chapter two summary sentence with enough detail to pass here.",
        }
        provider = _SequenceProvider(by_key=by_key)
        p = self._make_pipeline(provider)
        p._on_chunk = lambda content, _reasoning: streamed.append(content or "")

        buckets = {
            1: [self._chunk("chapter one body text")],
            2: [self._chunk("chapter two body text")],
        }
        result = p._generate_multi_chapter_summary(
            [1, 2], buckets, {1: "Intro", 2: "Methods"}
        )
        # Both chapters' summaries were surfaced via the callback as they finished.
        assert "Chapter one summary sentence" in "".join(streamed)
        assert "Chapter two summary sentence" in "".join(streamed)
        # Concatenated result still contains both chapters.
        assert "Chapter 2 — Methods" in result

    def test_multi_chapter_stream_separates_chapters(self) -> None:
        """Streamed output carries each heading and blank-line chapter breaks."""
        streamed: list[str] = []
        provider = _SequenceProvider(
            by_key={
                "Chapter 1": "Chapter one summary sentence with enough detail to pass here.",
                "Chapter 2": "Chapter two summary sentence with enough detail to pass here.",
            }
        )
        p = self._make_pipeline(provider)
        p._on_chunk = lambda content, _reasoning: streamed.append(content or "")

        buckets = {
            1: [self._chunk("chapter one body text")],
            2: [self._chunk("chapter two body text")],
        }
        p._generate_multi_chapter_summary([1, 2], buckets, {1: "Intro", 2: "Methods"})
        live = "".join(streamed)
        # Each chapter heading appears in the live stream ...
        assert "Chapter 1 — Intro" in live
        assert "Chapter 2 — Methods" in live
        # ... and consecutive chapters are separated by a blank line, so the
        # second heading never glues onto the first chapter's last sentence.
        assert "\n\nChapter 2 — Methods" in live

    def test_degenerate_bounded_window_is_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A degenerate (garbage) bounded window is dropped while clean ones survive."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )

        class _MixStreamProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                if "Part 1 of" in prompt:
                    return "garbage garbage garbage garbage garbage garbage"
                return "A clean second window summary with enough length to pass."

        provider = _MixStreamProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: None
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # The degenerate first window is dropped; the clean second window survives.
        assert "garbage" not in result
        assert "A clean second window summary" in result

    def test_chapter_summary_emits_grounded_content_only(self) -> None:
        """Chapter summaries emit grounded content only; reasoning never appears."""
        reasoning_seen: list[str] = []
        content_emitted: list[str] = []
        provider = _SequenceProvider(
            by_key={
                "document content below covers": (
                    "A final plausible summary with enough length to pass."
                ),
            }
        )
        p = self._make_pipeline(provider)

        def on_chunk(content: str, reasoning: str | None) -> None:
            if reasoning:
                reasoning_seen.append(reasoning)
            if content:
                content_emitted.append(content)

        p._on_chunk = on_chunk
        chunks = [self._chunk("Detailed chapter content " * 60)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # No reasoning is ever surfaced to the terminal.
        assert reasoning_seen == []
        # The heading is surfaced first, then the completed summary streams after.
        assert content_emitted and content_emitted[0].lstrip().startswith(
            "Chapter 18 (overview):"
        )
        # The completed summary is emitted (progressive output).
        assert "A final plausible summary" in "".join(content_emitted)
        assert "A final plausible summary with enough length to pass." in result

    def test_summary_streams_one_reduce_call_over_window_digests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Window digests feed one streamed reduce call that writes the overview."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        emitted: list[str] = []
        prompts: list[str] = []

        class _StreamReduceProvider(_SequenceProvider):
            def stream_chat(self, messages, on_chunk, temperature=0.7, max_tokens=4096):
                prompt = messages[0]["content"]
                prompts.append(prompt)
                if "internal digest" in prompt:
                    if "Part 1 of" in prompt:
                        text = "The first section covers CNN convolutions in detail."
                    else:
                        text = "The second section continues with pooling."
                else:
                    text = (
                        "The overview covers convolution layers first and then "
                        "pooling, written as one coherent piece of prose here."
                    )
                for i in range(0, len(text), 8):
                    on_chunk(text[i : i + 8], None)
                return text

        provider = _StreamReduceProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda c, _r: emitted.append(c or "")
        chunks = [self._chunk("A" * 3000), self._chunk("B" * 3000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert len(prompts) == 3  # two map digests + one reduce call
        reduce_prompt = prompts[-1]
        assert reduce_prompt.index(
            "The first section covers CNN convolutions"
        ) < reduce_prompt.index("The second section continues with pooling")
        # The final overview streams as ONE piece: single voice, no per-window seams.
        assert "The overview covers convolution layers" in "".join(emitted)
        assert "The overview covers convolution layers" in result

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

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
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

    def test_streaming_aborts_on_content_self_correction(self) -> None:
        """A content-channel figure-verification leak is aborted and clean-retried."""
        emitted: list[str] = []

        class _LeakProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                leaked = (
                    "AlexNet hit 77.?? (wait, the text says 79.33 percent) on CIFAR-10."
                )
                for word in leaked.split():
                    on_chunk(word + " ", None)
                return leaked

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                # Deterministic low-temperature retry returns a clean, stable figure.
                if temperature == 0.1:
                    return (
                        "AlexNet achieved the best test accuracy of 79.33 percent "
                        "on CIFAR-10, exceeding the feedforward network."
                    )
                return ""

        provider = _LeakProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, _reasoning: emitted.append(content or "")
        result = p._generate_window_guarded("prompt", "Chapter 18 (overview)")
        # The clean low-temperature retry replaces the leaked draft.
        assert "79.33 percent" in result
        assert "??" not in result
        assert "the text says" not in result

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

    def test_summary_path_uses_low_temperature_and_max_tokens(self) -> None:
        """Summary reduce samples at SUMMARY_TEMPERATURE with the reduce token cap."""
        captured: list[dict[str, Any]] = []

        class _CaptureProvider(_SequenceProvider):
            def generate(self, prompt, temperature=1.0, max_tokens=384000) -> str:
                captured.append({"temperature": temperature, "max_tokens": max_tokens})
                return "A plausible summary sentence that is long enough here."

        provider = _CaptureProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = False  # force the guarded sync path
        p._config.llm_temperature = 1.0
        p._config.llm_max_tokens = 384000
        chunks = [self._chunk("18.1 Section content here.")]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "A plausible summary sentence" in result
        # Summary generation uses a dedicated low temperature so figures are
        # reproduced faithfully rather than regenerated at the creative default,
        # and its output cap is a ceiling, not a target: GLM-class servers spend
        # the same budget on hidden reasoning and visible content, so a tight
        # cap amputates the overview mid-sentence.
        assert captured[0].get("temperature") == SUMMARY_TEMPERATURE
        assert captured[0].get("max_tokens") == _SUMMARY_REDUCE_MAX_TOKENS

    def test_trim_to_sentence_end_removes_dangling_fragment(self) -> None:
        """A window truncated mid-sentence is cut back to the last full sentence."""
        assert (
            _trim_to_sentence_end("The model is trained. It uses SGD with Nester")
            == "The model is trained."
        )
        # A complete ending sentence is untouched.
        assert (
            _trim_to_sentence_end("The forecasts track the 2019 data well.")
            == "The forecasts track the 2019 data well."
        )

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
        chunks = [
            self._chunk(
                "RNN chapter on multivariate weekly return forecasting reported an "
                "average weekly IC of 3.32 and 6.68, and an information coefficient "
                "of 0.9889."
            )
        ]
        result = p._generate_single_chapter_summary(chunks, 19, "RNNs")
        # Impossible IC values (> 1) are dropped; the metric name is retained.
        assert "3.32" not in result and "6.68" not in result
        assert "IC" in result or "coefficient" in result
        # An in-range value (<= 1) that is grounded in the source context is kept.
        assert "0.9889" in result

    def test_implausible_hedged_metric_values_pruned(self) -> None:
        """A hedged impossible value ('an IC of around 4') is stripped as well."""
        text = (
            "Early stopping yields a biased, cherry-picked information "
            "coefficient of around 4, and later sections report a daily "
            "average IC of approximately 0.009 with adequate detail here."
        )
        pruned = _prune_implausible_metric_figures(text)
        assert "around 4" not in pruned
        assert "coefficient" in pruned
        assert "approximately 0.009" in pruned

    def test_grounding_drops_fabricated_year(self) -> None:
        """A year the source never states is removed from the summary."""
        summary = (
            "a backtest over 2023\u20132027 yields a 35.6% cumulative return "
            "and a Sharpe of 0.53"
        )
        context = (
            "the naive strategy earned four basis points per day over the "
            "2013-2017 period, a 35.6 percent cumulative return and a Sharpe "
            "ratio of 0.53."
        )
        out = _ground_figures(summary, context)
        assert "2023" not in out and "2027" not in out
        assert "35.6%" in out
        assert "0.53" in out

    def test_grounding_drops_fabricated_percent(self) -> None:
        """A percentage absent from the source is removed."""
        summary = "AlexNet hit a top-5 error of 92% versus 16%"
        context = "AlexNet achieved a top-5 error of 16 percent"
        out = _ground_figures(summary, context)
        assert "92%" not in out
        assert "16%" in out

    def test_grounding_keeps_grounded_magnitude(self) -> None:
        """A magnitude figure present in the source is retained verbatim."""
        summary = "AlexNet has roughly 60 million parameters"
        context = "AlexNet has about 60 million parameters, far more than LeNet5"
        assert _ground_figures(summary, context) == summary

    def test_grounding_preserves_small_counts(self) -> None:
        """Small whole counts absent from the source are left alone."""
        summary = "it uses 15 technical indicators and 10 classes"
        context = "the chapter builds indicators spanning ten classes"
        out = _ground_figures(summary, context)
        assert "15" in out and "10" in out

    def test_grounding_tolerates_rounding(self) -> None:
        """A correctly rounded decimal is not destroyed (3.7 vs 3.57)."""
        summary = "ResNet pushed top-5 error to 3.7%"
        context = "ResNet reached a top-5 error of 3.57%"
        assert "3.7%" in _ground_figures(summary, context)

    def test_grounding_years_are_exact(self) -> None:
        """Years must match exactly; a close year is still fabricated."""
        summary = "the winning year was 2012"
        context = "the model was developed around 2015"
        assert _ground_figures(summary, context) == "the winning year was "

    def test_reasoning_leak_detected(self) -> None:
        """Leaked chain-of-thought self-talk marks a window implausible."""
        p = self._make_pipeline(_SequenceProvider([]))
        leaked = (
            "The dataset has 26,631 filings? Actually '22,631'? No, I misread, "
            "it's 16,758. I'll just say over two million parameters. This window "
            "is otherwise written out fully enough and lexically varied."
        )
        assert p._is_plausible_summary(leaked) is False

    def test_reasoning_leak_clean_passes(self) -> None:
        """A clean, diverse summary is not flagged as reasoning leakage."""
        p = self._make_pipeline(_SequenceProvider([]))
        clean = (
            "RNNs apply the same transformation at each time step. The LSTM cell "
            "combines an input gate, forget gate, and output gate to regulate the "
            "cell state and mitigate vanishing gradients over long sequences."
        )
        assert p._is_plausible_summary(clean) is True

    def test_contains_reasoning_leak_markers(self) -> None:
        """The marker matcher is case-insensitive and specific."""
        assert _contains_reasoning_leak("I'm misreading this number".lower()) is True
        assert _contains_reasoning_leak("Let me re-check the figure".lower()) is True
        assert _contains_reasoning_leak("a clean factual summary".lower()) is False

    def test_contains_self_correction_leak_markers(self) -> None:
        """Mid-prose self-correction scaffolding is flagged as a reasoning leak."""
        assert (
            _contains_reasoning_leak(
                "over windows from 15 to 30? Actually, windows ranged from 15 to 90.".lower()
            )
            is True
        )
        assert (
            _contains_reasoning_leak(
                "I meant to say the value is 4 million parameters.".lower()
            )
            is True
        )
        assert _contains_reasoning_leak("or rather the path diverges".lower()) is True
        assert (
            _contains_reasoning_leak(
                "the model reached 79.33 percent accuracy across twenty epochs.".lower()
            )
            is False
        )

    def test_reasoning_spiral_detected(self) -> None:
        """Hedge-dense, self-contradicting chain-of-thought is flagged."""
        p = self._make_pipeline(_SequenceProvider([]))
        spiral = (
            "No, wait, actually let me re-read. No, above 102 percent? No, above "
            "104? No, above 106? I misread. No, hold on, actually let me check "
            "again. No, wait, actually the value is different. No, above 108 "
            "percent? No, above 110? This self-verification keeps repeating "
            "without resolving anything. No, wait, actually I misread again. "
            "No, above 112 percent? No, above 114? No, above 116 percent? "
            "No, above 118? I misread yet again. No, wait, actually let me "
            "re-read the whole passage once more."
        )
        assert p._is_reasoning_spiral(spiral) is True

    def test_reasoning_spiral_normal_passes(self) -> None:
        """A short/ordinary planning block is never treated as a spiral."""
        p = self._make_pipeline(_SequenceProvider([]))
        assert (
            p._is_reasoning_spiral(
                "Outline the chapter structure, then summarize each section in order."
            )
            is False
        )
        assert p._is_reasoning_spiral("") is False

    def test_page_query_answers_verbatim(self) -> None:
        """A 'page N' query returns the page text verbatim, no LLM call."""
        provider = _SequenceProvider(["should not be used"])
        p = self._make_pipeline(provider)
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = [
            {
                "chunk_id": "c1",
                "chunk_text": "[ 500 ] page content about CNNs\nsecond sentence",
                "page_number": 529,
                "printed_page": 500,
            }
        ]
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500 of the book")

        assert res is not None
        assert res["sources"] and res["sources"][0]["printed_page"] == 500
        assert res["answer"] == "page content about CNNs\nsecond sentence"
        assert provider.calls == []
        storage_mock.find_chunks.assert_any_call(source_file=None, printed_page=500)

    def test_page_query_non_page_returns_none(self) -> None:
        """Queries without a page reference fall back to the semantic path."""
        p = self._make_pipeline(_SequenceProvider([]))
        assert p._answer_page_query("how do RNNs work") is None

    def test_page_query_missing_page_returns_not_found(self) -> None:
        """A referenced page with no stored chunks yields a graceful 'not found'."""
        p = self._make_pipeline(_SequenceProvider([]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = []
        searcher_mock.attach_mock(storage_mock, "storage")
        res = p._answer_page_query("what is on page 999")
        assert res is not None
        assert res["sources"] == []

    def test_page_query_returns_full_page_verbatim(self) -> None:
        """The full page text is returned verbatim with the marker stripped."""
        provider = _SequenceProvider(["should not be used"])
        p = self._make_pipeline(provider)
        long_text = "[ 500 ] " + "w" * 300
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = [
            {
                "chunk_id": "c1",
                "chunk_text": long_text,
                "page_number": 529,
                "printed_page": 500,
            }
        ]
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500 of the book")

        assert res is not None
        assert res["answer"] == "w" * 300
        assert provider.calls == []

    @pytest.mark.asyncio
    async def test_answer_page_query_async_returns_page_result(self) -> None:
        """_answer_page_query_async resolves a page query to its printed chunks."""
        p = self._make_pipeline(_SequenceProvider(["page 42 summary"]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = [
            {
                "chunk_id": "c1",
                "chunk_text": "[ 42 ] page 42 body",
                "page_number": 71,
                "printed_page": 42,
            }
        ]
        searcher_mock.attach_mock(storage_mock, "storage")

        res = await p._answer_page_query_async("what is on page 42 of the book")

        assert res is not None
        assert res["sources"] and res["sources"][0]["printed_page"] == 42
        storage_mock.find_chunks.assert_any_call(source_file=None, printed_page=42)

    @pytest.mark.asyncio
    async def test_query_async_routes_page_before_semantic(self) -> None:
        """query_async answers page queries without falling through to search."""
        p = self._make_pipeline(_SequenceProvider(["page 42 summary"]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = [
            {
                "chunk_id": "c1",
                "chunk_text": "[ 42 ] page 42 body",
                "page_number": 71,
                "printed_page": 42,
            }
        ]
        searcher_mock.attach_mock(storage_mock, "storage")

        res = await p.query_async("what is on page 42 of the book")

        assert res is not None
        assert res["sources"] and res["sources"][0]["printed_page"] == 42
        searcher_mock.search_async.assert_not_awaited()

    def test_page_query_expands_to_full_physical_page(self) -> None:
        """A page split across chunks returns the whole page, not just the marker."""
        p = self._make_pipeline(_SequenceProvider(["page 500 overview"]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()

        def _find(**kwargs: Any) -> list[dict[str, Any]]:
            if "printed_page" in kwargs:
                # Only the first chunk carries the printed-page marker.
                return [
                    {
                        "chunk_id": "c1",
                        "chunk_text": "[ 500 ] first half of the page",
                        "page_number": 529,
                        "printed_page": 500,
                    }
                ]
            # page_number expansion: both halves of the physical page.
            return [
                {
                    "chunk_id": "c1",
                    "chunk_text": "[ 500 ] first half of the page",
                    "page_number": 529,
                    "printed_page": 500,
                },
                {
                    "chunk_id": "c2",
                    "chunk_text": "second half of the same page without a marker",
                    "page_number": 529,
                    "printed_page": None,
                },
            ]

        storage_mock.find_chunks.side_effect = _find
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500 of the book")

        assert res is not None
        source_ids = {c["chunk_id"] for c in res["sources"]}
        assert source_ids == {"c1", "c2"}
        storage_mock.find_chunks.assert_any_call(source_file=None, printed_page=500)
        storage_mock.find_chunks.assert_any_call(source_file=None, page_number=[529])

    def test_page_query_orders_chunks_by_page_pos(self) -> None:
        """Verbatim page text is emitted in page_pos order, not scroll order."""
        p = self._make_pipeline(_SequenceProvider([]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()

        def _find(**kwargs: Any) -> list[dict[str, Any]]:
            if "printed_page" in kwargs:
                return [
                    {
                        "chunk_id": "c1",
                        "chunk_text": "[ 500 ] head",
                        "page_number": 529,
                        "printed_page": 500,
                        "page_pos": 0,
                    }
                ]
            # Scroll order is scrambled; page_pos must restore it.
            return [
                {
                    "chunk_id": "c3",
                    "chunk_text": "third sentence",
                    "page_number": 529,
                    "page_pos": 2,
                },
                {
                    "chunk_id": "c1",
                    "chunk_text": "[ 500 ] head",
                    "page_number": 529,
                    "printed_page": 500,
                    "page_pos": 0,
                },
                {
                    "chunk_id": "c2",
                    "chunk_text": "second sentence",
                    "page_number": 529,
                    "page_pos": 1,
                },
            ]

        storage_mock.find_chunks.side_effect = _find
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500")

        assert res is not None
        assert res["answer"] == "head\nsecond sentence\nthird sentence"
        assert [c["chunk_id"] for c in res["sources"]] == ["c1", "c2", "c3"]

    def test_page_query_collapses_chunk_overlap(self) -> None:
        """Consecutive page_pos chunks have their boundary overlap collapsed."""
        p = self._make_pipeline(_SequenceProvider([]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()

        def _find(**kwargs: Any) -> list[dict[str, Any]]:
            if "printed_page" in kwargs:
                return [
                    {
                        "chunk_id": "c1",
                        "chunk_text": "[ 500 ] The quick brown fox jumps over",
                        "page_number": 529,
                        "printed_page": 500,
                        "page_pos": 0,
                    }
                ]
            return [
                {
                    "chunk_id": "c2",
                    "chunk_text": "over the lazy dog",
                    "page_number": 529,
                    "page_pos": 1,
                },
                {
                    "chunk_id": "c1",
                    "chunk_text": "[ 500 ] The quick brown fox jumps over",
                    "page_number": 529,
                    "printed_page": 500,
                    "page_pos": 0,
                },
            ]

        storage_mock.find_chunks.side_effect = _find
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500")

        assert res is not None
        assert res["answer"] == "The quick brown fox jumps over the lazy dog"

    def test_page_query_strips_page_stub_line(self) -> None:
        """A standalone '[ N ]' stub line is removed from the page text."""
        p = self._make_pipeline(_SequenceProvider([]))
        searcher_mock = cast(Any, p._searcher)
        storage_mock = MagicMock()
        storage_mock.find_chunks.return_value = [
            {
                "chunk_id": "c1",
                "chunk_text": (
                    "Word Embeddings for Earnings Calls and SEC Filings\n"
                    "[ 500 ]\n"
                    "Preprocessing body"
                ),
                "page_number": 529,
                "printed_page": 500,
            }
        ]
        searcher_mock.attach_mock(storage_mock, "storage")

        res = p._answer_page_query("what is on page 500")

        assert res is not None
        assert res["answer"] == (
            "Word Embeddings for Earnings Calls and SEC Filings\nPreprocessing body"
        )

    def test_single_chapter_preserves_window_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Map digests reach the reduce prompt in source order."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        provider = _SequenceProvider(
            by_key={
                "Part 1 of": "First window summary with plenty length to pass.",
                "Part 2 of": "Second window summary with plenty length to pass.",
                "terse digests": (
                    "The overview weaves the digest material into one "
                    "coherent narrative with adequate length to pass."
                ),
            }
        )
        p = self._make_pipeline(provider)
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        reduce_prompt = provider.calls[-1]["prompt"]
        assert reduce_prompt.index("First window summary") < reduce_prompt.index(
            "Second window summary"
        )
        assert "The overview weaves" in result

    def test_stream_leak_detects_inline_self_correction(self) -> None:
        """Inline self-correction ("48? No--45.78") is detected as a stream leak."""
        assert _is_stream_leak("a test accuracy of 48? no--45.78 percent")
        assert _is_stream_leak("at 77.29? actually the text says 78.29 percent")
        assert not _is_stream_leak("Validation accuracy reached 97.96 percent.")
        assert not _is_stream_leak("The chapter presents clean, confident prose.")

    def test_stream_leak_ignores_benign_text_citations(self) -> None:
        """Ordinary "the text says/gives" citations never abort a window.

        A false trip costs the whole window: the stream aborts, the low-temp
        retry tends to repeat the same citation style, and the window is then
        silently dropped from the overview.
        """
        assert not _is_stream_leak("the text gives several examples of this.")
        assert not _is_stream_leak("the text states the model uses relu.")
        assert not _is_stream_leak("as the text says, early stopping applies.")

    def test_scrub_self_correction_handles_hedge_forms(self) -> None:
        """Hedge connectors and "(wait, the text says ...)" forms scrub clean."""
        assert (
            _scrub_self_correction(
                "accuracy of 77.29? Actually the text says 78.29 percent"
            )
            == "accuracy of 78.29 percent"
        )
        assert (
            _scrub_self_correction(
                "output of 77.?? (wait, the text says 78.29 percent)"
            )
            == "output of 78.29 percent"
        )
        assert _scrub_self_correction("48? No--45.78? Actually 43.05") == "43.05"
        clean = "Validation accuracy reached 45.78 percent."
        assert _scrub_self_correction(clean) == clean

    def test_streamed_leak_is_scrubbed_without_aborting_window(self) -> None:
        """A hedge leak inside the withheld tail is scrubbed; the window lives."""
        emitted: list[str] = []

        class _HedgeLeakProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                text = (
                    "The model reached 48? No--45.78 percent validation "
                    "accuracy in the final epoch."
                )
                for i in range(0, len(text), 10):
                    on_chunk(text[i : i + 10], None)
                return text

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                return "retry must not run"

        provider = _HedgeLeakProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda c, _r: emitted.append(c or "")
        result = p._summarize_bounded(
            heading="Chapter 18 (overview)",
            windows=[
                [self._chunk("It reached 45.78 percent validation accuracy. " * 6)]
            ],
            instruction="Summarize.",
        )
        assert "45.78 percent" in result
        assert "48? No--" not in result
        assert "48? No--" not in "".join(emitted)
        assert "retry must not run" not in result

    def test_mid_stream_death_recovers_with_continuation(self) -> None:
        """A dropped stream is continued seamlessly instead of losing the tail."""
        emitted: list[str] = []
        prompts: list[str] = []

        class _DyingStreamProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                prompts.append(prompt)
                if "<draft>" not in prompt:
                    text = "The chapter introduces convolution layers and pooling"
                    for i in range(0, len(text), 12):
                        on_chunk(text[i : i + 12], None)
                    raise RuntimeError("stream dropped mid-output")
                text = " stages with worked examples from the source text."
                for i in range(0, len(text), 12):
                    on_chunk(text[i : i + 12], None)
                return text

        provider = _DyingStreamProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda c, _r: emitted.append(c or "")
        result = p._summarize_bounded(
            heading="Chapter 18 (overview)",
            windows=[[self._chunk("Convolution and pooling source text. " * 10)]],
            instruction="Summarize.",
        )
        assert "pooling stages with worked examples" in result
        assert any("<draft>" in pr for pr in prompts)
        assert "worked examples" in "".join(emitted)

    def test_empty_stream_death_retries_before_skipping(self) -> None:
        """A window that dies before emitting anything is regenerated once."""

        class _SilentDeathProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                if "<draft>" in messages[0]["content"]:
                    raise AssertionError("resume must not run for empty partials")
                raise RuntimeError("provider stalled during reasoning")

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                if temperature == 0.1:
                    return "A complete regenerated summary of the section."
                return "garbage"

        provider = _SilentDeathProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        result = p._summarize_bounded(
            heading="Chapter 18 (overview)",
            windows=[[self._chunk("Source text for the section. " * 10)]],
            instruction="Summarize.",
        )
        assert "regenerated summary" in result

    def test_map_digest_content_never_streams(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Map-pass digest text stays internal; only its reasoning streams live."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        events: list[tuple[str, str | None]] = []

        class _MapStreamProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                if "internal digest" in prompt:
                    on_chunk("", "thinking about the section")
                    text = (
                        "Digest prose about convolutional layers and pooling examples."
                    )
                else:
                    text = "The overview weaves the digest material into one narrative."
                for i in range(0, len(text), 12):
                    on_chunk(text[i : i + 12], None)
                return text

        provider = _MapStreamProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda c, r: events.append((c or "", r))
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        streamed_content = "".join(c for c, _r in events)
        assert "Digest prose" not in streamed_content, (
            "digest content must never reach the screen"
        )
        assert any(r for _c, r in events), "map reasoning still streams for liveness"
        assert "The overview weaves" in result

    def test_reduce_amputated_mid_sentence_gets_continuation(self) -> None:
        """A normal return cut mid-sentence (GLM output cap) is continued."""
        prompts: list[str] = []

        class _AmputatingProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                prompts.append(prompt)
                if "<draft>" in prompt:
                    text = " stages with worked examples from the source text."
                else:
                    text = "The chapter introduces convolution layers and pooling"
                for i in range(0, len(text), 12):
                    on_chunk(text[i : i + 12], None)
                return text

        provider = _AmputatingProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        chunks = [self._chunk("Convolution and pooling source text. " * 10)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert any("<draft>" in pr for pr in prompts), (
            "mid-sentence normal return must trigger a continuation"
        )
        assert "pooling stages with worked examples" in result

    def test_reduce_empty_normal_return_retries(self) -> None:
        """A normal return with no content at all gets one clean regeneration."""
        calls: list[tuple[float, str]] = []

        class _EmptyProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                return ""

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                calls.append((temperature, prompt))
                return "A complete regenerated overview of the chapter section."

        provider = _EmptyProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        chunks = [self._chunk("Source text for the section. " * 10)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert len(calls) == 1, "empty normal return must fire exactly one retry"
        assert calls[0][0] == 0.1, "empty-return retry runs at the low temperature"
        assert "regenerated overview" in result

    def test_map_digest_failure_skips_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A window whose digest fails is skipped without killing the overview."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        stream_prompts: list[str] = []

        class _FlakyDigestProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                stream_prompts.append(prompt)
                if "internal digest" in prompt:
                    if "Part 1 of 2" in prompt:
                        raise RuntimeError("digest stream dropped")
                    text = (
                        "Digest prose about convolutional layers and pooling examples."
                    )
                else:
                    text = "The overview weaves the digest material into one narrative."
                for i in range(0, len(text), 12):
                    on_chunk(text[i : i + 12], None)
                return text

            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                return "garbage garbage garbage garbage garbage garbage garbage"

        provider = _FlakyDigestProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "The overview weaves" in result
        reduce_prompts = [pr for pr in stream_prompts if "terse digests" in pr]
        assert len(reduce_prompts) == 1
        assert reduce_prompts[0].count("--- Part") == 1, (
            "failed digest is skipped, not stubbed"
        )
        assert "Digest prose" in reduce_prompts[0]

    def test_single_pass_uses_one_call_over_full_source(self) -> None:
        """A chapter fitting the context budget is summarized in ONE call."""
        prompts: list[str] = []

        class _SinglePassProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                prompts.append(prompt)
                text = (
                    "The overview covers convolution layers first and then "
                    "pooling, written as one coherent piece of prose here."
                )
                for i in range(0, len(text), 8):
                    on_chunk(text[i : i + 8], None)
                return text

        provider = _SinglePassProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        chunks = [self._chunk("A" * 4000), self._chunk("B" * 4000)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert len(prompts) == 1, "single-pass must not stage digest calls"
        assert "A" * 50 in prompts[0] and "B" * 50 in prompts[0], (
            "the full source reaches the one call"
        )
        assert "--- Part" not in prompts[0]
        assert "internal digest" not in prompts[0]
        assert "The overview covers convolution layers" in result

    def test_hierarchically_condenses_large_digest_sets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Digests over the hierarchy threshold are group-condensed pre-reduce."""
        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        stream_prompts: list[str] = []
        group_prompts: list[str] = []

        class _HierarchyProvider(_SequenceProvider):
            def generate(self, prompt, temperature=0.7, max_tokens=4096) -> str:
                self.calls.append({"prompt": prompt, "temperature": temperature})
                if "condensing intermediate digests" in prompt:
                    group_prompts.append(prompt)
                    return (
                        "Merged digest of several parts covering convolution, "
                        "pooling, and regularization in varied prose form."
                    )
                return "garbage garbage garbage garbage garbage garbage garbage"

            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompt = messages[0]["content"]
                stream_prompts.append(prompt)
                if "internal digest" in prompt:
                    text = (
                        "Digest prose about convolutional layers and pooling "
                        "examples from this part of the chapter."
                    )
                else:
                    text = (
                        "The overview weaves the group digests into one "
                        "coherent narrative about the chapter's methods."
                    )
                for i in range(0, len(text), 12):
                    on_chunk(text[i : i + 12], None)
                return text

        provider = _HierarchyProvider()
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        chunks = [self._chunk(f"source part {i} " + "x" * 3200) for i in range(13)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        # 13 digests -> ceil(13/8)=2 balanced groups (7+6), then one reduce.
        assert len(group_prompts) == 2
        reduce_prompt = [pr for pr in stream_prompts if "terse digests" in pr][-1]
        assert reduce_prompt.count("--- Part") == 2
        assert reduce_prompt.count("Merged digest of several parts") == 2
        assert "Part 13 of 13" not in reduce_prompt
        assert "The overview weaves the group digests" in result

    def test_finalize_overview_enforces_word_budget(self) -> None:
        """An overlong overview is cut at a sentence boundary; a normal one passes."""
        p = self._make_pipeline(_SequenceProvider([]))
        over = "Sentence one stands. " + (
            "More varied detail follows here. " * (_OVERVIEW_MAX_WORDS // 5 + 10)
        )
        result = p._finalize_overview(over, "")
        assert len(result.split()) <= _OVERVIEW_MAX_WORDS
        assert result.endswith(".")
        assert result.startswith("Sentence one stands.")
        typical = "Sentence one stands. " + ("More varied detail follows here. " * 170)
        assert p._finalize_overview(typical, "") == typical.rstrip()
        under = "Short varied overview with adequate length to pass checks."
        assert p._finalize_overview(under, "") == under

    def test_prompts_have_no_numeric_length_bounds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Length is bounded deterministically; prompts carry no word counts."""
        prompts: list[str] = []

        class _RecordingProvider(_SequenceProvider):
            def stream_chat(
                self, messages, on_chunk, temperature=0.7, max_tokens=4096
            ) -> str:
                prompts.append(messages[0]["content"])
                text = (
                    "A final plausible overview with adequate length to pass "
                    "the plausibility checks of the pipeline."
                )
                for i in range(0, len(text), 8):
                    on_chunk(text[i : i + 8], None)
                return text

        p = self._make_pipeline(_RecordingProvider())
        p._config.streaming_enabled = True
        p._on_chunk = lambda _c, _r: None
        p._generate_single_chapter_summary(
            [self._chunk("Chapter body text. " * 30)], 18, "CNNs"
        )
        assert "six to ten short paragraphs" in prompts[0]
        assert "250-300" not in prompts[0]
        assert "100 words" not in prompts[0]

        # Forces the map-reduce fallback: the default single-pass path would
        # summarize this small source in one call (see test_single_pass_*).
        monkeypatch.setattr(
            "secondbrain.rag.pipeline._mixins._SINGLE_PASS_MAX_CHARS", 10
        )
        prompts.clear()
        p2 = self._make_pipeline(_RecordingProvider())
        p2._config.streaming_enabled = True
        p2._on_chunk = lambda _c, _r: None
        p2._generate_single_chapter_summary(
            [self._chunk("A" * 4000), self._chunk("B" * 4000)], 18, "CNNs"
        )
        digest_prompts = [pr for pr in prompts if "internal digest" in pr]
        assert digest_prompts, "fallback path still issues digest calls"
        assert all("100 words" not in pr for pr in digest_prompts)

    def test_split_bounded_aligns_windows_to_sentence_ends(self) -> None:
        """A window whose source ends mid-sentence carries the fragment forward."""
        p = self._make_pipeline(_SequenceProvider([]))
        first = "First sentence here. " * 8 + "Truncated tail with no end"
        second = " and it continues. Second chunk prose follows. More text."
        chunks = [
            {**self._chunk(first), "page": 1},
            {**self._chunk(second), "page": 1},
        ]
        windows = p._split_bounded(chunks, max_chars=len(first) + 10)
        assert len(windows) == 2
        assert windows[0][-1]["chunk_text"].endswith("First sentence here.")
        assert "Truncated tail with no" not in windows[0][-1]["chunk_text"]
        assert windows[1][0]["chunk_text"].startswith(
            "Truncated tail with no end and it continues."
        )
        # The original chunk payloads are never mutated.
        assert chunks[0]["chunk_text"] == first

    def test_split_bounded_keeps_terminal_free_chunks(self) -> None:
        """Terminal-free trailing chunks keep hard boundaries (no merge cascade)."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [self._chunk("A" * 900), self._chunk("B" * 900)]
        windows = p._split_bounded(chunks, max_chars=1000)
        assert len(windows) == 2
        assert windows[0][0]["chunk_text"] == "A" * 900

    def test_strip_numeric_self_correction_keeps_corrected_value(self) -> None:
        """Leaked "<candidate>? No--" artifacts are removed, keeping the figure."""
        cleaned = _strip_numeric_self_correction(
            "a test accuracy of 48? No--45.78 percent vs 72? No, 76.71 percent"
        )
        assert "48? No--" not in cleaned
        assert "72? No," not in cleaned
        assert "45.78 percent" in cleaned
        assert "76.71 percent" in cleaned

    def test_strip_numeric_self_correction_leaves_clean_prose(self) -> None:
        """Clean prose with no self-correction artifact is left unchanged."""
        clean = "Validation accuracy reached 97.96 percent after 10 epochs."
        assert _strip_numeric_self_correction(clean) == clean

    def test_split_bounded_orders_windows_by_page(self) -> None:
        """Windows follow numerical page order even when fed scrambled chunks."""
        p = self._make_pipeline(_SequenceProvider([]))
        pages = [5, 1, 4, 2, 3]
        chunks = [
            {**self._chunk(str(i) * 900), "page": pg} for i, pg in enumerate(pages)
        ]
        # Five ~900-char chunks with a 2000-char budget force multiple windows.
        windows = p._split_bounded(chunks, max_chars=2000)
        flat_pages = [int(c.get("page") or 0) for win in windows for c in win]
        assert len(windows) >= 2
        assert flat_pages == [1, 2, 3, 4, 5]

    def test_section_label_detected_when_header_is_mid_chunk(self) -> None:
        """A section header deep in a chunk (past the old 120-char window) is found."""
        p = self._make_pipeline(_SequenceProvider([]))
        text = (
            "Sentence padding repeats. " * 30
            + "\n18.4 Advanced Convolutional Architectures\nContent."
        )
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
        assert (
            p._detect_section_label("\n18.4 Advanced Convolutional Architectures\n", 18)
            == "18.4"
        )

    def test_leading_section_chapter_detects_heading_owner(self) -> None:
        """The chapter owning a numbered section heading is detected generically."""
        p = self._make_pipeline(_SequenceProvider([]))
        assert p._leading_section_chapter("19.1 Recurrent Networks\ncontent") == "19"
        assert p._leading_section_chapter("\n18.4 CNN Architectures\ncontent") == "18"
        # A wrapped figure reference is a caption, not a section heading.
        assert p._leading_section_chapter("Figure\n18.2 presents the result") is None
        # A plain body paragraph has no owning section.
        assert p._leading_section_chapter("Just a paragraph about pooling.") is None

    def test_filter_chunks_to_chapter_drops_foreign_sections(self) -> None:
        """Chunks with a section heading from another chapter are removed."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            self._chunk("18.1 Convolutional layers are weight shared.\ncontent"),
            self._chunk("A body paragraph with no section heading, still chapter 18."),
            self._chunk("19.1 Recurrent networks keep hidden state.\nRNN content"),
        ]
        kept = p._filter_chunks_to_chapter(chunks, "18", foreign_titles=[])
        assert len(kept) == 2
        assert "19.1" not in kept[0]["chunk_text"] + kept[1]["chunk_text"]
        assert "weight shared" in " ".join(c["chunk_text"] for c in kept)

    def test_filter_chunks_to_chapter_keeps_target_and_body(self) -> None:
        """Target-chapter sections and chapterless body paragraphs survive."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            self._chunk("18.2 Pooling reduces feature map size.\ncontent"),
            self._chunk("Some prose about transfer learning."),
        ]
        kept = p._filter_chunks_to_chapter(chunks, 18, foreign_titles=[])
        assert [c["chunk_text"] for c in kept] == [c["chunk_text"] for c in chunks]

    def test_filter_chunks_to_chapter_drops_foreign_title_opening(self) -> None:
        """A chunk opening with another chapter's title is dropped."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            self._chunk("RNNs for Multivariate Time Series\ncontent leaked in."),
            self._chunk("18.1 CNNs are weight shared.\ncontent"),
        ]
        kept = p._filter_chunks_to_chapter(
            chunks, 18, foreign_titles=["RNNs for Multivariate Time Series"]
        )
        assert len(kept) == 1
        assert "CNNs are weight shared" in kept[0]["chunk_text"]

    def test_filter_chunks_to_chapter_keeps_foreign_title_cross_reference(self) -> None:
        """A mid-text cross-reference to another chapter is not treated as leakage."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            self._chunk(
                "The CNN approach builds on the material in "
                "RNNs for Multivariate Time Series, discussed later."
            )
        ]
        kept = p._filter_chunks_to_chapter(
            chunks, 18, foreign_titles=["RNNs for Multivariate Time Series"]
        )
        assert len(kept) == 1

    def test_detect_chapter_openings_finds_magazine_style_headers(self) -> None:
        """Bare-number magazine chapter openings (marker + number + title) are found."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            {
                "page_number": 30,
                "chunk_text": "[ 2 ]\r\n1\r\nMachine Learning for Trading\r\ncontent",
            },
            {
                "page_number": 620,
                "chunk_text": "[ 591 ]\r\n19\r\nRNNs for Multivariate Time Series and Sentiment Analysis\r\ncontent",
            },
            {
                "page_number": 50,
                "chunk_text": "Regular body paragraph with no chapter opening.",
            },
        ]
        starts = p._detect_chapter_openings(chunks)
        assert starts.get(1) == 30
        assert starts.get(19) == 620
        assert 50 not in starts.values()

    def test_detect_chapter_openings_ignores_toc_and_front_matter(self) -> None:
        """TOC / front-matter entries (low page, dot leader, page suffix) are ignored."""
        p = self._make_pipeline(_SequenceProvider([]))
        chunks = [
            {
                "page_number": 12,
                "chunk_text": "3\r\nUnivariate time-series models 265\r\n...",
            },
            {
                "page_number": 30,
                "chunk_text": "5\r\nPortfolio Optimization ....... 223\r\n...",
            },
            {
                "page_number": 60,
                "chunk_text": "26\r\nHow a backtesting engine works 227\r\n...",
            },
        ]
        starts = p._detect_chapter_openings(chunks)
        assert starts == {}

    def test_single_large_chunk_is_not_skipped(self) -> None:
        """A very long single chunk is still summarized, never dropped."""
        by_key = {
            "chapter 18": "A complete summary even for a large chunk, long enough to pass.",
        }
        provider = _SequenceProvider(by_key=by_key)
        p = self._make_pipeline(provider)
        chunks = [self._chunk("Padding content. " * 400)]
        result = p._generate_single_chapter_summary(chunks, 18, "CNNs")
        assert "A complete summary" in result

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


class _RecordingProvider:
    """Minimal provider that records the prompt and returns a fixed answer."""

    def __init__(self, answer: str) -> None:
        self._answer = answer
        self.last_prompt = ""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.last_prompt = prompt
        return self._answer


class TestGenericOneShotGrounding:
    """Fail-closed figure vetting in the chat chapter-summary one-shot path."""

    def _make_pipeline(self, provider: _RecordingProvider) -> RAGPipeline:
        searcher = MagicMock(spec=Searcher)
        searcher.search.return_value = [
            {
                "chunk_text": (
                    "DenseNet201 achieves 77.29% top-1 accuracy on ImageNet "
                    "with 700 layers."
                ),
                "source_file": "t.pdf",
                "page": 1,
            }
        ]
        return RAGPipeline(
            searcher=searcher,
            llm_provider=provider,  # type: ignore
            top_k=5,
            context_window=5,
        )

    def test_grounds_fabricated_figures(self) -> None:
        """A figure not present in the retrieved source is dropped from the answer."""
        provider = _RecordingProvider(
            "The model reaches 77.29% accuracy and 99.99% on internal tests."
        )
        p = self._make_pipeline(provider)
        result = p._generic_one_shot(
            "Summarize chapter 18", top_k=5, show_sources=False
        )
        assert "77.29" in result["answer"], "source-present figure must survive"
        assert "99.99" not in result["answer"], "fabricated figure must be removed"

    def test_summary_intent_reinforces_exact_quoting_in_prompt(self) -> None:
        """Chapter/section summaries get the exact-quote instruction injected."""
        provider = _RecordingProvider("A grounded answer about the chapter.")
        p = self._make_pipeline(provider)
        p._generic_one_shot("Summarize chapter 18", top_k=5, show_sources=False)
        assert "Quote figures" in provider.last_prompt
        assert "function arguments" in provider.last_prompt

    def test_regenerates_when_answer_leaks_self_correction(self) -> None:
        """A mid-prose '...? Actually, ...' leak triggers a clean low-temp retry."""
        leaky = (
            "over windows 15 to 30? Actually, the model reaches 77.29 percent. "
            "This is a confident claim about the source."
        )
        clean = (
            "The DenseNet model reaches 77.29 percent accuracy, well below "
            "expectations in this regime."
        )
        calls: list[tuple[float, str]] = []

        class _Seq(_RecordingProvider):
            def generate(
                self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
            ) -> str:
                self.last_prompt = prompt
                calls.append((temperature, prompt))
                return leaky if len(calls) == 1 else clean

        p = self._make_pipeline(_Seq(clean))
        result = p._generic_one_shot(
            "Summarize chapter 18", top_k=5, show_sources=False
        )

        assert len(calls) == 2, "leaky first pass should trigger a regeneration"
        assert calls[1][0] == 0.1, "retry runs at the low guarded temperature"
        assert "Actually," not in result["answer"], "leak scaffolding must be gone"
        assert "77.29" in result["answer"], "clean retry figure must survive grounding"

    def test_regenerates_when_stuck_fallback_returns(self) -> None:
        """A provider stuck-reasoning fallback (no content) gets a clean retry."""
        fallback = (
            "I got stuck in repetitive reasoning and could not "
            "produce an answer. Please rephrase or narrow your question."
        )
        clean = "The DenseNet model reaches 77.29 percent accuracy on the benchmark."
        calls: list[tuple[float, str]] = []

        class _Seq(_RecordingProvider):
            def generate(
                self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
            ) -> str:
                self.last_prompt = prompt
                calls.append((temperature, prompt))
                return fallback if len(calls) == 1 else clean

        p = self._make_pipeline(_Seq(clean))
        result = p._generic_one_shot(
            "Summarize chapter 18", top_k=5, show_sources=False
        )

        assert len(calls) == 2, "stuck fallback should trigger a regeneration"
        assert calls[1][0] == 0.1, "retry runs at the low guarded temperature"
        assert "I got stuck" not in result["answer"], "dead-end fallback must not ship"
        assert "77.29" in result["answer"], "clean retry figure must survive grounding"

    def test_summary_path_is_non_streaming(self) -> None:
        """Chapter summaries generate non-streaming and emit the vetted result once."""
        provider = _DualProvider("A grounded summary with 77.29 percent accuracy.")
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        emitted: list[str] = []
        p._on_chunk = lambda content, reason: emitted.append(content or "")
        result = p._generic_one_shot(
            "Summarize chapter 18", top_k=5, show_sources=False
        )

        assert provider.stream_chat_called is False, "summary must NOT live-stream raw"
        assert emitted == [result["answer"]], (
            "vetted answer emitted once, not the draft"
        )
        assert "77.29" in result["answer"]

    def test_non_summary_path_streams(self) -> None:
        """Non-summary queries keep live streaming."""
        provider = _DualProvider("a" * 60)
        p = self._make_pipeline(provider)
        p._config.streaming_enabled = True
        p._on_chunk = lambda content, reason: None
        p._generic_one_shot("What is a hyperparameter?", top_k=5, show_sources=False)

        assert provider.stream_chat_called is True, "non-summary should live-stream"


class _DualProvider(_RecordingProvider):
    """Records whether live streaming (stream_chat) is invoked vs plain generate."""

    def __init__(self, answer: str) -> None:
        super().__init__(answer)
        self.stream_chat_called = False

    def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        on_chunk: Callable[[str, Any | None], None],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        self.stream_chat_called = True
        return ""
