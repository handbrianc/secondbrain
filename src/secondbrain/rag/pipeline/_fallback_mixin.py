"""Guarded generation, validation, and fallback helpers for the RAG pipeline."""

from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

from secondbrain.conversation import ConversationSession
from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.rag.pipeline._leak_scrub import (
    _contains_reasoning_leak,
    _is_stream_leak,
    _scrub_self_correction,
    _strip_numeric_self_correction,
)
from secondbrain.rag.pipeline._streaming import (
    _StreamAbortError,
    _StreamLeakError,
    _WindowStreamSink,
)
from secondbrain.rag.pipeline._text_quality import (
    _DERAIL_FUNCTION_WORD_RATIO,
    _DERAIL_TTR_FN_GATE,
    _DERAIL_TYPE_TOKEN_RATIO,
    _FUNCTION_WORDS,
    _ends_on_sentence,
    _ground_figures,
    _prune_implausible_metric_figures,
    _trim_to_sentence_end,
    _trim_to_word_budget,
)

logger = logging.getLogger(__name__)

# Upper bound on how many independent map-reduce LLM calls one summarisation may
# issue.  Without this, a dense multi-chapter book or a chapter with many
# sections would fan out into dozens of sequential, thinking-mode LLM calls,
# making the chat appear frozen on "Thinking..." for minutes.
_MAX_MAP_REDUCE_WINDOWS = 50


# Temperature for deterministic map-reduce *summary* generation (chapter and
# section overviews). Summaries must faithfully reproduce the source figures, so
# they are generated near-deterministically instead of at the default creative
# temperature (which makes the model regenerate numbers rather than copy them).
# This matches the low temperature the degenerate-window retry already uses.
SUMMARY_TEMPERATURE = 0.1


# Max wall-clock seconds a single summary window may run before it is aborted as
# unresolvable.  A model can spend its whole budget re-verifying figures in its
# reasoning, emitting only sporadic content and never stabilizing; the cap
# guarantees the overall summary always terminates and returns to the prompt.
# On abort the window's partial content is retained (trimmed to a clean
# sentence), so a slow final window still contributes its ending instead of the
# chapter overview dropping it.
#
# Heavy-reasoning models can legitimately think for minutes before any content
# streams, so the default is generous and overridable via
# SECONDBRAIN_SUMMARY_WINDOW_MAX_SECONDS.  The previous 150s (tuned for
# DeepSeek) silently dropped GLM windows whose thinking alone approached the
# budget: the collapsed-thinking counter printed, then the timeout fired before
# the first content token and the window vanished from the overview.  600s was
# sized for the 8000-token budget; with _SUMMARY_REDUCE_MAX_TOKENS at 32768 a
# healthy dense-chapter stream can legitimately run past 600s, and aborting it
# here discards minutes of completed reasoning and restarts the whole
# generation, so the wall must exceed the budget's realistic drain time.
_WINDOW_MAX_SECONDS = max(
    60,
    int(os.environ.get("SECONDBRAIN_SUMMARY_WINDOW_MAX_SECONDS", "1200")),
)


# Source characters per summary window.  Splitting the body into bounded windows
# like this is what keeps every generation small -- fast, under the request
# timeout, and too short to drive the model into a figure-verification loop --
# which is what makes the summary path robust for any source size.  Windows are
# small enough that each window's summary completes well within the output token
# cap, so the last window is not truncated mid-sentence.
_SUMMARY_WINDOW_CHARS = 3500


# Output token caps for the summary paths (single-pass overview, and the
# two-pass map-reduce fallback: map digest -> reduce overview).  These are
# ceilings, NOT length targets: the prompts bound the visible length (terse
# digests, overview per the caller's instruction), and the final overview's
# length is enforced deterministically by _OVERVIEW_MAX_WORDS below -- never
# by a numeric constraint in a prompt, which only triggers word-counting
# loops in the model's reasoning.  The generous ceilings exist because
# GLM-class servers spend the SAME max_tokens budget on hidden reasoning and
# visible content -- a tight cap amputates the content mid-sentence at
# finish_reason=length, which is exactly what silently cut off summary
# windows under the previous 1200-token per-window cap.  8000 was itself
# amputated on the densest chapters (GLM burned it on reasoning alone while
# drafting and re-verifying every figure), leaving nothing for the overview;
# 32768 leaves ~4x the observed worst-case reasoning spend for the answer.
_MAP_DIGEST_MAX_TOKENS = 4000


_SUMMARY_REDUCE_MAX_TOKENS = 32768


# A chapter whose formatted source fits within this budget is summarized in
# ONE streamed call over the complete text (~80k tokens at ~4 chars/token --
# comfortably inside a 128k+ context window).  The two-pass map-reduce path
# below is only the fallback for genuinely oversized sources.
_SINGLE_PASS_MAX_CHARS = 320_000


# Reduce-prompt hierarchy: when the map-reduce fallback produces more than
# _HIERARCHY_THRESHOLD digests, they are first condensed into balanced groups
# of at most _HIERARCHY_GROUP_SIZE (one non-streamed call per group) so the
# final reduce reads a handful of merged digests instead of dozens of "Part N"
# fragments.  Group calls may fail; the raw digests are then passed through,
# so condensation is a size optimization that never regresses coverage.
_HIERARCHY_GROUP_SIZE = 8


_HIERARCHY_THRESHOLD = 12


# Deterministic word ceiling for the final overview, enforced by trimming at
# a sentence boundary after generation (in _finalize_overview).  The prompt
# asks for a short overview in prose terms; the bound itself lives here so
# the model never burns reasoning counting words.  It is a runaway guard, NOT
# a length target: the reduce call streams its draft live, so any normal
# draft must survive finalization unchanged -- observed three-paragraph
# overviews run 500-900 words, and a tighter ceiling silently amputated the
# stored/history answer well short of the text the user had just read.
_OVERVIEW_MAX_WORDS = 1200


# Mid-stream guard for a live-streaming map-reduce window: once this many
# characters have accumulated, if the buffered text is already degenerate
# (repetitive/token-soup), we abort the stream immediately so a runaway window
# cannot stream an unbounded number of tokens (the summary path now uses the
# global unbounded max_tokens).  A short buffer is never treated as flooding so
# the first sentence of a normal summary always streams.
_STREAM_FLOOD_MIN_CHARS = 120


# Cap for the low-temperature *retry* of a degenerate window.  The retry is a
# recovery fallback, not the user-facing answer, so keeping it bounded prevents
# a still-degenerate retry from silently streaming a huge token-soup response.
_RETRY_MAX_TOKENS = 4096


# Characters withheld from the live stream before flushing, so a self-correction
# leak is caught on the buffered tail and the window aborted before it streams.
_STREAM_LEAK_HOLD = 120


# Terse single-chapter overview instruction. The static prompt is kept as a
# plain named constant and the chapter identification is substituted with
# .format() at call time, so the long text stays a single testable literal.
_CHAPTER_OVERVIEW_INSTRUCTION = (
    "Summarize the following portion of chapter {chapter_num} "
    "({chapter_title}). Use ONLY the document content below. Write a "
    "flowing prose overview in six to ten short paragraphs, one "
    "topic per paragraph, keeping each paragraph tight -- do not "
    "exhaust every subsection detail, select the chapter's major "
    "topics and their key supporting facts only. Then STOP -- do "
    "not fill extra space or restate. Cover the "
    "main topics, key concepts, and supporting details. Do "
    "NOT use headings, sub-headers, or bullet lists. Do NOT open with "
    "meta-framing such as 'This portion covers...' -- begin directly "
    "with the substance. Quote any numbers, years, statistics, and "
    "metrics EXACTLY as they appear in the content below; never invent, "
    "estimate, round, or 'correct' a figure the source does not state "
    "-- if a specific number is not clearly present, omit it rather "
    "than guessing. State each figure once and move on; do not hedge, "
    "second-guess, or correct figures. Cover each study's experimental "
    "setup -- data universe, feature construction and selection, and "
    "training or evaluation windows -- and any benchmark comparison "
    "the content draws, not only its headline results. When the "
    "content states conflicting values for the same fact (for example "
    "different years in narrative and citations), report the "
    "narrative value without editorializing about the discrepancy. "
    "When the content reports values from separate experiments or "
    "evaluation settings, give each value its own sentence tied to "
    "its own setup rather than combining different runs into one "
    "sentence that reads as self-contradiction. "
    "Do not reproduce code details or "
    "function arguments (e.g. list(range(...))) verbatim. Do not print "
    "any notes, disclaimers, or headings such as 'Note', 'Important', or "
    "'Not in this chapter'. Write the overview exactly once: treat "
    "your first complete draft as final -- do not produce a "
    "preliminary draft and then a second, tightened version of the "
    "same overview, and do not re-verify the quoted figures after "
    "drafting. Keep internal planning to brief selection and "
    "structure decisions only. If some "
    "content below does not belong to "
    "this chapter, summarize only the content that does and never add "
    "general knowledge or commentary about other chapters."
)


# Honest-fallback note streamed ahead of the whole-document overview when the
# chapter-range agreement gate vetoes the legacy chapter map: the reader is
# told per-chapter mapping failed instead of being shown confident wrong-page
# chapters.
_WHOLE_DOCUMENT_OVERVIEW_NOTE = (
    "Per-chapter page mapping was unavailable for this document; "
    "here is a whole-document overview."
)


# Upper bound on the page-spread sample that feeds the whole-document overview
# fallback.  Sized inside the 24-32 chunk budget tuned for the bounded-window
# summarizer: enough spread to cover a large document end to end (the sample
# is taken evenly across the full page range) while keeping the overview call
# small and fast.
_OVERVIEW_SAMPLE_MAX_CHUNKS = 28


