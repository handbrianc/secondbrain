"""Tests for the Summarizer context-budget guards (map-reduce + plausibility)."""

from __future__ import annotations

from secondbrain.document.summarizer import PARTIAL_COVERAGE_NOTE, Summarizer


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


def _marker_excerpts(count: int, size: int, prefix: str) -> list[str]:
    """*count* distinct size-pinned excerpts tagged ``{prefix}00``… in order."""
    texts = []
    for i in range(count):
        tag = f"{prefix}{i:02d} "
        texts.append(tag + "x" * (size - len(tag)))
    return texts


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
    # Beyond-cap sources are evenly sampled (first and last kept) rather
    # than head-truncated to satisfy the cap.
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


# ----------------------------------------------------------------------
# Full-source coverage within the window cap (design D4)
# ----------------------------------------------------------------------


async def test_plan_windows_full_coverage_covers_every_excerpt() -> None:
    # 10 x 40 = 400 chars: above the 100-char single-call budget yet within
    # the 4 x 100 window budget. Default greedy packing wastes 20 chars at
    # each boundary (5 windows), so the adaptive re-pack must fit the whole
    # sequence into the 4-window cap instead of dropping trailing excerpts.
    s = _summarizer(_RecordingProvider([]), max_input_chars=100, max_windows=4)
    excerpts = _marker_excerpts(10, 40, "sec")
    windows, partial = s._plan_windows(excerpts)
    assert partial is False
    assert len(windows) <= 4
    # Full coverage, in document order: no excerpt is dropped.
    assert [e for window in windows for e in window] == excerpts


async def test_plan_windows_empty_excerpts_yields_no_windows() -> None:
    s = _summarizer(_RecordingProvider([]), max_input_chars=100, max_windows=4)
    assert s._plan_windows([]) == ([], False)
    assert s._window_excerpts([]) == []


async def test_summarize_oversized_source_merges_late_sections() -> None:
    provider = _RecordingProvider(
        [
            "First window covers the early sections sec00 and sec01 material.",
            "Second window covers the middle sections sec03 and sec04 material.",
            "Third window covers the later sections sec06 and sec07 material.",
            "Fourth window covers the final section sec09 of the document.",
            "Merged summary folding all four windows into one complete story.",
        ]
    )
    s = _summarizer(provider, max_input_chars=100, max_windows=4)
    chunks = [_chunk(text) for text in _marker_excerpts(10, 40, "sec")]
    result = await s._summarize(chunks, "context")
    # Four window digests + one merge fold, still within the window cap.
    assert len(provider.calls) == 5
    # The final excerpt reaches an LLM call instead of being dropped.
    assert "sec09" in provider.calls[3]["prompt"]
    # The merged summary draws on the late sections as well.
    assert "final section sec09" in provider.calls[4]["prompt"]
    assert result == "Merged summary folding all four windows into one complete story."
    assert PARTIAL_COVERAGE_NOTE not in result


async def test_plan_windows_beyond_cap_samples_evenly() -> None:
    # 10 x 60 = 600 chars against a 2 x 100 = 200-char window budget: full
    # coverage is impossible, so the planner samples evenly across the whole
    # sequence instead of head-truncating.
    s = _summarizer(_RecordingProvider([]), max_input_chars=100, max_windows=2)
    excerpts = _marker_excerpts(10, 60, "part")
    windows, partial = s._plan_windows(excerpts)
    assert partial is True
    assert len(windows) <= 2
    sampled = [e for window in windows for e in window]
    assert sampled[0] == excerpts[0]
    assert sampled[-1] == excerpts[-1]
    # The sample is sized to fit the window budget.
    assert sum(len(e) for e in sampled) <= 2 * 100
    # The sample spans the whole sequence, not just its head.
    assert set(excerpts[3:7]) & set(sampled)
    assert set(sampled) != set(excerpts)


async def test_summarize_beyond_cap_prepends_partial_note() -> None:
    merge_text = "Merged summary of the evenly spread sample covering the source."
    provider = _RecordingProvider(
        [
            "First partial describes the opening of the sampled document span.",
            "Last partial describes the closing of the sampled document span.",
            merge_text,
        ]
    )
    s = _summarizer(provider, max_input_chars=100, max_windows=2)
    chunks = [_chunk(text) for text in _marker_excerpts(10, 60, "part")]
    result = await s._summarize(chunks, "context")
    # Two sampled windows + one merge fold, within the window cap.
    assert len(provider.calls) == 3
    # First and last excerpts survive the sample; the middle band is spread.
    assert "part00" in provider.calls[0]["prompt"]
    assert "part05" in provider.calls[0]["prompt"]
    assert "part09" in provider.calls[1]["prompt"]
    assert result == f"{PARTIAL_COVERAGE_NOTE}\n\n{merge_text}"
    # The note is display-level: it is never fed back into a prompt.
    assert PARTIAL_COVERAGE_NOTE not in provider.calls[2]["prompt"]


async def test_summarize_full_coverage_has_no_note() -> None:
    # 6 x 40 = 240 chars against a 4 x 100 budget: plain greedy packing (3
    # windows) covers the source completely, so nothing may disclose
    # partiality anywhere in the output or the prompts.
    merge_text = "Merged summary covering every section of the source completely."
    provider = _RecordingProvider(
        [
            "First window covers the opening sections of the source document.",
            "Second window covers the middle sections of the source document.",
            "Third window covers the closing sections of the source document.",
            merge_text,
        ]
    )
    s = _summarizer(provider, max_input_chars=100, max_windows=4)
    chunks = [_chunk(text) for text in _marker_excerpts(6, 40, "sec")]
    result = await s._summarize(chunks, "context")
    assert len(provider.calls) == 4
    assert result == merge_text
    assert PARTIAL_COVERAGE_NOTE not in result
    for call in provider.calls:
        assert PARTIAL_COVERAGE_NOTE not in call["prompt"]
