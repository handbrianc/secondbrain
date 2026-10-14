"""Behavioral tests for the RAG pipeline streaming-guard machinery.

Covers the live-streaming windows of ``_FallbackMixin`` (map-reduce window
generation, digest mapping, reduce-overview streaming, low-temperature
retries) with hand-rolled provider doubles that stream scripted chunks —
the same in-repo double style as ``tests/unit/rag/test_pipeline.py``, no
MagicMock at the domain layer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any
from unittest.mock import MagicMock

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._mixins import _StreamAbortError


class _StreamedProvider:
    """Provider double streaming scripted (content, reasoning) chunks.

    ``script`` is a list of ``(content, reasoning)`` tuples replayed through
    ``on_chunk``; ``stream_raise`` raises after the script is streamed to
    simulate a stream that dies mid-flight. ``generate_responses`` backs the
    non-streaming ``generate`` used by retries.
    """

    def __init__(
        self,
        script: Sequence[tuple[str, str | None]] = (),
        *,
        stream_raise: type[Exception] | None = None,
        stream_raise_calls: int | None = None,
        generate_responses: Sequence[str] = (),
        stream_scripts: Sequence[Sequence[tuple[str, str | None]]] | None = None,
    ) -> None:
        self.script = list(script)
        self.stream_raise = stream_raise
        self.stream_raise_calls = stream_raise_calls
        self.generate_responses = list(generate_responses)
        self.stream_scripts = (
            list(stream_scripts) if stream_scripts is not None else None
        )
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self._stream_calls_made = 0

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.generate_calls.append(
            {"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}
        )
        if self.generate_responses:
            return self.generate_responses.pop(0)
        if "Classify each of the following document headings" in prompt:
            return "NONE"
        return "retry generated answer"

    async def agenerate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return self.generate(prompt, temperature, max_tokens)

    def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        on_chunk: Callable[[str, str | None], None],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        self._stream_calls_made += 1
        self.stream_calls.append(
            {
                "prompt": messages[-1]["content"] if messages else "",
                "temperature": temperature,
            }
        )
        if self.stream_scripts is not None:
            current = list(self.stream_scripts.pop(0)) if self.stream_scripts else []
        else:
            current = self.script
        for content, reasoning in current:
            on_chunk(content, reasoning)
        if self.stream_raise is not None and (
            self.stream_raise_calls is None
            or self._stream_calls_made <= self.stream_raise_calls
        ):
            raise self.stream_raise("stream aborted mid-flight")
        return "".join(content for content, _ in current if content)


def _make_pipeline(
    provider: Any, on_chunk: Callable[[str, str | None], None] | None = None
) -> RAGPipeline:
    searcher = MagicMock()
    searcher.search.return_value = [
        {"chunk_text": "Some relevant context", "source_file": "a.pdf", "page": 1}
    ]
    pipeline = RAGPipeline(
        searcher=searcher,
        llm_provider=provider,  # type: ignore[arg-type]
        top_k=5,
        on_chunk=on_chunk,
    )
    pipeline._config.streaming_enabled = True
    return pipeline


class _CallbackCapture:
    """Streaming-callback double recording (content, reasoning) tuples."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, content: str, reasoning: str | None) -> None:
        self.calls.append((content, reasoning))

    @property
    def text(self) -> str:
        return "".join(c for c, _ in self.calls if c)


_PLAUSIBLE = (
    "This chapter explains the retrieval pipeline in careful detail. "
    "It covers embedding queries, ranking candidates, and trimming context. "
    "Each idea is presented once with a short example and no repetition. "
    "The closing paragraph ties the workflow together cleanly."
)


