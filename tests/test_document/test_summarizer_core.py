"""Unit tests for Summarizer core helpers: budgeting, windowing, guard."""

from __future__ import annotations

import pytest

from secondbrain.document.summarizer import (
    ChapterSummary,
    SectionSummary,
    Summarizer,
)


class _RecordingProvider:
    """Records every agenerate call; returns scripted responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def agenerate(self, prompt, temperature, max_tokens):
        self.calls.append(
            {"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}
        )
        if self.responses:
            return self.responses.pop(0)
        return f"summary for call {len(self.calls)}"


class _MockEmbedder:
    """Minimal embedder returning a fixed 8-dim vector."""

    def generate(self, text):
        return [0.1] * 8


class _MockStorage:
    def find_chunks(self, *args, **kwargs):
        return []


def _summarizer(provider, **kwargs):
    return Summarizer(
        llm_provider=provider,
        embedder=_MockEmbedder(),
        storage=_MockStorage(),
        **kwargs,
    )


PLAUSIBLE = (
    "This chapter introduces convolutional neural networks and explains how "
    "they model grid-like data such as images and financial time series."
)


class TestTokenBudget:
    def test_zero_chunks_returns_zero(self) -> None:
        assert Summarizer._token_budget_for(0, 100) == 0
        assert Summarizer._token_budget_for(-3, 100) == 0

    @pytest.mark.parametrize(
        ("n_chunks", "budget", "expected"),
        [(1, 10, 10), (2, 10, 5), (3, 10, 4), (4, 10, 3), (7, 10, 2)],
    )
    def test_even_distribution_with_remainder(self, n_chunks, budget, expected) -> None:
        assert Summarizer._token_budget_for(n_chunks, budget) == expected


class TestFitsInBudget:
    def test_boundary_equal_budget_fits(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=8)
        assert s._fits_in_budget(["abcd", "efgh"]) is True

    def test_one_char_over_budget_does_not_fit(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=8)
        assert s._fits_in_budget(["abcd", "efghi"]) is False

    def test_empty_list_fits(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=1)
        assert s._fits_in_budget([]) is True


class TestWindowExcerpts:
    def test_over_budget_excerpts_split_into_windows(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=10)
        windows = s._window_excerpts(["aaaaa", "bbbbbbbbbb", "cc", "dd"])
        # First window holds [aaaaa] (5); adding the 10-char excerpt would hit
        # 15 > 10, so it starts a new window; then cc+dd (4) fit in window 3.
        assert windows == [["aaaaa"], ["bbbbbbbbbb"], ["cc", "dd"]]
        for window in windows:
            assert sum(len(t) for t in window) <= 10

    def test_each_window_within_budget(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=15)
        excerpts = ["x" * 10, "y" * 10, "z" * 10, "w" * 5]
        windows = s._window_excerpts(excerpts)
        assert all(sum(len(t) for t in w) <= 15 for w in windows)
        # Greedy packing: 10 | 10 | 10+5 = 3 windows.
        assert len(windows) == 3

    def test_window_cap_drops_trailing_excerpts(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=10, max_windows=2)
        excerpts = ["a" * 10] * 10
        windows = s._window_excerpts(excerpts)
        assert len(windows) <= 2
        total_kept = sum(len(t) for w in windows for t in w)
        assert total_kept <= 10 * 2  # hard budget respected

    def test_empty_excerpts_produce_single_empty_window(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=100)
        windows = s._window_excerpts([])
        # Empty input: the greedy loop appends nothing, so no window at all.
        assert windows == []

    def test_single_excerpt_within_budget_stays_one_window(self) -> None:
        s = _summarizer(_RecordingProvider([]), max_input_chars=100)
        assert s._window_excerpts(["hello"]) == [["hello"]]


class TestEmptyChunkEarlyReturn:
    @pytest.mark.asyncio
    async def test_summarize_by_chapter_empty_chunks(self) -> None:
        provider = _RecordingProvider(["should not be called"])
        s = _summarizer(provider)
        result = await s.summarize_by_chapter(4)
        assert isinstance(result, ChapterSummary)
        assert result.summary == ""
        assert result.chunk_count == 0
        assert result.token_budget_used == 0
        assert result.chapter_id == 4
        assert result.chapter_title == "Chapter 4"
        assert provider.calls == []

    @pytest.mark.asyncio
    async def test_summarize_by_section_empty_chunks(self) -> None:
        provider = _RecordingProvider(["should not be called"])
        s = _summarizer(provider)
        result = await s.summarize_by_section("7.2")
        assert isinstance(result, SectionSummary)
        assert result.summary == ""
        assert result.section_id == "7.2"
        assert result.section_title == "Section 7.2"
        assert result.belongs_to_chapter == 7
        assert result.token_budget_used == 0
        assert provider.calls == []

    @pytest.mark.asyncio
    async def test_summarize_by_section_non_numeric_prefix(self) -> None:
        provider = _RecordingProvider([])
        s = _summarizer(provider)
        result = await s.summarize_by_section("appendix.intro")
        assert result.belongs_to_chapter == 0
        assert result.summary == ""

    @pytest.mark.asyncio
    async def test_stream_summaries_yields_each_chapter(self) -> None:
        provider = _RecordingProvider([])
        s = _summarizer(provider)
        collected = [c async for c in s.stream_summaries([1, 2])]
        assert [c.chapter_id for c in collected] == [1, 2]
        assert all(c.summary == "" for c in collected)


class TestGenerateWithGuard:
    @pytest.mark.asyncio
    async def test_retry_once_on_degenerate_output(self) -> None:
        degenerate = "la la la la la la la la la la la la la la la la la la"
        provider = _RecordingProvider([degenerate, PLAUSIBLE])
        s = _summarizer(provider, max_input_chars=1000)
        result = await s._generate_with_guard("prompt")
        assert result == PLAUSIBLE
        assert len(provider.calls) == 2
        assert provider.calls[0]["temperature"] == 0.5
        assert provider.calls[1]["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_returns_empty_when_retry_still_implausible(self) -> None:
        provider = _RecordingProvider(
            ["garbage garbage garbage garbage garbage", PLAUSIBLE[:10]]
        )
        s = _summarizer(provider, max_input_chars=1000)
        result = await s._generate_with_guard("prompt")
        assert result == ""
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_plausible_first_response_skips_retry(self) -> None:
        provider = _RecordingProvider([PLAUSIBLE])
        s = _summarizer(provider, max_input_chars=1000)
        result = await s._generate_with_guard("prompt")
        assert result == PLAUSIBLE
        assert len(provider.calls) == 1
        assert provider.calls[0]["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_max_tokens_forwarded_to_provider(self) -> None:
        provider = _RecordingProvider([PLAUSIBLE])
        s = _summarizer(provider, max_summary_tokens=321)
        await s._generate_with_guard("prompt")
        assert provider.calls[0]["max_tokens"] == 321
