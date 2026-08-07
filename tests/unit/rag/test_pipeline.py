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
    """Broad-coverage query with no detected chapters and no chapter target
    must fall through to generic search rather than error on a chapter."""

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
