"""Behavioral tests for the RAG overview digest/reduce streaming machinery.

Targets ``_summarize_bounded``, ``_map_window_digest``,
``_reduce_digest_overview``, ``_condense_digest_group``, ``_resume_summary``
and ``_finalize_or_retry_overview`` — the map-reduce overview path with its
leak-scrub hold buffer, dead-stream continuation, and degenerate-output
regeneration — using the scripted provider doubles from
``test_pipeline_streaming_guards``.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from tests.unit.rag.test_pipeline_streaming_guards import (
    _CallbackCapture,
    _make_pipeline,
    _StreamedProvider,
)

_PLAUSIBLE = (
    "The overview explains the retrieval pipeline in careful detail here. "
    "It covers embedding queries, ranking candidates, and trimming context. "
    "Each idea appears once with a short example and no repetition at all. "
    "The closing paragraph ties the workflow together cleanly for readers."
)


class TestSummarizeBounded:
    """Single-pass vs map-reduce dispatch in _summarize_bounded."""

    def _chunk(self, text: str) -> dict[str, Any]:
        return {"chunk_text": text, "source_file": "a.pdf", "page": 1}

    def _oversized_window(self) -> list[dict[str, Any]]:
        """One window whose formatted context exceeds _SINGLE_PASS_MAX_CHARS."""
        text = "source body prose " * 80  # truncated to ~1200 chars per chunk
        return [self._chunk(text) for _ in range(300)]

    def test_no_formatted_context_returns_empty(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        # Empty windows format to nothing -> no contexts -> "".
        assert (
            pipeline._summarize_bounded(
                heading="H", windows=[[]], instruction="Write an overview."
            )
            == ""
        )

    def test_single_pass_within_budget_skips_map_stage(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        answer = pipeline._summarize_bounded(
            heading="Chapter 1 — Intro",
            windows=[[self._chunk("Some source body text for the overview.")]],
            instruction="Write an overview.",
        )
        assert answer == _PLAUSIBLE
        # Exactly one generate call: the reduce, no per-window digest calls.
        assert len(provider.generate_calls) == 1
        assert "Some source body text" in provider.generate_calls[0]["prompt"]

    def test_oversized_source_uses_map_reduce(self) -> None:
        provider = _StreamedProvider(
            [],
            generate_responses=[
                "A terse digest of the oversized part covering its topics in "
                "order with figures preserved exactly as the source states.",
                _PLAUSIBLE,
            ],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        # One window formats past the single-pass budget, so the map stage
        # condenses it first and the reduce writes the overview from digests.
        pipeline._config.rag_max_context_chars = 400_000
        answer = pipeline._summarize_bounded(
            heading="Chapter 1 — Intro",
            windows=[self._oversized_window()],
            instruction="Write an overview.",
        )
        assert answer == _PLAUSIBLE
        assert len(provider.generate_calls) == 2
        # The map digest prompt identifies Part 1 of 1; the reduce consumes it.
        assert "Part 1 of 1" in provider.generate_calls[0]["prompt"]
        assert "terse digests" in provider.generate_calls[1]["prompt"]

    def test_digest_failure_skips_window(self, caplog) -> None:
        provider = _StreamedProvider([(("garbage " * 60).strip(), None)])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.rag_max_context_chars = 400_000
        with caplog.at_level(logging.WARNING):
            answer = pipeline._summarize_bounded(
                heading="Chapter 1 — Intro",
                windows=[self._oversized_window()],
                instruction="Write an overview.",
            )
        # The streamed digest was implausible: no digests survive, so the
        # overview is abandoned before the reduce runs.
        assert answer == ""
        assert provider.generate_calls == []
        assert any("unusable; skipping" in r.message for r in caplog.records)


class TestMapWindowDigest:
    """Digest generation: stream preference, failure regeneration, validation."""

    def test_stream_failure_falls_back_to_generate_guarded(self, caplog) -> None:
        provider = _StreamedProvider(
            [("A digest paragraph covering retrieval topics with some detail.", None)],
            stream_raise=RuntimeError,
            generate_responses=[
                "A regenerated digest paragraph covering the retrieval topics "
                "in detail, mentioning every figure exactly once, thoroughly."
            ],
        )
        pipeline = _make_pipeline(provider, on_chunk=_CallbackCapture())
        with caplog.at_level(logging.WARNING):
            digest = pipeline._map_window_digest("Chapter 1", "source ctx", 1, 2)
        assert "regenerated digest paragraph" in digest
        assert len(provider.generate_calls) == 1
        assert any("regenerating" in r.message for r in caplog.records)

    def test_unplausible_digest_skipped_with_warning(self, caplog) -> None:
        provider = _StreamedProvider([(("garbage " * 60).strip(), None)])
        pipeline = _make_pipeline(provider, on_chunk=None)
        with caplog.at_level(logging.WARNING):
            digest = pipeline._map_window_digest("Chapter 1", "source ctx", 1, 2)
        assert digest == ""
        # The streamed digest was non-empty but fails the plausibility gate.
        assert provider.generate_calls == []
        assert any("unusable; skipping" in r.message for r in caplog.records)

    def test_digest_generation_error_returns_empty(self, caplog) -> None:
        provider = _StreamedProvider([], generate_responses=[])

        def _boom(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
            raise RuntimeError("provider down")

        provider.generate = _boom  # type: ignore[method-assign]
        pipeline = _make_pipeline(provider, on_chunk=None)
        with caplog.at_level(logging.WARNING):
            digest = pipeline._map_window_digest("Chapter 1", "source ctx", 1, 2)
        assert digest == ""
        assert any("skipping part" in r.message for r in caplog.records)

    def test_valid_digest_is_scrubbed_and_trimmed(self) -> None:
        provider = _StreamedProvider(
            [],
            generate_responses=[
                "A digest of the chapter covering retrieval topics in careful "
                "detail with figures and examples throughout the whole text."
            ],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        digest = pipeline._map_window_digest(
            "Chapter 1", "the source mentions 42 percent", 1, 1
        )
        assert "digest of the chapter" in digest
        assert digest.endswith(("!", "?", "."))


class TestReduceDigestOverviewNonStreaming:
    """Non-streaming reduce path: guarded generation + finalize."""

    def test_generates_and_finalizes(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest part one", "digest part two"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == _PLAUSIBLE
        assert len(provider.generate_calls) == 1
        # Digests are numbered in the reduce prompt.
        assert "--- Part 1 ---" in provider.generate_calls[0]["prompt"]

    def test_generation_failure_returns_empty(self, caplog) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False

        def _boom(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
            raise RuntimeError("provider down")

        provider.generate = _boom  # type: ignore[method-assign]
        with caplog.at_level(logging.WARNING):
            answer = pipeline._reduce_digest_overview(
                "Chapter 1 — Intro",
                ["digest one"],
                "Write an overview.",
                parts_are_digests=True,
            )
        assert answer == ""

    def test_implausible_reduce_returns_empty(self) -> None:
        provider = _StreamedProvider(
            [], generate_responses=["garbage garbage garbage garbage garbage garbage"]
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == ""

    def test_non_streaming_emit_emits_final_overview(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        pipeline._config.streaming_enabled = False
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == _PLAUSIBLE
        assert answer in capture.text


class TestCondenseDigestGroup:
    """Digest-group condensation with failure fallbacks."""

    def test_condenses_group_to_one_digest(self) -> None:
        provider = _StreamedProvider(
            [],
            generate_responses=[
                "One merged digest covering both parts with figures preserved "
                "in order and enough prose to satisfy every quality gate here."
            ],
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        condensed = pipeline._condense_digest_group(
            "Chapter 1", ["digest one content", "digest two content"]
        )
        assert "merged digest" in condensed
        prompt = provider.generate_calls[0]["prompt"]
        assert "--- Digest 1 ---" in prompt and "--- Digest 2 ---" in prompt

    def test_generation_failure_returns_empty(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)

        def _boom(prompt: str, temperature: float = 0.7, max_tokens: int = 4096) -> str:
            raise RuntimeError("provider down")

        provider.generate = _boom  # type: ignore[method-assign]
        assert pipeline._condense_digest_group("Chapter 1", ["d1"]) == ""

    def test_implausible_condensation_returns_empty(self) -> None:
        provider = _StreamedProvider(
            [], generate_responses=["garbage garbage garbage garbage garbage garbage"]
        )
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert pipeline._condense_digest_group("Chapter 1", ["d1"]) == ""


class TestResumeSummary:
    """Continuation streaming completes a mid-sentence draft."""

    def test_continuation_streams_through_guard(self) -> None:
        provider = _StreamedProvider(
            [(" and the overview concludes here.", None)],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        pieces: list[str] = ["The overview begins with"]
        pipeline._resume_summary("prompt", pieces[0], lambda c, r: pieces.append(c))
        assert (
            "".join(pieces)
            == "The overview begins with and the overview concludes here."
        )
        assert len(provider.stream_calls) == 1
        assert "Draft so far" in provider.stream_calls[0]["prompt"]
        assert pieces[0] in provider.stream_calls[0]["prompt"]

    def test_continuation_failure_keeps_partial(self, caplog) -> None:
        provider = _StreamedProvider([], stream_raise=RuntimeError)
        pipeline = _make_pipeline(provider, on_chunk=None)
        received: list[str] = []
        with caplog.at_level(logging.WARNING):
            pipeline._resume_summary("prompt", "partial draft", received.append)
        assert received == []
        assert any("continuation failed" in r.message for r in caplog.records)


class TestFinalizeOrRetryOverview:
    """Ground/trim finalize with one degenerate-output retry."""

    def test_clean_overview_finalized_without_retry(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        final = pipeline._finalize_or_retry_overview(
            _PLAUSIBLE,
            prompt="prompt",
            heading="Chapter 1",
            grounding_context=_PLAUSIBLE,
        )
        assert "retrieval pipeline" in final
        assert provider.generate_calls == []

    def test_degenerate_overview_retried(self) -> None:
        salad = " ".join(
            [
                "zebra",
                "giraffe",
                "trampoline",
                "sapphire",
                "bakelite",
                "vertebra",
                "compass",
                "harbor",
            ]
            * 30
        )
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        final = pipeline._finalize_or_retry_overview(
            salad,
            prompt="prompt",
            heading="Chapter 1",
            grounding_context=_PLAUSIBLE,
        )
        assert final == _PLAUSIBLE
        assert len(provider.generate_calls) == 1

    def test_empty_overview_returns_empty_without_retry(self) -> None:
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert (
            pipeline._finalize_or_retry_overview(
                "", prompt="p", heading="H", grounding_context="ctx"
            )
            == ""
        )
        assert provider.generate_calls == []


class TestReduceDigestOverviewStreaming:
    """Streaming reduce path: hold buffer, scrubbing, continuation, retry."""

    def test_streams_and_flushes_hold_buffer(self) -> None:
        provider = _StreamedProvider(
            [(_PLAUSIBLE[:80], None), (_PLAUSIBLE[80:], None)],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == _PLAUSIBLE
        # Content streamed live through the callback (heading prefix emitted
        # before streaming begins).
        assert _PLAUSIBLE[:40] in capture.text

    def test_dead_stream_resumes_via_continuation(self) -> None:
        first = (
            "The overview explains the retrieval pipeline in careful detail here. "
            "It covers embedding queries, ranking candidates, and trimming"
        )
        continuation = (
            " context next. The closing paragraph ties the workflow together "
            "cleanly for readers of the whole document over many pages indeed."
        )
        provider = _StreamedProvider(
            [(first, None)],
            stream_raise=RuntimeError,
            stream_raise_calls=1,
            stream_scripts=[[(first, None)], [(continuation, None)]],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The continuation streamed the remainder through the same callback.
        assert "workflow together" in answer
        assert len(provider.stream_calls) >= 2
        assert "Draft so far" in provider.stream_calls[1]["prompt"]

    def test_leak_in_stream_is_scrubbed_not_shipped(self) -> None:
        leak_text = (
            "The overview covers ranking thoroughly here. A figure of 48? no, "
            "it is 45 percent overall in the source text above everything else."
        )
        provider = _StreamedProvider([(leak_text, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one mentions 45 percent overall"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The scrubber removed the rejected candidate and hedge; the corrected
        # figure survives (grounding verified it against the digest source).
        assert "48? no" not in answer
        assert "45 percent" in answer

    @pytest.mark.asyncio
    async def test_async_not_applicable_marker(self) -> None:
        """Guard: reduce overview is a sync-only path (no async twin)."""
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        assert hasattr(pipeline, "_reduce_digest_overview")
