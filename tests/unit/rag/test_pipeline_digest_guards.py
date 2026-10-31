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
import re
from typing import Any

import pytest

from secondbrain.rag.pipeline._fallback_mixin import (
    _CHAPTER_PARTIAL_COVERAGE_NOTE,
    _MAX_MAP_REDUCE_WINDOWS,
    _OVERVIEW_MAX_WORDS,
)
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

# Scripted map-digest response: plausible (passes the degenerate-output
# gate), sentence-terminal-ended, and free of digits so figure grounding
# against the window context is a no-op.
_MAP_DIGEST = (
    "The part covers its topics in the order the source presents them, "
    "recording the structure of the argument and the claims each section "
    "advances, with every point stated once in plain prose and no "
    "commentary added beyond the source."
)

_PAGE_BODY = "Narrative prose continues the argument here. "


def _page_chunk(page: int, page_pos: int, chars: int = 800) -> dict[str, Any]:
    """A body chunk of exactly *chars* characters, tagged with its page spot.

    Texts end on a sentence terminal with no trailing whitespace, so window
    boundary alignment (``_align_window_boundaries``) is a no-op and the
    page/window arithmetic in the coverage tests stays exact.
    """
    text = (_PAGE_BODY * (chars // len(_PAGE_BODY) + 1))[: chars - 1]
    if text.endswith(" "):
        text = text[:-1] + "x"
    return {
        "chunk_text": text + ".",
        "source_file": "a.pdf",
        "page_number": page,
        "page_pos": page_pos,
    }


def _digest_calls(provider: Any) -> list[dict[str, Any]]:
    """The provider's generate calls that are map-digest prompts."""
    return [
        call
        for call in provider.generate_calls
        if "internal digest of Part" in call["prompt"]
    ]


def _prompt_pages(prompt: str) -> set[int]:
    """Pages represented in a prompt's formatted ``Source: ... (page N)`` lines."""
    return {int(m) for m in re.findall(r"Source: a\.pdf \(page (\d+)\)", prompt)}


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


class TestSummaryWindowReplan:
    """Oversized map passes: adaptive re-split (D1) and coverage framing (D3).

    The old cap silently sliced ``windows[:50]``, dropping roughly half the
    source head-first; the replan re-splits the flattened chunks at an
    adaptive window size so the map pass covers the complete source within
    the map-call budget, and discloses sampling when even the per-window
    ceiling cannot fit the source.
    """

    def test_oversized_source_resplits_within_cap_and_covers_all_pages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """D1: a >50-window source re-splits to the cap, covering every page.

        400 chunks of 800 chars (~320k source chars, 100 pages): the caller's
        default 3500-char pre-split yields 100 windows -- over the 50-window
        map-call cap -- and the adaptive re-split at ceil(320k/50) = 6400
        chars yields exactly 50 windows of 8 chunks, so every page reaches a
        map window and none is dropped trailing.
        """
        chunks = [_page_chunk(1 + i // 4, i % 4) for i in range(400)]
        assert sum(len(c["chunk_text"]) for c in chunks) == 320_000
        provider = _StreamedProvider(
            [],
            generate_responses=[_MAP_DIGEST] * _MAX_MAP_REDUCE_WINDOWS + [_PLAUSIBLE],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        pipeline._config.streaming_enabled = False
        # Condensation is reduce-prompt plumbing (covered by
        # TestCondenseDigestGroup); patched out so the generate-call
        # accounting here counts map calls only.
        monkeypatch.setattr(
            pipeline, "_condense_digest_groups", lambda heading, digests: digests
        )
        answer = pipeline._summarize_bounded(
            heading="Chapter 15 (overview)",
            windows=pipeline._split_bounded(chunks),
            instruction="Write an overview.",
        )
        digest_calls = _digest_calls(provider)
        # The map pass ran exactly at the cap: one digest per re-split
        # window, numbered to 50 -- not the caller's 100 windows.
        assert len(digest_calls) == _MAX_MAP_REDUCE_WINDOWS
        assert "Part 50 of 50" in digest_calls[-1]["prompt"]
        # Full page range covered: every page of the 100-page source reached
        # a map window, and the final window still owns the trailing pages
        # the old windows[:50] slice used to drop.
        pages: set[int] = set()
        for call in digest_calls:
            pages |= _prompt_pages(call["prompt"])
        assert pages == set(range(1, 101))
        assert max(_prompt_pages(digest_calls[-1]["prompt"])) == 100
        # The reduce consumed the digests under the unchanged complete
        # framing, and no disclosure note reached either channel.
        reduce_prompt = next(
            c["prompt"]
            for c in provider.generate_calls
            if "terse digests" in c["prompt"]
        )
        assert "cover every part in order" in reduce_prompt
        assert "evenly spread sample" not in reduce_prompt
        assert answer == _PLAUSIBLE
        assert _CHAPTER_PARTIAL_COVERAGE_NOTE not in answer
        assert _CHAPTER_PARTIAL_COVERAGE_NOTE not in capture.text

    def test_partial_digest_framing_presents_a_sample_not_the_source(self) -> None:
        """D3: ``partial_coverage`` swaps the sequential-coverage framing."""
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        answer = pipeline._reduce_digest_overview(
            "Chapter 15 — Virtual machines",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
            partial_coverage=True,
        )
        assert answer == _PLAUSIBLE
        prompt = provider.generate_calls[0]["prompt"]
        assert "evenly spread sample of Chapter 15 — Virtual machines" in prompt
        assert "not the complete source" in prompt
        # The complete framing's sequential claim must not leak into a
        # sampled run.
        assert "cover every part in order" not in prompt

    def test_single_pass_framing_untouched_by_the_partial_flag(self) -> None:
        """The single-pass framing is complete by construction; flag is inert."""
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        pipeline = _make_pipeline(provider, on_chunk=None)
        pipeline._config.streaming_enabled = False
        answer = pipeline._reduce_digest_overview(
            "Chapter 15 — Virtual machines",
            ["raw source part"],
            "Write an overview.",
            parts_are_digests=False,
            numbered_parts=False,
            partial_coverage=True,
        )
        assert answer == _PLAUSIBLE
        prompt = provider.generate_calls[0]["prompt"]
        assert "covers Chapter 15 — Virtual machines" in prompt
        assert "terse digests" not in prompt
        assert "evenly spread sample" not in prompt

    def test_consolidate_windows_regroups_without_dropping_chunks(self) -> None:
        """Surplus windows re-group evenly; no chunk is dropped or duplicated."""
        provider = _StreamedProvider([], generate_responses=[])
        pipeline = _make_pipeline(provider, on_chunk=None)
        windows = [[{"i": i}] for i in range(60)]
        # At or under the limit the windows are returned untouched.
        kept = windows[:_MAX_MAP_REDUCE_WINDOWS]
        assert pipeline._consolidate_windows(kept) is kept
        regrouped = pipeline._consolidate_windows(windows)
        assert len(regrouped) == _MAX_MAP_REDUCE_WINDOWS
        # Every chunk survives exactly once, in reading order.
        flat = [c["i"] for window in regrouped for c in window]
        assert flat == list(range(60))
        # Even grouping: group sizes differ by at most one chunk.
        sizes = [len(window) for window in regrouped]
        assert max(sizes) - min(sizes) <= 1


class TestMapWindowDigest:
    """Digest generation: stream preference, failure regeneration, validation."""

    def test_progress_marker_forwarded_on_reasoning_channel(self) -> None:
        """One one-line marker per window on the reasoning channel only."""
        provider = _StreamedProvider(
            [],
            generate_responses=[
                "A digest paragraph covering the retrieval topics with every "
                "figure preserved exactly once, in careful detail, throughout."
            ],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        digest = pipeline._map_window_digest("Chapter 15", "source ctx", 3, 7)
        assert "digest paragraph" in digest
        # Exactly the window's marker, ahead of its generation, on the
        # reasoning channel; the content channel stays pure.
        assert ("", "· window 3/7\n") in capture.calls
        assert capture.text == ""

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


class TestOverviewWordCeiling:
    """The word ceiling is a runaway guard: legitimate drafts survive it.

    The fix-summary-window-truncation replay of UserManual.pdf chapter 15
    (full-coverage adaptive map windows) drafted a legitimate 1255-word,
    ten-paragraph overview; the then-1200-word ceiling trimmed the stored
    copy at a sentence boundary ("...manage VM snapshots.") while the
    terminal had streamed the complete draft.  These tests pin the contract
    the ceiling's rationale comment claims: a normal draft survives
    finalization unchanged, a genuine runaway loop is still cut.
    """

    @staticmethod
    def _draft(words: int) -> str:
        """A digits-free, sentence-terminal prose draft of ~*words* words.

        Sentences cycle topic/qualifier words so the text is varied rather
        than degenerate repetition, and contain no digits, which keeps the
        scrub, metric-prune, and figure-ground post-passes no-ops so the
        tests exercise only the word-ceiling behaviour.
        """
        topics = [
            "retrieval",
            "ranking",
            "chunking",
            "embedding",
            "storage",
            "ingestion",
            "search",
            "querying",
            "caching",
            "streaming",
        ]
        qualifiers = [
            "careful",
            "detailed",
            "concise",
            "thorough",
            "practical",
            "clear",
            "structured",
            "focused",
            "consistent",
            "compact",
        ]
        sentences: list[str] = []
        count = 0
        i = 0
        while count < words:
            topic = topics[i % len(topics)]
            qualifier = qualifiers[(i // len(topics)) % len(qualifiers)]
            sentence = (
                f"The {qualifier} handling of {topic} receives its own "
                "careful explanation here, and the chapter keeps each "
                "discussion grounded in the workflow the reader already "
                "knows well."
            )
            sentences.append(sentence)
            count += len(sentence.split())
            i += 1
        return " ".join(sentences)

    def test_legitimate_dense_draft_survives_finalization(self) -> None:
        pipeline = _make_pipeline(
            _StreamedProvider([], generate_responses=[]), on_chunk=None
        )
        draft = self._draft(1255)  # the observed legitimate ch15 draft size
        assert len(draft.split()) >= 1255
        assert _OVERVIEW_MAX_WORDS > 1255
        assert pipeline._finalize_overview(draft, "") == draft

    def test_runaway_draft_is_still_trimmed_at_sentence_boundary(self) -> None:
        pipeline = _make_pipeline(
            _StreamedProvider([], generate_responses=[]), on_chunk=None
        )
        draft = self._draft(_OVERVIEW_MAX_WORDS * 2)
        result = pipeline._finalize_overview(draft, "")
        assert result != draft
        assert len(result.split()) <= _OVERVIEW_MAX_WORDS
        assert result.endswith(".")
