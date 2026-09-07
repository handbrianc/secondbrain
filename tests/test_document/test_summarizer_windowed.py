"""Tests for the Summarizer context-budget guards (map-reduce + plausibility)."""

from __future__ import annotations

from secondbrain.document.summarizer import Summarizer


class _RecordingProvider:
    """Records every agenerate call; returns scripted responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def agenerate(self, prompt: str, temperature: float, max_tokens: int) -> str:
        self.calls.append(
            {"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}
        )
        if self.responses:
            return self.responses.pop(0)
        return f"summary for call {len(self.calls)}"


class _MockEmbedder:
    pass


class _MockStorage:
    def find_chunks(self, *args, **kwargs):
        return []


def _chunk(text: str) -> dict:
    return {
        "chunk_id": "c1",
        "chunk_role": "body",
        "chunk_text": text,
        "source_file": "b.pdf",
    }


def _summarizer(provider: _RecordingProvider, **kwargs) -> Summarizer:
    return Summarizer(
        llm_provider=provider,
        embedder=_MockEmbedder(),
        storage=_MockStorage(),
        **kwargs,
    )


def _plausible(text: str) -> str:
    return text


async def test_fits_in_budget_true_below_limit() -> None:
    s = _summarizer(_RecordingProvider([]), max_input_chars=1000)
    assert s._fits_in_budget(["abcd", "efgh"])


async def test_fits_in_budget_false_above_limit() -> None:
    s = _summarizer(_RecordingProvider([]), max_input_chars=5)
    assert not s._fits_in_budget(["abcd", "efgh"])


PLAUSIBLE = (
    "This chapter introduces convolutional neural networks and explains how "
    "they model grid-like data such as images and financial time series."
)


async def test_single_call_when_input_fits_budget() -> None:
    provider = _RecordingProvider([PLAUSIBLE])
    s = _summarizer(provider, max_input_chars=1000)
    result = await s._summarize([_chunk("short text")], "context")
    assert result == PLAUSIBLE
    assert len(provider.calls) == 1
    assert provider.calls[0]["temperature"] == 0.5


async def test_map_reduce_when_input_exceeds_budget() -> None:
    provider = _RecordingProvider(
        [
            "First partial summary of the first window covering its main ideas.",
            "Second partial summary of the second window covering its main ideas.",
            "Combined summary folding both partials into one coherent overview.",
        ]
    )
    s = _summarizer(provider, max_input_chars=30, max_windows=8)
    chunks = [_chunk("a" * 40), _chunk("b" * 40)]
    result = await s._summarize(chunks, "context")
    assert result == (
        "Combined summary folding both partials into one coherent overview."
    )
    # Two window summaries + one merge fold.
    assert len(provider.calls) == 3
    # Merge prompt carries both partials.
    merge_prompt = provider.calls[2]["prompt"]
    assert "First partial summary" in merge_prompt
    assert "Second partial summary" in merge_prompt
    assert "Combined Summary" in merge_prompt


async def test_window_excerpts_caps_number_of_windows() -> None:
    s = _summarizer(_RecordingProvider([]), max_input_chars=10, max_windows=2)
    excerpts = ["x" * 10] * 100
    windows = s._window_excerpts(excerpts)
    assert len(windows) <= 2
    # Truncation drops trailing excerpts rather than exceeding the cap.
    assert len(windows) >= 1


async def test_guard_retries_once_on_implausible_first_response() -> None:
    # First response is repetitive token-soup; retry is plausible.
    provider = _RecordingProvider(
        [
            "la la la la la la la la la la la la la la la la la la la la",
            PLAUSIBLE,
        ]
    )
    s = _summarizer(provider, max_input_chars=1000)
    result = await s._summarize([_chunk("text")], "context")
    assert result == PLAUSIBLE
    assert len(provider.calls) == 2
    assert provider.calls[1]["temperature"] == 0.1


async def test_guard_returns_empty_when_retry_still_implausible() -> None:
    provider = _RecordingProvider(
        [
            "garbage garbage garbage garbage garbage garbage garbage",
            "more garbage more garbage more garbage more garbage more garbage",
        ]
    )
    s = _summarizer(provider, max_input_chars=1000)
    result = await s._summarize([_chunk("text")], "context")
    assert result == ""
    assert len(provider.calls) == 2


def test_is_plausible_summary_rejects_short_and_repetitive() -> None:
    s = _summarizer(_RecordingProvider([]))
    assert s._is_plausible_summary(
        "This is a normal detailed summary with varied words."
    )
    assert not s._is_plausible_summary("hi")
    assert not s._is_plausible_summary("aaaa aaaa aaaa aaaa aaaa aaaa aaaa")


def test_extract_excerpts_skips_empty_text() -> None:
    s = _summarizer(_RecordingProvider([]))
    chunks = [_chunk("hello"), {"chunk_id": "x", "chunk_text": ""}, _chunk("world")]
    assert s._extract_excerpts(chunks) == ["hello", "world"]


async def test_summarize_returns_empty_when_no_excerpts() -> None:
    provider = _RecordingProvider(["should not be called"])
    s = _summarizer(provider, max_input_chars=1000)
    result = await s._summarize([{"chunk_id": "x", "chunk_text": ""}], "context")
    assert result == ""
    assert provider.calls == []


async def test_map_reduce_single_partial_passthrough() -> None:
    # If only one window has content, no merge fold is emitted.
    provider = _RecordingProvider([PLAUSIBLE])
    s = _summarizer(provider, max_input_chars=30, max_windows=8)
    result = await s._summarize([_chunk("z" * 40)], "context")
    assert result == PLAUSIBLE
    assert len(provider.calls) == 1