# Whole-document overview instruction for the gate-veto fallback.  Mirrors the
# chapter overview instruction's voice; the source is a page-spread sample, so
# the model is told to treat it as the document's content rather than muse
# about sampling.
_WHOLE_DOCUMENT_OVERVIEW_INSTRUCTION = (
    "Write a whole-document overview of the document from which the "
    "content below is sampled. Use ONLY the document content below. Write "
    "a flowing prose overview in six to ten short paragraphs, one topic "
    "per paragraph, keeping each paragraph tight -- do not exhaust every "
    "detail, select the document's major topics and their key supporting "
    "facts only, in the order the content presents them. Then STOP -- do "
    "not fill extra space or restate. Quote any numbers, years, "
    "statistics, and metrics EXACTLY as they appear in the content below; "
    "never invent, estimate, round, or 'correct' a figure the source does "
    "not state -- if a specific number is not clearly present, omit it "
    "rather than guessing. State each figure once and move on; do not "
    "hedge, second-guess, or correct figures. Do NOT use headings, "
    "sub-headers, or bullet lists. Do NOT open with meta-framing such as "
    "'This document covers...' -- begin directly with the substance. Do "
    "not mention page numbers and do not comment on the text below being "
    "a sample or an excerpt; treat it as the document's content. Do not "
    "reproduce code details or function arguments (e.g. "
    "list(range(...))) verbatim. Do not print any notes, disclaimers, or "
    "headings such as 'Note', 'Important', or 'Not in this document'. "
    "Write the overview exactly once: treat your first complete draft as "
    "final -- do not produce a preliminary draft and then a second, "
    "tightened version of the same overview, and do not re-verify the "
    "quoted figures after drafting. Keep internal planning to brief "
    "selection and structure decisions only."
)


# Per-part summary instruction for anthology documents (one generation per
# part via the bounded-window machinery).  The static prompt is kept as a
# plain named constant with the part identification substituted with
# .format() at call time, so the long text stays a single testable literal
# (same pattern as _CHAPTER_OVERVIEW_INSTRUCTION).
_ANTHOLOGY_PART_INSTRUCTION = (
    "Summarize part {part_id} of this compiled document as a standalone "
    "report section. Use ONLY the document content below. Write a flowing "
    "prose overview in four to eight short paragraphs, one topic per "
    "paragraph, keeping each paragraph tight -- do not exhaust every "
    "subsection detail, select the part's major topics and their key "
    "supporting facts only, in the order the content presents them. Then "
    "STOP -- do not fill extra space or restate. Cover the part's key "
    "points and structure. Do NOT use headings, sub-headers, or bullet "
    "lists. Do NOT open with meta-framing such as 'This part covers...' "
    "-- begin directly with the substance. Quote any numbers, years, "
    "statistics, and metrics EXACTLY as they appear in the content below; "
    "never invent, estimate, round, or 'correct' a figure the source does "
    "not state -- if a specific number is not clearly present, omit it "
    "rather than guessing. State each figure once and move on; do not "
    "hedge, second-guess, or correct figures. Do not reproduce code "
    "details or function arguments (e.g. list(range(...))) verbatim. Do "
    "not print any notes, disclaimers, or headings such as 'Note', "
    "'Important', or 'Not in this part'. Write the overview exactly once: "
    "treat your first complete draft as final -- do not produce a "
    "preliminary draft and then a second, tightened version of the same "
    "overview, and do not re-verify the quoted figures after drafting. "
    "Keep internal planning to brief selection and structure decisions "
    "only. If some content below does not belong to this part, summarize "
    "only the content that does and never add general knowledge or "
    "commentary about other parts."
)


# Upper bound on section titles quoted into one part's prompt context.  The
# list only orients the model (it shows the part's internal structure); a
# full roster of a 20-section part would bloat every window call for little
# benefit.
_ANTHOLOGY_PART_SECTION_CONTEXT_MAX = 12


