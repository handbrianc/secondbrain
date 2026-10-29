"""Reasoning-channel and live-streaming display tests for the reduce path.

Tasks 3.1/3.3 of the ``fix-summary-fidelity`` change (display contract
revised 2026-10-25 per user decision: live streaming wins over byte
parity): reasoning reaches the terminal only on the reasoning channel
(``("", reasoning)`` pairs -- the renderer collapses it by default), and
``_reduce_digest_overview`` streams committed hold-releases live while the
draft forms.  The stored answer is the finalized overview: equal to the
streamed draft on the happy path (finalize makes no mutation), legitimately
divergent on repair paths -- leak-scrub hold replacement keeps parity, while
leak-abort retries, adopted empty-stream retries, degenerate finalize
retries, and finalize post-pass mutations diverge.  Each case is pinned
below, along with the no-duplicate guarantee (a retry block is never
followed by a second emission of the finalized overview).

The second-to-last class documents the "depenzds" root-cause mechanism that
remains in the legacy guarded window path (out of scope) and, by the same
mechanism, on the reduce path's repair retries: a low-temperature retry is
APPENDED to already-committed screen output while the returned (stored)
answer is the retry text alone, so the display holds words the stored answer
does not.  The final class pins the multi-chapter generator's transcript
parity: mixed runs store byte-for-byte what they stream, and a run with no
content at all collapses to "" for the caller's roster fallback.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from unittest.mock import MagicMock

import secondbrain.rag.pipeline._fallback_mixin as _fallback_mixin
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._fallback_mixin import _STREAM_LEAK_HOLD


class _StreamedProvider:
    """Provider double streaming scripted (content, reasoning) chunks.

    ``script`` is a list of ``(content, reasoning)`` tuples replayed through
    ``on_chunk`` on every ``stream_chat`` call; ``generate_responses`` backs
    the non-streaming ``generate`` used by low-temperature retries.  When
    per-call scripts matter (multi-chapter runs stream one call per chapter),
    ``stream_scripts`` supplies one script per ``stream_chat`` call in order,
    falling back to the shared ``script`` once exhausted.
    """

    def __init__(
        self,
        script: Sequence[tuple[str, str | None]] = (),
        *,
        generate_responses: Sequence[str] = (),
        stream_scripts: Sequence[Sequence[tuple[str, str | None]]] = (),
    ) -> None:
        self.script = list(script)
        self.generate_responses = list(generate_responses)
        self.stream_scripts = [list(s) for s in stream_scripts]
        self.generate_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.generate_calls.append(
            {"prompt": prompt, "temperature": temperature, "max_tokens": max_tokens}
        )
        if self.generate_responses:
            return self.generate_responses.pop(0)
        return "retry generated answer"

    def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
        on_chunk: Callable[[str, str | None], None],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        self.stream_calls.append(
            {
                "prompt": messages[-1]["content"] if messages else "",
                "temperature": temperature,
            }
        )
        script = self.stream_scripts.pop(0) if self.stream_scripts else self.script
        for content, reasoning in script:
            on_chunk(content, reasoning)
        return "".join(content for content, _ in script if content)


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

    @property
    def content_calls(self) -> list[str]:
        """Content-channel emissions in order (reasoning-only calls excluded)."""
        return [c for c, _ in self.calls if c]


_PLAUSIBLE = (
    "This chapter explains the retrieval pipeline in careful detail. "
    "It covers embedding queries, ranking candidates, and trimming context. "
    "Each idea is presented once with a short example and no repetition. "
    "The closing paragraph ties the workflow together cleanly."
)


def _chunk(text: str) -> dict[str, Any]:
    """Minimal body-chunk double for the generator window machinery."""
    return {"chunk_text": text, "source_file": "a.pdf", "page": 1}


class TestReduceReasoningChannel:
    """Reasoning keeps flowing on its own ("" content) channel."""

    def test_reduce_forwards_reasoning_with_empty_content(self) -> None:
        provider = _StreamedProvider(
            [("", "weighing the digest order"), (_PLAUSIBLE, None)]
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The pipeline->renderer reasoning contract is unchanged: ("", reasoning)
        # pairs the renderer can buffer into its collapsed thinking element.
        assert ("", "weighing the digest order") in capture.calls
        assert all(c == "" for c, r in capture.calls if r)
        # The content channel streamed the draft live; finalize made no
        # mutation on this clean stream, so the display equals the stored
        # answer byte for byte (happy-path parity).
        assert capture.text == answer

    def test_map_digest_reasoning_forwarded_content_internal(self) -> None:
        digest_text = (
            "A terse digest of the part covering retrieval topics in careful "
            "detail with grounded figures and no commentary at all."
        )
        provider = _StreamedProvider([("", "reading the window"), (digest_text, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        digest = pipeline._map_window_digest("Chapter 1", "the source text", 1, 1)
        assert digest == digest_text
        assert ("", "reading the window") in capture.calls
        # The digest content itself never reaches the screen.
        assert capture.text == ""


class TestReduceDisplayParity:
    """Live committed-prefix streaming; happy-path parity, documented repairs.

    The reduce streams committed hold-releases while the draft forms.  The
    stored answer is the finalized overview: identical to the streamed draft
    when finalize makes no mutation, and legitimately divergent when a repair
    pass (scrub replacement, retry, post-pass trim) changes the text after
    (part of) it was already on screen.
    """

    def test_clean_stream_final_emitted_once_and_matches(self) -> None:
        provider = _StreamedProvider(
            [
                (_PLAUSIBLE[:60], None),
                (_PLAUSIBLE[60:120], None),
                (_PLAUSIBLE[120:], None),
            ]
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
        # Content streamed live: the hold-buffer overflow can only fire inside
        # the stream guard, so more than one content emission proves committed
        # prefixes reached the terminal while the draft was forming.
        assert len(capture.content_calls) >= 2
        # No duplicate final emission: the emissions join to exactly the
        # stored answer (finalize made no mutation on this clean stream).
        assert "".join(capture.content_calls) == answer
        assert capture.text == answer

    def test_scrubbed_hold_replacement_keeps_display_equal(self) -> None:
        prefix = (
            "The overview explains the retrieval pipeline in careful detail "
            "across indexing, ranking, and context trimming stages. It grounds "
            "every quoted figure against the source text without exception. "
        )
        leak_tail = "A figure of 48? no, it is 45 percent overall in the corpus."
        assert len(prefix) > _STREAM_LEAK_HOLD
        provider = _StreamedProvider([(prefix, None), (leak_tail, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one mentions 45 percent overall"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The scrubbable leak was cut from the withheld tail; the corrected
        # figure (grounded against the digest) survives in the final.
        assert "48? no" not in answer
        assert "45 percent" in answer
        # The committed prefix streamed live (overflow inside the guard), and
        # the scrub replacement was confined to the withheld tail, so the
        # emitted text is exactly the scrubbed draft the finalize kept.
        assert len(capture.content_calls) >= 2
        assert "".join(capture.content_calls) == answer
        assert capture.text == answer

    def test_leak_abort_retry_streams_replacement_block(self) -> None:
        clean = (
            "The overview explains the retrieval pipeline in careful detail "
            "across indexing, ranking, and context trimming stages. It grounds "
            "every quoted figure against the source text without exception. "
        )
        assert len(clean) > _STREAM_LEAK_HOLD
        leak = "and then, wait - the numbers never settled at all anywhere."
        provider = _StreamedProvider(
            [(clean, None), (leak, None)], generate_responses=[_PLAUSIBLE]
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
        assert provider.generate_calls[0]["temperature"] == 0.1
        # HEAD semantics: the pre-leak committed prefix was already on screen
        # when the unscrubbable leak aborted the stream; the low-temperature
        # retry then streamed as a replacement block.  The leak itself never
        # reached the terminal.
        assert capture.content_calls[0] == clean[: len(clean) - _STREAM_LEAK_HOLD]
        assert capture.content_calls[1] == f"\n\n{_PLAUSIBLE}\n\n"
        assert len(capture.content_calls) == 2
        assert "wait -" not in capture.text
        # Documented repair divergence (the "depenzds" mechanism): the screen
        # keeps the pre-leak prefix and the raw retry block, while the stored
        # answer is the finalized retry text alone.
        assert capture.text != answer

    def test_empty_stream_retry_streams_replacement_block(self) -> None:
        provider = _StreamedProvider([], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == _PLAUSIBLE
        assert provider.generate_calls[0]["temperature"] == 0.1
        # The retry streamed as a replacement block and was adopted as the
        # draft (the bookkeeping marks it already-flushed), so it is emitted
        # exactly once -- no duplicate final emission of the adopted draft.
        assert capture.content_calls == [f"\n\n{_PLAUSIBLE}\n\n"]
        # Documented repair divergence: the screen shows the raw retry block
        # with its own separators; the stored answer is the bare finalized
        # text (identical content here, different padding).
        assert capture.text != answer

    def test_implausible_final_retry_streams_replacement_block(self) -> None:
        draft = ("garbage " * 7).strip() + "."
        provider = _StreamedProvider([(draft, None)], generate_responses=[_PLAUSIBLE])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        assert answer == _PLAUSIBLE
        assert provider.generate_calls[0]["temperature"] == 0.1
        # The degenerate draft is shorter than the hold buffer, so it reached
        # the screen in the end-of-stream flush; the finalize retry then
        # streamed as a replacement block and is stored (finalized) as the
        # answer -- emitted exactly once, no duplicate.
        assert capture.content_calls == [draft, f"\n\n{_PLAUSIBLE}\n\n"]
        # Documented repair divergence: the screen keeps the degenerate draft
        # the stored answer supersedes.
        assert "garbage" in capture.text
        assert "garbage" not in answer

    def test_finalize_mutation_diverges_display_metric_prune(self) -> None:
        draft = (
            "The overview explains the retrieval pipeline in careful detail "
            "and covers ranking candidates with a worked example throughout. "
            "The model reported an average weekly IC of 3.32 and 6.68 in tests."
        )
        provider = _StreamedProvider([(draft, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The raw draft streamed to the terminal (committed prefixes live,
        # remainder flushed at the end of the stream); the finalize post-pass
        # then pruned the impossible figures, so the stored answer is the
        # pruned text.  This is the documented post-pass divergence of the
        # restored live-streaming contract, not a display bug.
        assert "3.32" in draft
        assert "3.32" not in answer and "6.68" not in answer
        assert "IC" in answer
        assert "".join(capture.content_calls) == draft
        assert capture.text == draft
        assert capture.text != answer

    def test_finalize_mutation_diverges_display_word_budget(self, monkeypatch) -> None:
        draft = (
            "The overview explains the retrieval pipeline in careful detail. "
            "It covers embedding queries and ranking candidates clearly. "
            "Then it trims context and cites each source example faithfully."
        )
        monkeypatch.setattr(_fallback_mixin, "_OVERVIEW_MAX_WORDS", 12)
        provider = _StreamedProvider([(draft, None)])
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._reduce_digest_overview(
            "Chapter 1 — Intro",
            ["digest one"],
            "Write an overview.",
            parts_are_digests=True,
        )
        # The word-budget post-pass cut the draft back to a sentence boundary
        # after the full draft had streamed; the screen keeps the draft while
        # the stored answer is the trimmed final (documented divergence).
        assert (
            answer == "The overview explains the retrieval pipeline in careful detail."
        )
        assert "".join(capture.content_calls) == draft
        assert capture.text == draft
        assert capture.text != answer

    def test_non_streaming_emits_bare_final(self) -> None:
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
        # The emission is the bare final exactly as stored -- no "\n\n" padding.
        assert capture.calls[-1] == (_PLAUSIBLE, None)
        assert capture.text == answer


class TestLegacyGuardedPathRetryDivergence:
    """Documents the depenzds mechanism on retry repair paths.

    ``_generate_window_guarded`` (no production callers; kept for the legacy
    map-reduce surface) streams its window content live and, when the stream
    degrades, APPENDS a low-temperature retry block to the already-emitted
    prefix -- while the returned (stored) answer is the retry text alone.
    The screen therefore keeps words the stored answer does not have.  The
    reduce path now streams live too (user decision: streaming wins over
    byte parity), so its repair retries behave the same way; the parity
    tests above pin exactly which repair paths diverge and which keep
    display and storage equal.
    """

    def test_retry_appends_after_committed_prefix_display_holds_typo(self) -> None:
        prefix = (
            "The pipeline depenzds on the index and rank steps as documented "
            "in the manual carefully."
        )
        leak = "and the value of 77?? (wait, the text says 78.29 percent) hmm."
        provider = _StreamedProvider(
            [(prefix, None), (leak, None)], generate_responses=[_PLAUSIBLE]
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_window_guarded("prompt", "Chapter 1")
        # The aborted leak chunk itself never reached the screen, but the
        # pre-leak prefix did -- and the retry was appended after it.
        assert answer == _PLAUSIBLE
        assert "depenzds" in capture.text
        assert "depenzds" not in answer
        assert capture.text != answer
        # The retry block was appended with its own separators, not a plain
        # continuation of the committed prefix.
        assert capture.text.endswith(f"{_PLAUSIBLE}\n\n")


class TestMultiChapterTranscriptParity:
    """A multi-chapter run stores byte-for-byte what it streams.

    The generator streams one heading per chapter and each chapter's reduce
    streams its committed overview prefixes live; every character of a
    surviving overview is emitted exactly once (hold overflow during the
    stream, remainder at the end-of-stream flush), so the returned
    transcript -- what ``_save_turn`` stores -- joins the same blocks in the
    same order whenever finalize makes no mutation.  A chapter whose
    overview fails keeps its streamed heading block; a run where NO chapter
    produced any content collapses to ``""`` so the caller's roster fallback
    can speak (the headings already on screen are the documented
    roster-fallback display divergence, unchanged).
    """

    def test_mixed_run_stream_equals_return(self) -> None:
        garbage = ("garbage " * 7).strip() + "."
        provider = _StreamedProvider(
            generate_responses=[garbage],
            stream_scripts=[
                # Chapter 1: no content at all; the low-temperature retry
                # also fails (implausible), so nothing streams for it and
                # this overview comes back empty.
                [("", "reading chapter one")],
                # Chapter 2: a clean three-chunk overview.
                [
                    (_PLAUSIBLE[:60], None),
                    (_PLAUSIBLE[60:120], None),
                    (_PLAUSIBLE[120:], None),
                ],
            ],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_multi_chapter_summary(
            [1, 2],
            {1: [_chunk("chapter one body")], 2: [_chunk("chapter two body")]},
            {1: "One", 2: "Two"},
        )
        # The failed chapter keeps its streamed heading block; the dead
        # draft and its failed retry never ship.
        assert answer.startswith("Chapter 1 — One\n\n")
        assert "garbage" not in answer
        assert "Chapter 2 — Two" in answer
        assert _PLAUSIBLE in answer
        # Reasoning flowed on the reasoning channel only; the only content
        # emissions are chapter 2's streamed overview (plus the headings).
        assert ("", "reading chapter one") in capture.calls
        assert all(c == "" for c, r in capture.calls if r)
        # Byte-exact parity between the live stream and the stored transcript.
        assert capture.text == answer
        # Chapter 1's dead stream triggered exactly one retry.
        assert [c["temperature"] for c in provider.generate_calls] == [0.1]

    def test_all_empty_collapses_to_empty_for_roster_fallback(self) -> None:
        garbage = ("garbage " * 7).strip() + "."
        provider = _StreamedProvider(
            generate_responses=[garbage, garbage],
            stream_scripts=[[("", None)], [("", None)]],
        )
        capture = _CallbackCapture()
        pipeline = _make_pipeline(provider, on_chunk=capture)
        answer = pipeline._generate_multi_chapter_summary(
            [1, 2],
            {1: [_chunk("chapter one body")], 2: [_chunk("chapter two body")]},
            {1: "One", 2: "Two"},
        )
        # No chapter produced content: the transcript collapses to "" so the
        # caller's roster fallback keeps speaking (unchanged contract).
        assert answer == ""
        # The headings still streamed -- the documented roster-fallback
        # display divergence, identical to the pre-change behaviour.  The
        # retries' garbage never streams (implausible retries emit nothing).
        assert "Chapter 1 — One" in capture.text
        assert "Chapter 2 — Two" in capture.text
        assert "garbage" not in capture.text
        assert [c["temperature"] for c in provider.generate_calls] == [0.1, 0.1]