class TestGenerateWindowGuardedStreaming:
    """Streaming window generation: heading emit, guards, and retries."""

    def test_streams_heading_and_content_to_callback(self) -> None:
        provider = _StreamedProvider(
            [
                ("This window explains the retrieval flow in careful detail. ", None),
                (
                    "It covers embedding queries, ranking candidates, and context trimming.",
                    None,
                ),
            ]
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## Heading")
        assert answer == (
            "This window explains the retrieval flow in careful detail. "
            "It covers embedding queries, ranking candidates, and context trimming."
        )
        assert capture.calls[0] == ("## Heading\n\n", None)
        assert "".join(c for c, _ in capture.calls[1:]) == answer

    def test_reasoning_is_consumed_not_forwarded(self) -> None:
        provider = _StreamedProvider(
            [
                (
                    "The answer explains ranking and context trimming in careful detail "
                    "with a short example.",
                    "thinking hard",
                )
            ]
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert "The answer explains ranking and context trimming" in answer
        assert all("thinking hard" not in c for c, _ in capture.calls)

    def test_flood_guard_aborts_and_retries_low_temp(self) -> None:
        # >400 chars of repetition trips _is_flooding mid-stream.
        spam = ("garbage " * 80).strip()
        provider = _StreamedProvider([(spam, None)], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        # The retry regenerated at temperature 0.1 and replaced the partial.
        assert answer == _PLAUSIBLE
        assert len(provider.generate_calls) == 1
        assert provider.generate_calls[0]["temperature"] == 0.1
        # The derailed tail was never streamed; the retry answer was.
        assert "garbage" not in capture.text
        assert _PLAUSIBLE in capture.text

    def test_content_self_correction_aborts_stream(self) -> None:
        prefix = "A clean and informative summary sentence. "
        provider = _StreamedProvider(
            [(prefix + "?? (wait, the text says something else)", None)],
            generate_responses=[_PLAUSIBLE],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert answer == _PLAUSIBLE

    def test_reasoning_budget_fallback_prefix_aborts(self) -> None:
        from secondbrain.rag.pipeline._mixins import _REASONING_BUDGET_FALLBACK_PREFIX

        provider = _StreamedProvider(
            [(_REASONING_BUDGET_FALLBACK_PREFIX + " stuck", None)],
            generate_responses=[_PLAUSIBLE],
        )
        pipeline = _make_pipeline(provider, on_chunk=_CallbackCapture())
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert answer == _PLAUSIBLE

    def test_stream_exception_triggers_low_temp_retry(self) -> None:
        provider = _StreamedProvider(
            [("Some partial content. ", None)],
            stream_raise=RuntimeError,
            generate_responses=[_PLAUSIBLE],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert answer == _PLAUSIBLE

    def test_completed_window_word_salad_gets_low_temp_retry(self) -> None:
        # High-diversity salad passes the flood guard but fails the completed-
        # window word-salad check, so a low-temperature retry regenerates.
        salad = (
            "zebra giraffe trampoline sapphire bakelite vertebra compass harbor "
            "syringe enamel abacus scaffold pilgrim turbine torrent sampler "
            "beetle carnival monograph espresso necklace paradigm kettle octopus "
            "verdict meadow glacier bundle flask compartment lantern gyroscope "
            "basketball garrison numeral meridian splinter reassembly soil "
            "oracle basin quiver anvil badger cilantro donkey eclipse falcon "
            "granite hedgehog iguana jasmine kayak lagoon magnolia narwhal."
        )
        provider = _StreamedProvider([(salad, None)], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert answer == _PLAUSIBLE

    def test_retry_unusable_returns_empty(self) -> None:
        provider = _StreamedProvider(
            [(("garbage " * 80).strip(), None)],
            generate_responses=["garbage garbage garbage garbage"],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert pipeline._generate_window_guarded("prompt", "## H") == ""

    def test_retry_failure_returns_clean_prefix(self) -> None:
        prefix = (
            "This chapter explains the retrieval pipeline in careful detail, "
            "covering embedding queries and candidate ranking with short examples."
        )
        provider = _StreamedProvider(
            [(prefix, None)],
            stream_raise=RuntimeError,
            generate_responses=[],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        # The retry failed too; the streamed clean prefix is kept.
        assert "retrieval pipeline in careful detail" in answer
        assert "retrieval pipeline in careful detail" in capture.text

    def test_retry_stream_leak_skips_window(self) -> None:
        leaky = (
            "A figure of 48? no, the correct value is 45.78 percent overall here "
            "with plenty of additional prose to keep the summary readable."
        )
        provider = _StreamedProvider(
            [((("garbage " * 80).strip()), None)],
            generate_responses=[leaky],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "## H")
        # The retry leaked a self-correction: skipped; the derailed partial
        # is unusable, so the window ships nothing.
        assert answer == ""
        assert "45.78" not in capture.text

    def test_non_streaming_fallback_emits_once(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        capture = _CallbackCapture()
        pipeline._on_chunk = capture
        answer = pipeline._generate_window_guarded("prompt", "## H")
        assert answer == _PLAUSIBLE
        assert capture.calls == [(f"## H\n\n{_PLAUSIBLE}\n\n", None)]


class TestMapReduceStream:
    """Fan-out over window prompts, concatenating guarded results."""

    def test_concatenates_window_summaries_in_order(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        pipeline._generate_window_guarded = (  # type: ignore[method-assign]
            lambda prompt, heading, temperature=None: f"{heading} body"
        )
        result = pipeline._map_reduce_stream(
            [("H1", "p1"), ("H2", "p2")], temperature=0.3
        )
        assert result == "H1\nH1 body\n\nH2\nH2 body"

    def test_skips_empty_windows(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        pipeline._generate_window_guarded = (  # type: ignore[method-assign]
            lambda prompt, heading, temperature=None: (
                "content" if heading == "H1" else ""
            )
        )
        result = pipeline._map_reduce_stream([("H1", "p1"), ("H2", "p2")])
        assert result == "H1\ncontent"
        assert "" not in result.split("\n")

    def test_empty_items_return_empty(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert pipeline._map_reduce_stream([]) == ""


class TestLowTempRetry:
    """Direct coverage of the low-temperature retry contract."""

    def test_acceptable_retry_streamed_with_heading(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        result = pipeline._low_temp_retry("prompt", False, "## H", max_tokens=512)
        assert result == _PLAUSIBLE
        assert provider.generate_calls[0]["temperature"] == 0.1
        assert provider.generate_calls[0]["max_tokens"] == 512
        # Heading was not shown yet, so the retry emits heading + answer.
        assert capture.calls == [(f"## H\n\n{_PLAUSIBLE}\n\n", None)]

    def test_acceptable_retry_heading_shown_emits_answer_only(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        result = pipeline._low_temp_retry("prompt", True, "## H", max_tokens=512)
        assert result == _PLAUSIBLE
        assert capture.calls == [(f"\n\n{_PLAUSIBLE}\n\n", None)]

    def test_generate_failure_returns_none(self, caplog) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)

        def _boom(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
            raise RuntimeError("provider down")

        provider.generate = _boom  # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING):
            result = pipeline._low_temp_retry("prompt", False, "## H", max_tokens=512)
        assert result is None
        assert any("retry failed" in r.message for r in caplog.records)

    def test_leaked_retry_returns_none(self, caplog) -> None:
        leaky = (
            "A draft that second-guesses itself. ?? (wait, the text says the "
            "source claims 42 percent, correct to 40 percent)"
        )
        provider = _StreamedProvider([], generate_responses=[leaky])
        pipeline = _make_pipeline(provider, on_chunk=None)
        with caplog.at_level(logging.WARNING):
            result = pipeline._low_temp_retry("prompt", False, "## H", max_tokens=512)
        assert result is None

    def test_unacceptable_retry_returns_none(self) -> None:
        provider = _StreamedProvider(
            [], generate_responses=["garbage garbage garbage garbage garbage"]
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert pipeline._low_temp_retry("prompt", False, "## H", max_tokens=512) is None


class TestStreamAbortError:
    """The abort sentinel is a plain exception raised by the flood guard."""

    def test_abort_error_is_an_exception(self) -> None:
        assert isinstance(_StreamAbortError(), Exception)