class _FallbackMixin(_RAGPipelineState):
    """No-results fallback, grounded re-retrieval, and relevance helpers."""

    def _contextual_search(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
    ) -> list[dict[str, Any]] | None:
        """Check whether *query* is a grounded follow-up and run the sync search.

        Only attempts retrieval when the query references an entity from the
        conversation (a genuine follow-up). Returns the retrieved chunks when
        relevant, or ``None`` when the query is not a follow-up, nothing relevant
        is retrieved, or the search fails — so the caller can fall through to the
        knowledge fallback.
        """
        terms = self._extract_contextual_terms(conversation_history)
        if not terms or not self._query_references_context(query, terms):
            return None
        contextual_query = self._build_contextual_search_query(
            query, conversation_history
        )
        if not contextual_query.strip():
            return None
        try:
            chunks = self._searcher.search(contextual_query, top_k=top_k)
        except Exception as exc:
            logger.warning(
                "Contextual re-retrieval failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not self._has_relevant_chunks(chunks):
            return None
        return chunks

    async def _contextual_search_async(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
    ) -> list[dict[str, Any]] | None:
        """Async variant of :meth:`_contextual_search` (uses ``search_async``)."""
        terms = self._extract_contextual_terms(conversation_history)
        if not terms or not self._query_references_context(query, terms):
            return None
        contextual_query = self._build_contextual_search_query(
            query, conversation_history
        )
        if not contextual_query.strip():
            return None
        try:
            if hasattr(self._searcher, "search_async"):
                chunks = await self._searcher.search_async(
                    contextual_query, top_k=top_k
                )
            else:
                chunks = self._searcher.search(contextual_query, top_k=top_k)
        except Exception as exc:
            logger.warning(
                "Contextual re-retrieval failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not self._has_relevant_chunks(chunks):
            return None
        return chunks

    def _generate(self, prompt: str) -> str:
        """Run the LLM synchronously with the pipeline's temperature/max_tokens."""
        return self._llm_provider.generate(
            prompt=prompt,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )

    async def _agenerate(self, prompt: str) -> str:
        """Run the LLM asynchronously (falls back to the sync ``generate``)."""
        if hasattr(self._llm_provider, "agenerate"):
            return await self._llm_provider.agenerate(
                prompt=prompt,
                temperature=self._config.llm_temperature,
                max_tokens=self._config.llm_max_tokens,
            )
        return self._llm_provider.generate(
            prompt=prompt,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )

    def _stream_generate(self, prompt: str, prefix: str = "") -> tuple[str, bool]:
        """Generate a response, streaming through ``_on_chunk`` when possible.

        When streaming is enabled, the provider supports ``stream_chat`` and an
        ``_on_chunk`` callback is registered, ``prefix`` (if any) is emitted
        first and the answer is forwarded token by token. Otherwise falls back
        to the synchronous ``_generate``.

        Returns:
            Tuple of ``(answer, streamed)`` where ``streamed`` indicates the
            output was already pushed through ``_on_chunk`` and the caller must
            not re-emit it.
        """
        can_stream = (
            self._config.streaming_enabled
            and self._on_chunk is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        if not can_stream:
            return self._generate(prompt), False
        if prefix and self._on_chunk:
            self._on_chunk(prefix, None)
        messages = [{"role": "user", "content": prompt}]
        accumulated: list[str] = []

        def on_chunk(content: str, _reasoning: str | None) -> None:
            if content:
                accumulated.append(content)
            if self._on_chunk and (content or _reasoning):
                self._on_chunk(content, _reasoning)

        self._llm_provider.stream_chat(
            messages=messages,
            on_chunk=on_chunk,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )
        return "".join(accumulated), True

    def _is_plausible_summary(self, text: str) -> bool:
        """Detect degenerate/token-soup output (repetitive or low-diversity text).

        Mirrors ``summarizer.Summarizer._is_plausible_summary`` so the RAG chat
        path applies the same guard against context-overflow degeneration that
        the dedicated summariser uses. A genuinely useful answer is non-trivial
        in length and lexically varied; repetitive or single-token-dominated
        output signals that the model ran out of budget and corrupted.
        """
        if not text or len(text.strip()) < 40:
            return False
        if _contains_reasoning_leak(text.lower()):
            return False
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
        if not tokens:
            return False
        counts = Counter(tokens)
        most_common_frac = counts.most_common(1)[0][1] / len(tokens)
        if most_common_frac > 0.4:
            return False
        unique_frac = len(counts) / len(tokens)
        return unique_frac >= 0.2

    @staticmethod
    def _trim_rehashed_tail(text: str) -> str:
        """Drop a trailing re-statement that adds almost no new content.

        When the model emits the same material twice (a second, re-worded pass
        over the same topics), keep only the first pass.  A trailing run is
        treated as redundant when it reuses the earlier coverage without
        introducing new material: either its content words (excluding function
        words) are almost all already covered, or it re-states the same
        proper-noun/technical entities of the preceding text and adds (at most)
        none that are new.  A genuinely progressive summary that adds new topics
        is never cut.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        if len(sentences) < 6:
            return text

        def _terms(piece: str) -> list[str]:
            return [
                w
                for w in re.findall(r"[A-Za-z0-9']+", piece.lower())
                if w not in _FUNCTION_WORDS
            ]

        def _entities(piece: str) -> set[str]:
            # Reliable entities: mid-sentence proper nouns ("LeNet5", "AlexNet")
            # and any technical identifier with a digit ("VGG16", "2012").
            # Sentence-initial capitals ("Here", "Chapter") are not proper nouns.
            ents: set[str] = set()
            for m in re.finditer(r"\b[A-Z][A-Za-z0-9]*\b", piece):
                prefix = piece[: m.start()].rstrip()
                at_sentence_start = (
                    prefix == ""
                    or prefix.endswith((".", "!", "?"))
                    or prefix.endswith("\n")
                )
                token = m.group(0)
                if (not at_sentence_start) or any(c.isdigit() for c in token):
                    ents.add(token.lower())
            for m in re.finditer(r"[A-Za-z0-9]*\d[A-Za-z0-9]*", piece):
                ents.add(m.group(0).lower())
            return ents

        for start in range(len(sentences) // 2, len(sentences) - 1):
            if len(sentences) - start < 3:
                break
            head = set(_terms(" ".join(sentences[:start])))
            rest = _terms(" ".join(sentences[start:]))
            if not rest:
                continue
            novel = sum(1 for w in rest if w not in head) / len(rest)
            if novel < 0.20:
                return " ".join(sentences[:start]).strip()
            head_entities = _entities(" ".join(sentences[:start]))
            tail_entities = _entities(" ".join(sentences[start:]))
            if not tail_entities:
                continue
            overlap = len(tail_entities & head_entities) / len(tail_entities)
            new_entities = tail_entities - head_entities
            if overlap >= 0.7 and len(new_entities) <= 1:
                return " ".join(sentences[:start]).strip()
        return text

    def _generate_guarded(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a chat answer, rerunning once if the output looks degenerate.

        Option C (fail-closed + gibberish guard): if the first response fails
        the plausibility check, retry at a low temperature. If the retry is
        still implausible, return an empty string so the caller can fall back
        to a cleaner default rather than surfacing token-soup to the user.

        *temperature* / *max_tokens* override the default sampling parameters for
        the first call; the retry always uses temperature 0.1.
        """
        temp = temperature if temperature is not None else self._config.llm_temperature
        tokens = max_tokens if max_tokens is not None else self._config.llm_max_tokens
        text = self._llm_provider.generate(
            prompt=prompt,
            temperature=temp,
            max_tokens=tokens,
        )
        if self._is_plausible_summary(text):
            return text
        logger.warning(
            "RAG output failed plausibility check; retrying at low temperature"
        )
        text = self._llm_provider.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=tokens,
        )
        if self._is_plausible_summary(text):
            return text
        logger.error("RAG output still implausible; returning empty")
        return ""

    def _generate_multi_chapter_summary(
        self,
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        """Produce a chapter-by-chapter overview via bounded windows per chapter.

        Chapters whose bucket is empty (page-range detection found no body text
        in their range) are still listed, with an explicit placeholder note, so
        a partial overview is visible to the reader instead of silently
        omitting chapters.
        """
        all_parts: list[str] = []
        for ch_num in chapter_keys:
            bucket = chapter_buckets.get(ch_num)
            title = self._display_chapter_title(ch_titles.get(ch_num, ""))
            heading = f"Chapter {ch_num}" + (f" — {title}" if title else "")
            if not bucket:
                # An empty bucket means the chapter's page range contained no
                # body chunks (usually a mis-pinned start page).  Emit an
                # explicit placeholder: silently omitting chapters made a
                # partial overview look complete.
                note = (
                    "No document content was retrieved for this chapter "
                    "(its detected page range contains no body text), so no "
                    "summary could be generated."
                )
                if self._on_chunk:
                    # The returned text joins blocks with "\n\n"; the live
                    # stream needs its own separators or chapters glue together.
                    self._on_chunk(
                        (f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n")
                        + note,
                        None,
                    )
                all_parts.append(f"{heading}\n\n{note}")
                continue
            if self._on_chunk:
                # The returned text joins blocks with "\n\n"; the live stream
                # needs its own separators or consecutive chapters glue together.
                self._on_chunk(
                    f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n",
                    None,
                )
            instruction = (
                f"Provide a brief, focused summary of {heading} using ONLY the "
                "document content below. 2-4 sentences. Never add information from "
                "outside this document or from prior knowledge. Quote any numbers, "
                "years, statistics, and metrics EXACTLY as they appear in the "
                "content below; never invent, estimate, round, or 'correct' a "
                "figure the source does not state -- if a specific number is not "
                "clearly present, omit it rather than guessing. Do not hedge, "
                "second-guess, or correct figures, and do not reproduce code "
                "details or function arguments (e.g. list(range(...))) verbatim."
            )
            summary = self._summarize_bounded(
                heading=heading,
                windows=self._split_bounded(bucket),
                instruction=instruction,
            )
            if summary.strip():
                all_parts.append(f"{heading}\n\n{summary}")
        return "\n\n".join(all_parts)

    def _generate_single_chapter_summary(
        self,
        chunks: list[dict[str, Any]],
        chapter_num: int | str,
        chapter_title: str,
        *,
        foreign_titles: list[str] | None = None,
    ) -> str:
        """Produce a comprehensive chapter overview via bounded windows.

        The chapter is split into small, character-bounded windows, each is
        condensed into a terse internally-held digest grounded to its own
        source (map), and one final streamed call writes the whole overview
        from the digests in a single voice (reduce) -- so the instruction's
        length bound applies once to the chapter, not once per window. The
        streaming guards (leak scrubbing, dead-stream continuation,
        low-temperature retry) apply to the reduce call; a window whose digest
        is unusable is skipped, never surfaced.
        """
        chunks = self._filter_chunks_to_chapter(
            chunks, chapter_num, foreign_titles=foreign_titles
        )
        windows = self._split_bounded(chunks)
        if not windows:
            return ""
        heading = f"Chapter {chapter_num} (overview)"
        instruction = _CHAPTER_OVERVIEW_INSTRUCTION.format(
            chapter_num=chapter_num, chapter_title=chapter_title
        )
        if self._on_chunk:
            self._on_chunk(f"{heading}:\n\n", None)
        body = self._summarize_bounded(
            heading=heading, windows=windows, instruction=instruction
        )
        if not body.strip():
            return ""
        return f"{heading}:\n\n{body}"

    def _generate_anthology_summary(self, parts: list[dict[str, Any]]) -> str:
        """Produce a part-by-part overview for an anthology document.

        One streamed section per part: the part heading
        (``I.1 — <title> (pages 3\u201313)``) followed by that part's summary
        from the bounded-window machinery, with the part's section roster
        quoted into the prompt as structure-only context.  A part whose
        bucket is empty (its detected page range contained no body text) is
        still listed, with an explicit placeholder note, so a partial
        overview is visible to the reader instead of silently omitting
        parts -- mirroring the legacy multi-chapter generator's behaviour.

        Args:
            parts: Parts in document order, each carrying ``label``,
                ``title``, ``start_page``, ``end_page``, an optional
                ``sections`` roster (prompt context only) and ``chunks``
                (the sampled body chunks for the part).

        Returns:
            The full concatenated answer (one section per part, blocks
            joined with blank lines).
        """
        all_parts: list[str] = []
        for part in parts:
            label = str(part.get("label", "") or "").strip() or "Part"
            # The title is rendered verbatim (stripped only): it comes from a
            # clean opener heading, and ``_display_chapter_title``'s run-on
            # cleanup would truncate legitimate titles that carry short digit
            # tokens (e.g. "Volume 1 — ...").
            title = str(part.get("title", "") or "").strip()
            start_page = part.get("start_page")
            end_page = part.get("end_page")
            heading = label
            if title:
                heading += f" — {title}"
            if start_page is not None and end_page is not None:
                # En dash (U+2013) between the pages, per the design
                # contract's part heading format.
                heading += f" (pages {start_page}–{end_page})"  # noqa: RUF001
            chunks = part.get("chunks") or []
            if not chunks:
                # An empty part means the part's page range contained no
                # body chunks.  Emit an explicit placeholder: silently
                # omitting parts made a partial overview look complete
                # (same rationale as the legacy empty-chapter note).
                note = (
                    "No document content was retrieved for this part (its "
                    "detected page range contains no body text), so no "
                    "summary could be generated."
                )
                if self._on_chunk:
                    # The returned text joins blocks with "\n\n"; the live
                    # stream needs its own separators or parts glue together.
                    self._on_chunk(
                        (f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n")
                        + note,
                        None,
                    )
                all_parts.append(f"{heading}\n\n{note}")
                continue
            if self._on_chunk:
                self._on_chunk(
                    f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n",
                    None,
                )
            part_id = f"{label} ({title})" if title else label
            instruction = _ANTHOLOGY_PART_INSTRUCTION.format(part_id=part_id)
            section_context = self._render_part_sections(part.get("sections"))
            if section_context:
                instruction += "\n\n" + section_context
            summary = self._summarize_bounded(
                heading=heading,
                windows=self._split_bounded(chunks),
                instruction=instruction,
            )
            if not summary.strip():
                note = "A summary could not be generated for this part."
                if self._on_chunk:
                    self._on_chunk(note, None)
                summary = note
            all_parts.append(f"{heading}\n\n{summary}")
        return "\n\n".join(all_parts)

    @staticmethod
    def _render_part_sections(sections: Any) -> str:
        """Render a part's section roster as short prompt context, or ''.

        The section list is orientation only -- it shows the model the
        part's internal structure so the overview can follow it; it must
        stay short, so at most ``_ANTHOLOGY_PART_SECTION_CONTEXT_MAX``
        entries are quoted, with a trailing count when the roster was cut.
        Entries are defensively read as ``{label/number, title}`` dicts;
        anything else contributes nothing.

        Args:
            sections: The part's ``sections`` value as built by the
                per-part map (a list of section dicts), or anything else.

        Returns:
            A one-sentence section list for the prompt, or ``""`` when
            nothing usable was supplied.
        """
        if not isinstance(sections, (list, tuple)):
            return ""
        lines: list[str] = []
        rendered = 0
        for section in sections:
            if len(lines) >= _ANTHOLOGY_PART_SECTION_CONTEXT_MAX:
                break
            rendered += 1
            if not isinstance(section, dict):
                continue
            label = str(section.get("label", section.get("number", "")) or "").strip()
            title = str(section.get("title", "") or "").strip()
            if label and title:
                lines.append(f"{label} {title}")
            elif title or label:
                lines.append(title or label)
        if not lines:
            return ""
        listed = "; ".join(lines)
        remaining = len(sections) - rendered
        if remaining > 0:
            listed += f"; and {remaining} more sections"
        return (
            "For structure only, the part contains these sections: "
            f"{listed}. Use this list to orient the overview's coverage "
            "and order; do not summarize the section list itself item by "
            "item."
        )

    def _generate_whole_document_overview(self, chunks: list[dict[str, Any]]) -> str:
        """Produce an honest whole-document overview from a page-spread sample.

        The fallback for documents whose per-chapter mapping is
        untrustworthy (the chapter-range agreement gate vetoed the legacy
        chapter map): instead of confident wrong-page chapters, the reader
        first gets a short note that per-chapter mapping was unavailable,
        then one whole-document overview built from an evenly spaced sample
        of the body chunks via the bounded-window machinery.

        Args:
            chunks: Body chunks of the scoped document.

        Returns:
            The note line followed by the overview text (or just the note
            when the overview could not be generated).
        """
        note = _WHOLE_DOCUMENT_OVERVIEW_NOTE
        if self._on_chunk:
            self._on_chunk(f"{note}\n\n", None)
        sampled = self._page_spread_sample(chunks)
        summary = self._summarize_bounded(
            heading="this document",
            windows=self._split_bounded(sampled),
            instruction=_WHOLE_DOCUMENT_OVERVIEW_INSTRUCTION,
        )
        if not summary.strip():
            return note
        return f"{note}\n\n{summary}"

    @staticmethod
    def _page_spread_sample(
        chunks: list[dict[str, Any]],
        limit: int = _OVERVIEW_SAMPLE_MAX_CHUNKS,
    ) -> list[dict[str, Any]]:
        """Return an evenly spaced, page-ordered sample of *chunks*.

        The overview fallback must cover the whole document even when the
        full body exceeds the summarizer's budget, so the chunks are sorted
        into document order (page, then within-page position) and an evenly
        spaced subset is taken across that sequence -- deterministic, with
        no randomness, and always including the document's first and last
        chunks.  Inputs at or under *limit* are returned whole.

        Args:
            chunks: Body chunks (each carrying ``page_number``/``page``,
                optionally ``page_pos``).
            limit: Maximum number of chunks to return.

        Returns:
            The sampled chunks in document order.
        """
        if not chunks or limit <= 0:
            return []
        ordered = sorted(
            chunks,
            key=lambda c: (
                c.get("page_number", c.get("page", 0)) or 0,
                c.get("page_pos", 0) or 0,
            ),
        )
        if len(ordered) <= limit:
            return ordered
        if limit == 1:
            return ordered[:1]
        step = (len(ordered) - 1) / (limit - 1)
        picked: list[dict[str, Any]] = []
        seen: set[int] = set()
        for i in range(limit):
            index = round(i * step)
            if index not in seen:
                seen.add(index)
                picked.append(ordered[index])
        return picked

    def _split_bounded(
        self,
        chunks: list[dict[str, Any]],
        *,
        max_chars: int | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Split *chunks* into contiguous windows of bounded source characters.

        Input is sorted into numerical page order (stable, so within-page reading
        order is preserved) before windowing so the emitted summary windows follow
        the document's page sequence rather than retrieval/interleaving order.
        Boundaries are then aligned to sentence ends via
        :meth:`_align_window_boundaries` so no window's source stops mid-sentence.
        """
        ordered = sorted(
            chunks,
            key=lambda c: c.get("page_number", c.get("page", 0)) or 0,
        )
        budget = max_chars or _SUMMARY_WINDOW_CHARS
        windows: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for chunk in ordered:
            text = chunk.get("chunk_text", chunk.get("text", ""))
            if text and current and current_chars + len(text) > budget:
                windows.append(current)
                current = []
                current_chars = 0
            current.append(chunk)
            current_chars += len(text)
        if current:
            windows.append(current)
        return self._align_window_boundaries(windows)

    @staticmethod
    def _align_window_boundaries(
        windows: list[list[dict[str, Any]]],
    ) -> list[list[dict[str, Any]]]:
        """Move the mid-sentence tail of each window to the next window's front.

        Ingest chunking cuts mid-sentence, and a window whose source ends
        mid-sentence makes the summary mirror the truncation: the live stream
        ends mid-word and :func:`_trim_to_sentence_end` later discards the
        tail as wasted generation.  The fragment after the last sentence
        terminal of a window is therefore prepended to the next window.  A
        terminal-free trailing chunk is left alone: carrying whole chunks
        forward could chain-merge every window into one.  Payload dicts are
        copied on modification so the caller's chunks are never mutated.
        """
        for idx in range(len(windows) - 1):
            window = windows[idx]
            if not window:
                continue
            tail = window[-1]
            key = "chunk_text" if "chunk_text" in tail else "text"
            if key not in tail:
                continue
            text = str(tail[key])
            ends = [m.end() for m in re.finditer(r"[.!?][\"'\u201d\u2019]?\s", text)]
            if not ends:
                continue
            remainder = text[ends[-1] :].strip()
            if not remainder:
                continue
            nxt = windows[idx + 1][0]
            nkey = "chunk_text" if "chunk_text" in nxt else "text"
            if nkey not in nxt:
                continue
            trimmed = dict(tail)
            trimmed[key] = text[: ends[-1]].rstrip()
            windows[idx] = [*window[:-1], trimmed]
            merged = dict(nxt)
            merged[nkey] = f"{remainder} {str(nxt[nkey]).lstrip()}"
            windows[idx + 1][0] = merged
        return windows

    def _summarize_bounded(
        self,
        *,
        heading: str,
        windows: list[list[dict[str, Any]]],
        instruction: str,
    ) -> str:
        """Summarize *windows* in one streamed call over the complete source.

        PRIMARY (single pass): when the formatted source fits within
        ``_SINGLE_PASS_MAX_CHARS``, one LLM call receives the whole chapter and
        writes the overview.  This is both cheaper and more faithful than any
        staged pipeline: the per-call reasoning/planning overhead is paid once
        instead of once per window, no intermediate digest can drop detail, and
        there are no per-window seams to recover from.

        FALLBACK (map-reduce, oversized sources only): each window is condensed
        into a terse internal digest (map -- digest content never streams), and
        one final streamed call writes the overview from the digests (reduce).
        A window whose digest is unusable is skipped, never surfaced.
        """
        contexts: list[str] = []
        for window in windows:
            ctx = self._format_context(
                window, max_chars=self._config.rag_max_context_chars
            )
            if ctx.strip():
                contexts.append(ctx)
        if not contexts:
            return ""
        if sum(len(ctx) for ctx in contexts) <= _SINGLE_PASS_MAX_CHARS:
            return self._reduce_digest_overview(
                heading,
                contexts,
                instruction,
                parts_are_digests=False,
                numbered_parts=False,
            )
        if len(windows) > _MAX_MAP_REDUCE_WINDOWS:
            logger.warning(
                "summary source exceeds the single-pass budget and has %d "
                "windows; capping map pass at %d",
                len(windows),
                _MAX_MAP_REDUCE_WINDOWS,
            )
            windows = windows[:_MAX_MAP_REDUCE_WINDOWS]
            contexts = contexts[:_MAX_MAP_REDUCE_WINDOWS]
        digests: list[str] = []
        total = len(contexts)
        for index, ctx in enumerate(contexts, 1):
            digest = self._map_window_digest(heading, ctx, index, total)
            if digest:
                digests.append(digest)
        if not digests:
            return ""
        return self._reduce_digest_overview(
            heading, digests, instruction, parts_are_digests=True
        )

    def _map_window_digest(
        self,
        heading: str,
        ctx: str,
        index: int,
        total: int,
    ) -> str:
        """Condense one source window into an internal, grounded digest.

        The digest is deliberately small so the reduce pass sees a compact,
        faithful skeleton of the chapter instead of a stack of full-window
        essays -- that is what finally makes the overview's deterministic
        length ceiling effective.  Its size is shaped by "terse digest
        paragraph" phrasing rather than a numeric word bound, which would
        only trigger word-counting loops in the model's reasoning.
        Reasoning streams (visible activity) but content stays
        internal. On a stream failure the digest is regenerated once via
        :meth:`_generate_guarded`; an unusable digest is skipped with a warning
        so one bad window cannot stall the whole overview.
        """
        prompt = self._build_prompt(
            (
                f"You are preparing an internal digest of Part {index} of "
                f"{total} of {heading}.\n\nWrite a terse digest paragraph that "
                "records, in source order: the topics the part "
                "covers; every figure or table it presents, quoted with its "
                'exact label (e.g. "Figure 18.5", "Table 18.2") and subject; '
                "and the key numeric results, copied exactly from the source. "
                "Plain prose only -- no headers, bullets, transitions, or "
                "commentary. Never mention page numbers. State each figure "
                "once. Never add anything the source does not contain."
            ),
            ctx,
        )
        can_stream = self._config.streaming_enabled and hasattr(
            self._llm_provider, "stream_chat"
        )
        digest = ""
        if can_stream:
            pieces: list[str] = []
            digest_start = time.monotonic()

            def _fwd_map(chunk: str, reasoning: str | None) -> None:
                if time.monotonic() - digest_start > _WINDOW_MAX_SECONDS:
                    raise TimeoutError("map digest exceeded time budget")
                # Reasoning streams so the user sees live activity; the digest
                # content itself must never reach the screen.
                if reasoning and self._on_chunk:
                    self._on_chunk("", reasoning)
                if chunk:
                    pieces.append(chunk)

            try:
                returned = self._llm_provider.stream_chat(
                    messages=[{"role": "user", "content": prompt}],
                    on_chunk=_fwd_map,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_MAP_DIGEST_MAX_TOKENS,
                )
                digest = "".join(pieces) or (returned or "")
            except Exception as e:
                logger.warning(
                    "map digest stream failed (%s: %s); regenerating",
                    type(e).__name__,
                    e,
                )
        if not digest.strip():
            try:
                digest = self._generate_guarded(
                    prompt,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_MAP_DIGEST_MAX_TOKENS,
                )
            except Exception as e:
                logger.warning(
                    "map digest generation failed (%s: %s); skipping part %d/%d",
                    type(e).__name__,
                    e,
                    index,
                    total,
                )
                return ""
        if not digest.strip():
            return ""
        digest = _strip_numeric_self_correction(_scrub_self_correction(digest))
        digest = _prune_implausible_metric_figures(digest)
        digest = _ground_figures(digest, ctx)
        digest = _trim_to_sentence_end(digest)
        if not digest.strip() or not self._is_plausible_summary(digest):
            logger.warning("map digest %d/%d unusable; skipping", index, total)
            return ""
        return digest

    def _reduce_digest_overview(
        self,
        heading: str,
        parts: list[str],
        instruction: str,
        *,
        parts_are_digests: bool,
        numbered_parts: bool = True,
    ) -> str:
        """Write the final overview from *parts* in one streamed LLM call.

        Serves both summary paths: the single-pass primary (raw source parts,
        ``numbered_parts=False``) and the map-reduce reduce stage (terse
        digests, numbered in reading order).  When the digest count exceeds
        ``_HIERARCHY_THRESHOLD``, the digests are first condensed into balanced
        groups so the reduce prompt stays readable.

        A single call is what gives the overview one voice, an effective
        length bound, and no per-window seams. All streaming guards apply here:
        withheld-tail leak scrubbing, dead-stream continuation, and the
        low-temperature retry. Two GLM failure modes that raise no exception
        are handled explicitly below: a normal return whose content was
        amputated mid-sentence by the server output cap, and a normal return
        with no content at all.
        """
        emit = self._on_chunk
        can_stream = (
            self._config.streaming_enabled
            and emit is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        grounding_context = "\n\n".join(parts)
        if parts_are_digests and len(parts) > _HIERARCHY_THRESHOLD:
            # Grounding keeps the raw digests (best figure fidelity); only the
            # reduce prompt switches to the condensed groups.
            parts = self._condense_digest_groups(heading, parts)
        if numbered_parts:
            joined = "\n\n".join(
                f"--- Part {i} ---\n{p}" for i, p in enumerate(parts, 1)
            )
        else:
            joined = "\n\n".join(parts)
        if parts_are_digests:
            framing = (
                "The document content below consists of terse digests of the "
                f"consecutive parts of {heading}, in reading order. Write the "
                "final overview as ONE coherent piece of prose that weaves the "
                "digests into a single narrative: cover every part in order "
                "with one consistent voice; never use per-part headers or "
                "'Part N' labels; never name a figure or table the digests do "
                "not contain, and when you do cite one, quote its label "
                "exactly as the digests give it; never mention page numbers; "
                "end on a complete statement."
            )
        else:
            framing = (
                f"The document content below covers {heading}. Write the final "
                "overview as ONE coherent piece of prose with one consistent "
                "voice: never name a figure or table the content does not "
                "contain, and when you do cite one, quote its label exactly "
                "as the content gives it; never mention page numbers; end on "
                "a complete statement."
            )
        prompt = instruction + "\n\n" + framing + "\n\n" + joined

        if not can_stream:
            try:
                text = self._generate_guarded(
                    prompt,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
                )
            except Exception as e:
                logger.warning("summary reduce failed (%s: %s)", type(e).__name__, e)
                return ""
            final = self._finalize_overview(text, grounding_context)
            if not final.strip() or not self._is_plausible_summary(final):
                return ""
            if emit:
                # Non-streaming mode still surfaces the completed overview through
                # the callback so the chat shows progressive output.
                emit(f"\n\n{final}\n\n", None)
            return final

        pieces: list[str] = []
        reduce_start = time.monotonic()
        # Withhold a short tail of streamed content so a self-correction leak
        # is caught on the buffered text before it reaches the screen.
        hold: list[str] = [""]
        flushed = [0]

        def _emit_streamed(text: str) -> None:
            if text and emit:
                emit(text, None)

        def _flush_hold() -> None:
            # `flushed` must advance with the emission: the leak scrubber's
            # already-emitted-prefix comparison depends on it staying exact.
            if hold[0]:
                flushed[0] += len(hold[0])
                _emit_streamed(hold[0])
                hold[0] = ""

        def _fwd(chunk: str, reasoning: str | None) -> None:
            if time.monotonic() - reduce_start > _WINDOW_MAX_SECONDS:
                raise TimeoutError("summary reduce exceeded time budget")
            if reasoning and emit:
                emit("", reasoning)
            if not chunk:
                return
            pieces.append(chunk)
            hold[0] += chunk
            joined = "".join(pieces)
            if _is_stream_leak(joined.lower()):
                # A scrubbable leak confined to the withheld tail is cut out
                # and streaming continues; only a leak that would alter
                # already-emitted text (or resists scrubbing) aborts the
                # overview to the retry path.
                scrubbed = _scrub_self_correction(joined)
                if (
                    scrubbed != joined
                    and scrubbed[: flushed[0]] == joined[: flushed[0]]
                    and not _is_stream_leak(scrubbed.lower())
                ):
                    pieces.clear()
                    pieces.append(scrubbed)
                    hold[0] = scrubbed[flushed[0] :]
                    return
                raise _StreamLeakError()
            if len(hold[0]) > _STREAM_LEAK_HOLD:
                committed = hold[0][:-_STREAM_LEAK_HOLD]
                hold[0] = hold[0][-_STREAM_LEAK_HOLD:]
                _emit_streamed(committed)
                flushed[0] += len(committed)

        text = ""
        try:
            returned = self._llm_provider.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                on_chunk=_fwd,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
            _flush_hold()
            text = "".join(pieces) or (returned or "")
            if text and not pieces:
                # A provider that returned the whole text without streaming
                # chunks: seed the buffer so a follow-up continuation extends
                # this draft instead of dropping it.
                pieces.append(text)
        except _StreamLeakError:
            # The overview leaked an inline self-correction into content:
            # regenerate rather than ship it. Pre-leak chunks may already be
            # on screen; the retry replaces the draft.
            text = ""
        except Exception as e:  # the stream died mid-flight; recover it
            logger.warning(
                "summary reduce stream aborted (%s: %s)", type(e).__name__, e
            )
            text = "".join(pieces)
            _flush_hold()
            if text.strip():
                # Idle-timeout stalls and provider drops kill long
                # reasoning-heavy generations mid-sentence; one streamed
                # continuation completes the draft so the overview is not
                # silently truncated.
                self._resume_summary(prompt, text, _fwd)
                _flush_hold()
                text = "".join(pieces)

        if not text.strip():
            # Covers both a stream that died before any content and the GLM
            # "normal" empty return (reasoning consumed the whole output
            # budget): one clean regeneration before the overview is abandoned.
            retry = self._low_temp_retry(
                prompt, True, heading, max_tokens=_SUMMARY_REDUCE_MAX_TOKENS
            )
            if retry is None:
                return ""
            # _fwd must operate on the adopted draft so a follow-up
            # continuation extends it instead of resurrecting dead pieces.
            pieces.clear()
            pieces.append(retry)
            hold[0] = ""
            flushed[0] = len(retry)
            text = retry

        if not _ends_on_sentence(text):
            # GLM-class servers cap thinking+content with one output budget and
            # can return "normally" with the content amputated mid-sentence --
            # no exception reaches the handler above. A streamed continuation
            # completes the draft so the overview does not end mid-word.
            self._resume_summary(prompt, text, _fwd)
            _flush_hold()
            text = "".join(pieces)

        return self._finalize_or_retry_overview(
            text,
            prompt=prompt,
            heading=heading,
            grounding_context=grounding_context,
        )

    def _condense_digest_groups(self, heading: str, digests: list[str]) -> list[str]:
        """Condense a large digest set into balanced groups for the reduce prompt.

        ``len(digests)`` is split into the fewest groups whose size stays within
        ``_HIERARCHY_GROUP_SIZE`` (balanced sizes, no singleton trailing group),
        and each group is merged into one terser digest by a non-streamed call.
        A group whose condensation fails or reads as garbage falls back to its
        raw digests, so a failed optimization call cannot lose coverage.
        """
        n = len(digests)
        n_groups = -(-n // _HIERARCHY_GROUP_SIZE)
        size = -(-n // n_groups)
        merged: list[str] = []
        for start in range(0, n, size):
            group = digests[start : start + size]
            condensed = self._condense_digest_group(heading, group)
            merged.append(condensed if condensed.strip() else "\n\n".join(group))
        return merged

    def _condense_digest_group(self, heading: str, group: list[str]) -> str:
        """Merge one group of digests into a single terser digest, or '' on failure."""
        prompt = self._build_prompt(
            (
                f"You are condensing intermediate digests of {heading}.\n\nThe "
                "digests below cover consecutive parts in reading order. Merge "
                "them into ONE terser digest that preserves, in source order: "
                "every topic; every figure or table label, quoted exactly as "
                "the digests give it; and every numeric result, copied exactly "
                "from the digests. Plain prose only -- no headers, bullets, or "
                "commentary. Never mention page numbers. Never add anything "
                "the digests do not contain."
            ),
            "\n\n".join(f"--- Digest {i} ---\n{d}" for i, d in enumerate(group, 1)),
        )
        try:
            condensed = self._generate_guarded(
                prompt,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning(
                "digest group condensation failed (%s: %s); passing raw digests",
                type(e).__name__,
                e,
            )
            return ""
        condensed = _strip_numeric_self_correction(_scrub_self_correction(condensed))
        condensed = _prune_implausible_metric_figures(condensed)
        condensed = _ground_figures(condensed, "\n\n".join(group))
        condensed = _trim_to_sentence_end(condensed)
        if not condensed.strip() or not self._is_plausible_summary(condensed):
            return ""
        return condensed

    def _finalize_or_retry_overview(
        self,
        text: str,
        *,
        prompt: str,
        heading: str,
        grounding_context: str,
    ) -> str:
        """Ground and trim the reduced overview, regenerating once if degenerate."""
        final = self._finalize_overview(text, grounding_context)
        if not final.strip():
            return ""
        if not self._is_plausible_summary(final):
            retry = self._low_temp_retry(
                prompt, True, heading, max_tokens=_SUMMARY_REDUCE_MAX_TOKENS
            )
            if retry is not None:
                final = self._finalize_overview(retry, grounding_context)
        return final

    @staticmethod
    def _finalize_overview(text: str, grounding_context: str) -> str:
        """Apply the deterministic post-passes to a reduced overview.

        Scrubbing, metric pruning, figure grounding against *grounding_context*
        (the digests, or the raw source for a single-pass overview), the
        deterministic word ceiling, and sentence-end trimming mean a leaked or
        fabricated figure still cannot ship and an overlong draft is cut at a
        sentence boundary rather than trusted to the model's own counting.
        """
        text = _strip_numeric_self_correction(_scrub_self_correction(text))
        text = _prune_implausible_metric_figures(text)
        text = _ground_figures(text, grounding_context)
        text = _trim_to_word_budget(text, _OVERVIEW_MAX_WORDS)
        return _trim_to_sentence_end(text)

    def _resume_summary(
        self,
        prompt: str,
        partial: str,
        on_chunk: Callable[[str, str | None], None],
    ) -> None:
        """Stream a continuation that completes an overview cut off mid-sentence.

        Provider drops, idle-timeout stalls, and the server-side output cap of
        reasoning models (thinking and content share one token budget, so
        content can be amputated with a normal, exception-free return) all
        truncate long generations mid-sentence; regenerating from scratch would
        repeat minutes of thinking, so the model is shown its own draft and
        asked to continue seamlessly. Chunks flow through the caller's
        ``on_chunk`` guard, so leak scrubbing, hold buffering, and the time
        budget keep applying. Failures are logged and swallowed: the caller
        keeps the partial draft.
        """
        resume_prompt = (
            prompt + "\n\nYour draft was cut off mid-sentence before it could "
            "finish. Draft so far:\n<draft>\n"
            + partial
            + "\n</draft>\nContinue seamlessly from that exact point: first "
            "complete the unfinished sentence, then finish the overview, "
            "ending on a complete statement. Output ONLY the continuation -- "
            "never repeat text already present in the draft."
        )
        try:
            self._llm_provider.stream_chat(
                messages=[{"role": "user", "content": resume_prompt}],
                on_chunk=on_chunk,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
            logger.info(
                "overview continuation completed: draft extended by %d "
                "characters after a mid-sentence cutoff",
                len(partial),
            )
        except Exception as e:
            logger.warning(
                "summary continuation failed (%s: %s); keeping partial",
                type(e).__name__,
                e,
            )

    @staticmethod
    def _detect_section_label(text: str, chapter_num: int | str) -> str | None:
        """Return the section key (e.g. ``"18.2"``) a chunk belongs to, if any.

        Only honours a section number that appears at a *heading* position (start
        of the chunk or start of a line), where true section headers live.  A
        line-start ``18.N`` is ignored when the preceding text is a
        figure/table/equation/listing reference (e.g. a wrapped "Figure [newline]
        18.2"), which would otherwise fabricate phantom sections from captions;
        such content folds into the chapter overview.
        """
        chapter_s = str(chapter_num)
        heading_re = re.compile(rf"(?:^|\n)\s*{re.escape(chapter_s)}\.(\d+)\b")
        ref_indicator = re.compile(
            r"(figure|table|equation|listing|eq\.?|page|p\.)\s*$",
            re.IGNORECASE,
        )
        for m in heading_re.finditer(text):
            if ref_indicator.search(text[: m.start()]):
                continue
            return f"{chapter_s}.{m.group(1)}"
        return None

    @staticmethod
    def _leading_section_chapter(text: str) -> str | None:
        """Return the chapter number of the first real numbered heading in *text*.

        Mirrors ``_detect_section_label``'s heading-position guard: only a section
        number at the start of the chunk or start of a line counts, and a
        line-start number that directly follows a figure/table/equation/listing
        reference (e.g. a wrapped "Figure [newline] 18.2") is ignored as a
        caption.  Unlike ``_detect_section_label`` this is chapter-agnostic, which
        lets us attribute a chunk to *whatever* chapter its section heading names.
        """
        heading_re = re.compile(r"(?:^|\n)\s*(\d+)\.\d+(?:\.\d+)?\b")
        ref_indicator = re.compile(
            r"(figure|table|equation|listing|eq\.?|page|p\.)\s*$",
            re.IGNORECASE,
        )
        for m in heading_re.finditer(text):
            if ref_indicator.search(text[: m.start()]):
                continue
            return m.group(1)
        return None

    @staticmethod
    def _filter_chunks_to_chapter(
        chunks: list[dict[str, Any]],
        chapter_num: int | str,
        foreign_titles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Drop retrieved chunks that belong to a *later* chapter.

        ``final_chunks`` for a single-chapter target is collected by page range,
        and page-range boundaries are imperfect, so the next chapter's content
        can leak into the target chapter's bucket.  This filter removes each
        chunk whose numbered section heading belongs to another chapter or whose
        opening line names another chapter's title, and also drops every chunk
        on or after the first page that opens with an explicitly later "Chapter
        N" heading -- which clears the next chapter's body paragraphs that carry
        no section prefix of their own.
        """
        chapter_s = str(chapter_num)
        target_n = int(chapter_s) if str(chapter_s).isdigit() else None
        seen_foreign = {f.strip().lower() for f in (foreign_titles or []) if f.strip()}
        title_starts = [" ".join(t.split()[:4]) for t in seen_foreign]
        ch_open_re = re.compile(r"^(?:Chapter|Module|Lesson)\s+(\d+)\b", re.IGNORECASE)
        printed_page_re = re.compile(r"^\[\s*\d{1,4}\s*\]\s*")

        def _opens_heading_after(text: str) -> bool:
            if target_n is None:
                return False
            s = printed_page_re.sub("", text.lstrip(), count=1).lstrip()
            hm = ch_open_re.match(s)
            if hm and int(hm.group(1)) > target_n:
                return True
            first_line = (s.splitlines()[0] if s else "").strip()
            return (
                first_line.isdigit()
                and 1 <= int(first_line) <= 30
                and int(first_line) > target_n
            )

        def _opens_foreign_title(text: str) -> bool:
            if not title_starts:
                return False
            low = text.lstrip().lower()
            return any(low.startswith(t) for t in title_starts)

        def _page(c: dict[str, Any]) -> int:
            return int(c.get("page_number", c.get("page", 0)) or 0)

        anchor = min(
            (
                _page(c)
                for c in chunks
                if _opens_heading_after(c.get("chunk_text", c.get("text", "")))
            ),
            default=None,
        )
        cutoff = anchor if (anchor is not None and anchor > 1) else None
        kept: list[dict[str, Any]] = []
        for c in chunks:
            text = c.get("chunk_text", c.get("text", ""))
            lead = _FallbackMixin._leading_section_chapter(text)
            if lead is not None and lead != chapter_s:
                continue
            if _opens_foreign_title(text):
                continue
            if cutoff is not None and _page(c) >= cutoff:
                continue
            kept.append(c)
        return kept

    def _map_reduce_stream(
        self,
        items: list[tuple[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        """Stream map-reduce window generations in order and concatenate.

        *items* is a list of ``(heading, prompt)`` pairs.  Fan-out is guarded to
        ``_MAX_MAP_REDUCE_WINDOWS`` — a generous safety ceiling against a
        pathologically large source, not a normal truncation limit — so all
        legitimate windows are processed in full.

        Each window runs through :meth:`_generate_window_guarded`, which streams
        its ``heading``, reasoning, and content live to ``_on_chunk`` so the
        interactive chat progresses in real time.  Content is validated for
        plausibility as it flows (a runaway tail aborts the stream) and once more
        on completion — a degenerate window is retried at a low temperature or
        skipped, never surfaced in the final answer.

        ``temperature`` optionally overrides the sampling temperature for every
        window (used by the summary path to keep figure-heavy output faithful).

        Returns the concatenated answer (falling back to it when no content was
        streamed at all).
        """
        if not items:
            return ""
        capped = items[:_MAX_MAP_REDUCE_WINDOWS]
        parts: list[tuple[str, str]] = []
        for heading, prompt in capped:
            summary = self._trim_rehashed_tail(
                self._generate_window_guarded(prompt, heading, temperature=temperature)
            )
            if summary:
                parts.append((heading, summary))
        return "\n\n".join(f"{h}\n{s}" for h, s in parts)

    def _generate_window_guarded(
        self,
        prompt: str,
        heading: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate one map-reduce window, streaming reasoning and content live.

        In a streaming-enabled session, the heading is emitted first and then
        reasoning + content tokens are forwarded to ``_on_chunk`` as they arrive,
        so the chat streams in real time instead of buffering a whole window.
        Sampling uses ``llm_temperature`` / ``llm_max_tokens`` (unless overridden).

        A mid-stream flood guard detects derailment as it accumulates and
        **aborts the stream immediately**, so a runaway window cannot stream an
        unbounded number of tokens.  Because a derailed window's clean prefix is
        truncated (it ends at the degradation point), the window is **retried at
        temperature 0.1** so a complete, stable summary replaces the partial —
        otherwise a chapter that degrades midway would silently lose every
        section that followed.  When the retried window still degenerates, it is
        skipped, so token-soup never reaches the user.

        Returns the validated answer text (or an empty string when skipped), and
        streams the ``heading`` + answer through ``_on_chunk`` on success.
        """
        temp = temperature if temperature is not None else self._config.llm_temperature
        tokens = max_tokens if max_tokens is not None else self._config.llm_max_tokens

        can_stream = (
            self._config.streaming_enabled
            and self._on_chunk is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        if not can_stream:
            answer = self._generate_guarded(prompt, temperature=temp, max_tokens=tokens)
            if answer and self._on_chunk:
                self._on_chunk(f"{heading}\n\n{answer}\n\n", None)
            return answer

        sink = _WindowStreamSink(
            heading,
            is_reasoning_spiral=self._is_reasoning_spiral,
            is_flooding=self._is_flooding,
            on_chunk=self._on_chunk,
        )
        try:
            self._llm_provider.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                on_chunk=sink,
                temperature=temp,
                max_tokens=tokens,
            )
        except _StreamAbortError:
            sink.aborted = True
        except (ServiceUnavailableError, RuntimeError) as e:
            # A stalled or errored stream (provider idle-timeout, API error, read
            # failure) must not surface as a hard failure after a long silence;
            # treat it like a derail so the window is regenerated deterministically.
            logger.warning(
                "RAG window stream degraded (%s: %s); regenerating at low temperature",
                type(e).__name__,
                e,
            )
            sink.aborted = True

        return self._resolve_window_answer(sink, prompt, heading, tokens)

    def _resolve_window_answer(
        self,
        sink: _WindowStreamSink,
        prompt: str,
        heading: str,
        tokens: int,
    ) -> str:
        """Turn a finished window stream into the answer text (or skip it).

        A window that derailed mid-stream is incomplete: the clean prefix ends
        at the degradation point, dropping whatever the chapter covered after
        it.  Retry at low temperature to salvage a complete, stable summary
        instead of surfacing a chapter cut off mid-way.  Only when the retry is
        also unusable do we fall back to the clean prefix (or skip).
        """
        if sink.aborted:
            logger.warning(
                "RAG window degraded mid-stream; retrying at low temperature for a complete summary"
            )
            retry = self._low_temp_retry(
                prompt, sink.heading_shown, heading, max_tokens=tokens
            )
            if retry is not None:
                return retry

        # Word-salad is judged on this COMPLETED window — reliable, unlike a
        # mid-stream partial — so a legitimate dense summary passes here, while a
        # genuine whole-window salad falls through to a low-temperature retry below.
        text = sink.text
        if self._is_plausible_summary(text) and not self._looks_derailed(text):
            return text
        logger.warning(
            "RAG window derailed before producing usable content; retrying at low temperature"
        )
        retry = self._low_temp_retry(
            prompt, sink.heading_shown, heading, max_tokens=_RETRY_MAX_TOKENS
        )
        if retry is not None:
            return retry
        logger.warning("RAG window output still implausible; skipping section")
        return ""

    def _low_temp_retry(
        self,
        prompt: str,
        heading_shown: bool,
        heading: str,
        *,
        max_tokens: int,
    ) -> str | None:
        """Regenerate a window at temperature 0.1 and return it if acceptable.

        Used when a window degrades (derails mid-stream or is implausible as a
        whole) so the caller can surface a complete, stable summary rather than
        a truncated or degenerate one.  Returns ``None`` when the retry is also
        unacceptable, so the caller decides the fallback.
        """
        # Attempt 1 asks for exact source figures, which the model can obsess over
        # and burn its reasoning budget on; relax that pressure on the retry so it
        # can actually complete a summary instead of looping again.
        retry_prompt = (
            prompt
            + "\n\nYour previous attempt became stuck re-verifying exact figures. "
            "Write a complete, confident overview now: state key numbers once, "
            "approximate values are acceptable. Do not try to confirm, re-derive, "
            "or second-guess any value -- present a flowing summary and finish."
        )
        try:
            retry = self._llm_provider.generate(
                prompt=retry_prompt,
                temperature=0.1,
                max_tokens=max_tokens,
            )
        except Exception as e:
            # Best-effort by contract: a provider timeout or transport error
            # here must never crash the surrounding summary loop.
            logger.warning(
                "RAG window retry failed (%s: %s); skipping window",
                type(e).__name__,
                e,
            )
            return None
        if _is_stream_leak(retry.lower()):
            logger.warning(
                "RAG window retry still leaked a self-correction; skipping window"
            )
            return None
        if not self._is_acceptable(retry):
            logger.warning("RAG window retry unacceptable; skipping window")
            return None
        if self._on_chunk:
            if heading_shown:
                self._on_chunk(f"\n\n{retry}\n\n", None)
            else:
                self._on_chunk(f"{heading}\n\n{retry}\n\n", None)
        return retry

    def _is_acceptable(self, text: str) -> bool:
        """Return True when a window answer is safe to surface.

        An answer is acceptable only if it is plausible (non-repetitive, adequately
        long) *and* has not derailed into agrammatic word-salad — the high-diversity
        degeneration that repetition-based checks alone miss.
        """
        return self._is_plausible_summary(text) and not self._looks_derailed(text)

    def _is_flooding(self, text: str) -> bool:
        """Return True once a live-streaming window degenerates into repetition.

        A stream must be aborted only on a genuine runaway tail — repetitive or
        single-token-dominated output (:meth:`_is_plausible_summary`).  It must
        NOT consult :meth:`_looks_derailed`: that word-salad diversity heuristic
        false-positives on the high-diversity partial buffer of a *legitimate*
        dense technical summary (a list of model/technique names spiking
        type-token ratio), so using it here truncates good summaries mid-sentence.
        Word-salad is judged on a whole completed window (the low-temperature
        retry path), never as a streaming abort signal.

        A short buffer is never treated as flooding so the first sentence of a
        normal summary always streams.
        """
        if len(text.strip()) < _STREAM_FLOOD_MIN_CHARS:
            return False
        return not self._is_plausible_summary(text)

    def _is_reasoning_spiral(self, reasoning: str) -> bool:
        """Return True when chain-of-thought reasoning has degenerated.

        Reasoning that derails (the "thinking spiral" that can also leak into the
        final answer) reveals itself by dense, repeated first-person
        self-verification: a stream of "No... wait... actually... let me re-read...
        misread" hedges, and/or an unbounded string of implausible metric guesses
        ("above 98%? No, above 103%?").  A short, normal planning block is never
        treated as a spiral — this requires a long, hedge-dense, or
        impossible-figure reasoning run.
        """
        if not reasoning or len(reasoning) < 400:
            return False
        low = reasoning.lower()
        words = re.findall(r"[a-z']+", low)
        if not words:
            return False
        hedges = len(
            re.findall(
                r"\b(no\b|wait\b|actually\b|hmm\b|hold on\b|correction\b|"
                r"misread\b|re-?read\b|re-?check\b|check again\b|let me look\b|"
                r"let me trace\b|i mis\b)",
                low,
            )
        )
        if hedges >= 10 and hedges / len(words) >= 0.12:
            return True
        above = [int(n) for n in re.findall(r"above\s+(\d+)\s*(?:percent|%)", low)]
        return bool(len(above) >= 4 and max(above) > 100)

    def _looks_derailed(self, text: str) -> bool:
        """Return True when a trailing span of text is rambling word-salad.

        Two complementary signals over the most recent tokens:

        - **Function-word share**: a genuine summary (even dense technical
          writing) keeps a steady share of determiners/prepositions/auxiliaries;
          a pure agrammatic degeneration crams content words together with
          almost none.
        - **Type-token ratio**: a derailment often keeps enough function words to
          hide from the ratio above, yet churns out an almost unbroken run of
          novel words, so nearly every recent token is unique — never true of
          prose, which reuses terms and closed-class words.
        """
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())[-120:]
        if len(tokens) < 40:
            return False
        function_count = sum(1 for t in tokens if t in _FUNCTION_WORDS)
        fn_ratio = function_count / len(tokens)
        if fn_ratio < _DERAIL_FUNCTION_WORD_RATIO:
            return True
        type_token_ratio = len(set(tokens)) / len(tokens)
        # Novel-rambling counts only when it is also low in function words, so it
        # cannot fire on a legitimate but diverse/terse summary.
        return (
            type_token_ratio > _DERAIL_TYPE_TOKEN_RATIO
            and fn_ratio < _DERAIL_TTR_FN_GATE
        )

    @staticmethod
    def _no_result_notice(query: str) -> str:
        """Return the static notice when no relevant documents are found."""
        return f"I couldn't find relevant documents for your query: {query}"

    @staticmethod
    def _apply_llm_fallback(notice: str, llm_answer: object) -> str:
        """Append a non-empty LLM answer to the static *notice*."""
        if isinstance(llm_answer, str) and llm_answer.strip():
            return f"{notice}\n\n{llm_answer}"
        return notice

    def _build_knowledge_fallback_prompt(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build a self-contained instruction prompt for the LLM knowledge fallback.

        The prompt explains that no matching documents exist in the local
        knowledge base and instructs the model to answer using the supplied
        conversation context (if any) and its own general knowledge — or to
        honestly state it has no information.

        When ``conversation_history`` is provided and non-empty, a
        "Relevant conversation context" section (built with
        :meth:`_format_history`) is inserted before the no-documents
        instructions so a multi-turn follow-up can leverage earlier turns in the
        chat session. When it is None/empty, the prompt is stateless and matches
        the original single-turn behaviour exactly.

        Args:
            query: The user's original query.
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session to give the
                model conversational context.

        Returns:
            The instruction prompt to send to the LLM.
        """
        conversation_section = ""
        if conversation_history:
            formatted = self._format_history(conversation_history)
            if formatted:
                conversation_section = (
                    "Relevant conversation context (from this chat session):\n"
                    f"{formatted}\n\n"
                )
        return (
            f"The user asked: {query}\n\n"
            f"{conversation_section}"
            "There are no matching documents for this question in the local "
            "knowledge base, so no retrieved context is available.\n"
            "Using ONLY the conversation context above and your own general "
            "knowledge, answer THE user's CURRENT question stated at the top - "
            "not earlier questions in the conversation context, and not the "
            "prior topic if the user has changed subjects. If you do NOT have "
            "enough information, reply with a short, honest statement that you "
            "do not have information on it. Do not fabricate facts or present "
            "guesswork as established knowledge."
        )

    def _build_contextual_search_query(
        self, query: str, conversation_history: list[dict[str, Any]] | None = None
    ) -> str:
        """Derive an augmented retrieval query from recent conversation terms.

        Appends distinctive named entities and technical tokens (e.g. a person
        name and a hyphenated term such as "ADOS-2") extracted from the most
        recent conversation turns so a multi-turn follow-up like "what
        challenges will brian face..." can retrieve the source document for the
        actual entity (Brian Hand / an ADOS-2 report), rather than relying on a
        generic knowledge answer.

        Args:
            query: The user's latest (rewritten) query.
            conversation_history: Recent conversation messages.

        Returns:
            The *query* augmented with extracted terms, or *query* unchanged
            when no usable history/terms are available.
        """
        terms = self._extract_contextual_terms(conversation_history)
        if not terms:
            return query
        return f"{query} {' '.join(terms)}"

    def _extract_contextual_terms(
        self,
        conversation_history: list[dict[str, Any]] | None,
        max_terms: int = 5,
        recent_turns: int = 20,
    ) -> list[str]:
        """Extract the most distinctive entity/technical terms from conversation.

        Counts occurrences of multi-word proper nouns and hyphenated tokens
        containing digits (e.g. "ADOS-2") across the recent *recent_turns*
        messages, preferring terms that recur — repeated entities are the most
        likely subject — so an entity established several turns back is still
        captured. Sentence-leading filler words are skipped. Technical tokens
        get a small boost since they are strong document discriminators.

        Args:
            conversation_history: Recent conversation messages.
            max_terms: Maximum number of terms to return.
            recent_turns: How many of the most recent messages to scan.

        Returns:
            At most *max_terms* unique terms, ranked by descending frequency
            with ties broken by first appearance, or an empty list.
        """
        if not conversation_history:
            return []
        text = "\n".join(
            m.get("content", "") for m in conversation_history[-recent_turns:]
        )
        filler = {
            "The",
            "According",
            "Based",
            "Yes",
            "This",
            "That",
            "Since",
            "Using",
            "Please",
            "Note",
            "As",
            "Our",
            "Do",
            "Not",
            "Only",
            "There",
            "I",
            "You",
            "Your",
            "If",
            "In",
            "On",
            "For",
            "A",
            "An",
            "But",
            "And",
            "So",
            "It",
            "We",
            "Or",
            "Because",
            "Regarding",
        }
        names = [
            n
            for n in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text)
            if n.split()[0] not in filler
        ]
        technical = re.findall(r"[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9]*[0-9]+\b", text)
        technical_set = set(technical)
        counts = Counter(names + technical)
        seen: dict[str, int] = {}
        for token in names + technical:
            seen.setdefault(token, len(seen))

        def _rank(token: str) -> tuple[int, int]:
            boost = 1 if token in technical_set else 0
            return (-(counts[token] + boost), seen[token])

        ranked = sorted(counts, key=_rank)
        return ranked[:max_terms]

    def _query_references_context(self, query: str, terms: list[str]) -> bool:
        """Whether *query* refers to any entity named by an extracted term.

        Restricts the grounded re-retrieval to genuine multi-turn follow-ups,
        which reference an entity established in earlier turns (e.g. a follow-up
        about "brian" cites the extracted "Brian Hand"). A fresh, self-contained
        question such as "what is the speed of light" shares no tokens with the
        history terms and must not be re-queried with unrelated conversation
        topics, which would otherwise return irrelevant-but-high-scoring chunks.

        Args:
            query: The user's latest query.
            terms: Contextual terms extracted from the conversation history.

        Returns:
            True if the query references a history entity, False otherwise.
        """
        lowered = query.lower()
        for term in terms:
            for token in term.split():
                base = token.lower().rstrip("'s").split("-")[0]
                if len(base) >= 3 and base in lowered:
                    return True
        return False

    def _save_turn(
        self,
        session: ConversationSession,
        query: str,
        answer: str,
    ) -> None:
        """Persist one chat turn (user message + assistant answer) to a session.

        All ``chat()`` exit paths call this so that follow-up turns always see
        the most recent exchange, even when the answer came from a no-source
        fallback path (which otherwise would not be recorded).
        """
        if not answer or not answer.strip():
            return
        session.add_message("user", query)
        session.add_message("assistant", answer)

    def _grounded_context_retry(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any] | None:
        """Re-query the vector DB with a context-augmented query.

        Only attempted when the query references an entity from the
        conversation (a genuine follow-up). If relevant chunks are found,
        return a dict with a grounded RAG answer. Returns None when the query is
        not a follow-up or nothing relevant is retrieved, so the caller can use
        the knowledge fallback.
        """
        chunks = self._contextual_search(query, conversation_history, top_k)
        if chunks is None:
            return None
        context_text = self._format_context(chunks)
        prompt = self._build_prompt(query, context_text, conversation_history or [])
        try:
            answer, streamed = self._stream_generate(prompt)
        except Exception as exc:
            logger.warning(
                "Grounded generation failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not answer or not answer.strip():
            return None
        if not streamed and self._on_chunk and answer:
            self._on_chunk(answer, None)
        result: dict[str, Any] = {
            "answer": answer,
            "query": query,
            "rewritten_query": query,
            "grounded_retry": True,
        }
        if show_sources:
            result["sources"] = chunks
        return result

    async def _grounded_context_retry_async(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any] | None:
        """Async variant of :meth:`_grounded_context_retry`.

        Identical contract (returns a grounded answer dict if the query is a
        follow-up referencing history and relevant chunks are found, else None)
        but uses the provider's async ``search_async``/``agenerate`` when
        available, falling back to the sync equivalents otherwise.
        """
        chunks = await self._contextual_search_async(query, conversation_history, top_k)
        if chunks is None:
            return None
        context_text = self._format_context(chunks)
        prompt = self._build_prompt(query, context_text, conversation_history or [])
        try:
            answer = await self._agenerate(prompt)
        except Exception as exc:
            logger.warning(
                "Grounded generation failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not answer or not answer.strip():
            return None
        result: dict[str, Any] = {
            "answer": answer,
            "query": query,
            "rewritten_query": query,
            "grounded_retry": True,
        }
        if show_sources:
            result["sources"] = chunks
        return result

    def _relevance_gate_threshold(self, source_filter: str | None) -> float | None:
        """Return the relevance-gate threshold for the current retrieval scope.

        Scoped retrieval (``source_filter`` set) means the user's query
        explicitly names an ingested document — strong intent whose raw query
        string carries path tokens that pollute the embedding and depress its
        score against the document's own chunks — so the gate relaxes to
        ``rag_scoped_min_similarity_threshold``. Unscoped retrieval keeps the
        global ``rag_min_similarity_threshold`` (returned as ``None`` so
        :meth:`_has_relevant_chunks` falls back to its default).

        Args:
            source_filter: Resolved source_file filter, or ``None`` for
                unscoped (whole-knowledge-base) retrieval.

        Returns:
            The score floor to pass to :meth:`_has_relevant_chunks`, or
            ``None`` to use its configured default.
        """
        return (
            self._config.rag_scoped_min_similarity_threshold if source_filter else None
        )

    def _has_relevant_chunks(
        self,
        chunks: list[dict[str, Any]],
        threshold: float | None = None,
    ) -> bool:
        """Return True if any retrieved chunk meets the relevance score threshold.

        A chunk counts as relevant when its cosine-similarity ``score`` is at
        least ``threshold`` (``rag_min_similarity_threshold`` when ``threshold``
        is ``None``). Callers may pass a lower floor for source-scoped
        retrieval, where the query explicitly names an ingested document and
        its path tokens depress the embedding score (see
        :meth:`_relevance_gate_threshold`). When none of the chunks carry a
        ``score`` they are all treated as relevant, so existing behaviour is
        preserved for score-less context (e.g. unit-test fixtures). When at
        least one chunk has a score, only the scored chunks are evaluated — a
        single score-less chunk cannot bypass the threshold gate on an
        otherwise-scored batch. Returns False only when *chunks* is empty or
        every scored chunk falls below the threshold.

        Args:
            chunks: Retrieved chunk dicts (each may carry a ``score``).
            threshold: Score floor to apply; ``None`` uses the configured
                ``rag_min_similarity_threshold``.

        Returns:
            True if there is usable relevant context, False otherwise.
        """
        if not chunks:
            return False
        scored = [c["score"] for c in chunks if c.get("score") is not None]
        if not scored:
            return True  # no score signal at all -> do not gate (backward compatible)
        floor = (
            threshold
            if threshold is not None
            else self._config.rag_min_similarity_threshold
        )
        return any(s >= floor for s in scored)

    def _handle_no_results(
        self,
        query: str,
        allow_llm_fallback: bool = True,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Handle case when no documents retrieved.

        Always reports that no relevant documents were found in the knowledge
        base. When ``allow_llm_fallback`` is True and the
        ``rag_llm_fallback_enabled`` config flag is set, it additionally asks the
        LLM to answer from its own knowledge (and the supplied conversation
        context, if any) and appends that answer when non-empty. The static
        notice is always returned first.

        Args:
            query: Original query.
            allow_llm_fallback: Whether this call may use the LLM knowledge
                fallback. Pass False to return only the static notice (e.g. when
                the LLM has already failed in the same request).
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session, threaded into
                the fallback prompt so a multi-turn follow-up can use earlier
                turns even when no documents matched.

        Returns:
            The static no-results notice, or the notice followed by a non-empty
            LLM knowledge answer when the fallback is enabled and succeeds.

        Example:
            >>> pipeline._handle_no_results("What is Python?")
            "I couldn't find relevant documents for your query: What is Python?"
        """
        notice = self._no_result_notice(query)

        if not allow_llm_fallback or not self._config.rag_llm_fallback_enabled:
            return notice

        prompt = self._build_knowledge_fallback_prompt(
            query, conversation_history=conversation_history
        )
        try:
            llm_answer, streamed = self._stream_generate(prompt, prefix=f"{notice}\n\n")
        except Exception as exc:
            logger.warning(
                "LLM knowledge fallback failed for query %r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return notice

        result = self._apply_llm_fallback(notice, llm_answer)
        if not streamed and self._on_chunk and result:
            self._on_chunk(result, None)
        return result

    async def _handle_no_results_async(
        self,
        query: str,
        allow_llm_fallback: bool = True,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Async variant of :meth:`_handle_no_results`.

        Identical behaviour to the sync version but uses the provider's async
        ``agenerate`` method when available for the LLM knowledge fallback. Falls
        back to the sync ``generate`` method when ``agenerate`` is unavailable.
        Never raises: on any failure the static notice is returned unchanged.

        Args:
            query: Original query.
            allow_llm_fallback: Whether this call may use the LLM knowledge
                fallback.
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session, threaded into
                the fallback prompt so a multi-turn follow-up can use earlier
                turns even when no documents matched.

        Returns:
            Fallback response text.
        """
        notice = self._no_result_notice(query)

        if not allow_llm_fallback or not self._config.rag_llm_fallback_enabled:
            return notice

        prompt = self._build_knowledge_fallback_prompt(
            query, conversation_history=conversation_history
        )
        try:
            llm_answer = await self._agenerate(prompt)
        except Exception as exc:
            logger.warning(
                "LLM knowledge fallback (async) failed for query %r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return notice

        return self._apply_llm_fallback(notice, llm_answer)
