"""Chapter- and section-level summarisation using an injectable LLM provider.

Exports
-------
ChapterSummary
    Dataclass holding one chapter's summary and metadata.
SectionSummary
    Dataclass holding one section's summary and metadata.
Summarizer
    Main entry point; expose ``summarize_by_chapter()``,
    ``summarize_by_section()``, and ``stream_summaries()``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from secondbrain.logging import get_logger

# Real chapter starts are chunks whose text begins with "Chapter <N>"; TOC
# listings and prose cross-references place the phrase mid-text instead.
_CHAPTER_START_RE = re.compile(r"^\s*chapter\s+(\d+)\b", re.IGNORECASE)

SUMMARIZE_PROMPT = """\
You are a knowledgeable research assistant.
Read the following excerpts from a document and produce a detailed, well-structured summary that expounds on the content rather than condensing it.

Write a thorough summary that:
- Covers the main ideas, key arguments, methods, and findings in depth.
- Includes significant names, numbers, definitions, and concrete examples from the material.
- Explains what the document actually says, not just what topics it mentions.
- Is organised into several clear paragraphs: an overview, the key points, and a short conclusion.
- Does NOT simply restate the title or write a one-sentence description.

Aim for roughly {target_tokens} tokens. Write enough to fully convey the substance of the excerpts. Respond in the same language as the excerpts.

## Excerpts
{excerpts}

## Summary:
"""


# Used to fold the per-window partial summaries produced by map-reduce back into
# a single coherent cover-all summary when a chapter/section exceeds the input
# budget (see ``Summarizer._summarize_windowed``).
MERGE_SUMMARIES_PROMPT = """\
You are a knowledgeable research assistant.
You are given several partial summaries, each describing a different part of the
same document. Combine them into ONE coherent, well-structured summary that covers
the combined substance without repeating the same points multiple times.

Write a thorough combined summary that:
- Covers the main ideas, key arguments, methods, and findings across ALL partials in depth.
- Includes significant names, numbers, definitions, and concrete examples from across the parts.
- Organises the result into several clear paragraphs: an overview, the key points, and a short conclusion.
- Does NOT simply restate the partial headings or repeat each partial verbatim.

Aim for roughly {target_tokens} tokens. Respond in the same language as the partial summaries.

## Partial Summaries
{partials}

## Combined Summary:
"""


@dataclass
class ChapterSummary:
    """Summary result for one document chapter."""

    chapter_id: int
    chapter_title: str
    summary: str
    chunk_count: int
    token_budget_used: int


@dataclass
class SectionSummary:
    """Summary result for one document section."""

    section_id: str
    section_title: str
    summary: str
    belongs_to_chapter: int
    token_budget_used: int


class Summarizer:
    """Summarise document chapters or sections using an LLM provider.

    Parameters
    ----------
    llm_provider
        Object conforming to the |LocalLLMProvider| protocol (has
        ``generate()`` / ``agenerate()``).
    embedder
        Embedding backend (unused in this class but kept for future
        chunk prioritisation). The object must have an ``embed()`` method.
    storage
        MongoDB-backed vector store. Must expose
        ``find_chunks_by_metadata()`` returning a list of chunk dicts.
    max_summary_tokens
        Hard cap on the number of tokens the LLM may emit in a single
        summary (default 512).
    summary_model
        Optional model override passed to the LLM provider.
    max_input_chars
        Hard cap on the total number of characters of document text sent to
        the LLM in a single request (default 16000). When the collected
        excerpts exceed this, map-reduce summarisation is used instead of a
        single call, preventing context-window overflow and the degenerate
        "token soup" output that follows it.
    max_windows
        Upper bound on map-reduce partial windows (default 8) so that an
        arbitrarily large chapter cannot spawn an unbounded number of LLM
        calls. When exceeded the excerpts are truncated to the budget.
    """

    def __init__(
        self,
        llm_provider: Any,
        embedder: Any,
        storage: Any,
        *,
        max_summary_tokens: int = 512,
        summary_model: str | None = None,
        max_input_chars: int = 16000,
        max_windows: int = 8,
    ) -> None:
        self._llm = llm_provider
        self._embedder = embedder
        self._storage = storage
        self._max_tokens = max_summary_tokens
        self._model = summary_model
        self._max_input_chars = max(1, max_input_chars)
        self._max_windows = max(1, max_windows)
        self._logger = get_logger(__name__)
        self._chapter_map_cache: dict[str, dict[int, int]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def summarize_by_chapter(
        self,
        chapter_id: int,
        *,
        include_subsections: bool = True,
        source_file: str | None = None,
    ) -> ChapterSummary:
        """Produce a single summary paragraph covering all section content in this chapter.

        Parameters
        ----------
        chapter_id
            Numeric chapter identifier, e.g. ``3`` for chapter 3.
        include_subsections
            When True (the default), gather all chunks belonging to any
            subsection of the given chapter (``3.1``, ``3.9.11``, …).
        source_file
            Optional path of the ingested document to restrict results to.
            When provided, only chunks from that specific source are used,
            preventing cross-document aggregation.

        Returns
        -------
        ChapterSummary
            Concise paragraph-level summary plus metadata.
        """
        chapter_title = f"Chapter {chapter_id}"
        chunks = self._collect_chapter_chunks(
            chapter_id,
            include_subsections=include_subsections,
            source_file=source_file,
        )

        if not chunks:
            self._logger.warning("No chunks found for chapter %s", chapter_id)
            return ChapterSummary(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                summary="",
                chunk_count=0,
                token_budget_used=0,
            )

        context = (
            f"The following excerpts belong to {chapter_title}. "
            "Please summarise the main ideas across all of them."
        )
        summary_text = await self._summarize(chunks, context)

        return ChapterSummary(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            summary=summary_text,
            chunk_count=len(chunks),
            token_budget_used=self._max_tokens,
        )

    async def summarize_by_section(
        self, section_id: str, *, source_file: str | None = None
    ) -> SectionSummary:
        """Produce a focused summary of one section's content.

        Parameters
        ----------
        section_id
            Dot-separated section path, e.g. ``"3.9.11"``.
        source_file
            Optional path of the ingested document to restrict results to.
            When provided, only chunks from that specific source are used,
            preventing cross-document aggregation.

        Returns
        -------
        SectionSummary
            Narrowly-scoped section summary.
        """
        section_parts = section_id.split(".")
        try:
            chapter_id = int(section_parts[0])
        except ValueError:
            chapter_id = 0

        section_title = f"Section {section_id}"
        chunks = self._collect_section_chunks(section_id, source_file=source_file)

        if not chunks:
            self._logger.warning("No chunks found for section %s", section_id)
            return SectionSummary(
                section_id=section_id,
                section_title=section_title,
                summary="",
                belongs_to_chapter=chapter_id,
                token_budget_used=0,
            )

        context = (
            f"The following excerpts belong specifically to {section_title} "
            "of the document."
        )
        summary_text = await self._summarize(chunks, context)

        return SectionSummary(
            section_id=section_id,
            section_title=section_title,
            summary=summary_text,
            belongs_to_chapter=chapter_id,
            token_budget_used=self._max_tokens,
        )

    async def stream_summaries(
        self,
        chapter_ids: list[int],
    ) -> AsyncIterator[ChapterSummary]:
        """Stream summaries for multiple chapters (useful for a ``--each`` flag).

        Parameters
        ----------
        chapter_ids
            Ordered list of chapter identifiers to summarise.

        Yields
        ------
        ChapterSummary
            One summary per chapter, in the same order as *chapter_ids*.
        """
        for ch_id in chapter_ids:
            yield await self.summarize_by_chapter(ch_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_chapter_chunks(
        self,
        chapter_id: int,
        *,
        include_subsections: bool = True,
        source_file: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all chunk dicts for the given chapter from storage.

        Storage is queried by ``chapter_id`` metadata.
        When *include_subsections* is True, all subsections whose number
        starts with ``{chapter_id}.`` are also included.
        When *source_file* is provided, results are restricted to chunks
        from that specific source document.
        """
        raw: list[dict[str, Any]] = []
        try:
            raw = list(
                self._storage.find_chunks(
                    source_file=source_file,
                    chapter_id=str(chapter_id),
                )
            )
        except Exception as exc:
            self._logger.error("Failed to fetch chapter %s chunks: %s", chapter_id, exc)
            return []

        if not include_subsections:
            return raw

        # Gather subsections (e.g. chapter_id==3 → section_prefix=="3.")
        section_prefix = f"{chapter_id}."
        try:
            subsections = list(
                self._storage.find_chunks(
                    source_file=source_file,
                    section_id_pattern=rf"^{section_prefix}",
                )
            )
        except Exception as exc:
            self._logger.error(
                "Failed to fetch subsections for chapter %s: %s", chapter_id, exc
            )
            return raw

        # Merge, avoiding duplicates by chunk_id
        seen: set[str] = set()
        combined: list[dict[str, Any]] = []
        for chunk in raw + subsections:
            cid = chunk.get("chunk_id") or chunk.get("_id")
            if cid and cid not in seen:
                seen.add(cid)
                combined.append(chunk)

        # When the document carries no chapter_id/section_id metadata, fall back
        # to detecting chapter boundaries by page so chapter summaries still work.
        if not combined and source_file:
            combined = self._collect_chapters_by_page(chapter_id, source_file)

        return combined

    def _collect_chapters_by_page(
        self, chapter_id: int, source_file: str
    ) -> list[dict[str, Any]]:
        """Gather a chapter's chunks by page range when no chapter metadata exists.

        Builds a ``chapter_number -> start_pdf_page`` map from body chunks whose
        text begins with a "Chapter N" heading (excludes the TOC and prose
        cross-references, which place the phrase mid-text). The chapter's body is
        then every relevant chunk on pages ``[start_N, start_{N+1})`` of the given
        *source_file*.
        """
        page_map = self._chapter_page_map(source_file)
        if chapter_id not in page_map:
            return []
        start = page_map[chapter_id]
        end = page_map.get(chapter_id + 1, 10**9)
        try:
            chunks = list(self._storage.find_chunks(source_file=source_file))
        except Exception as exc:
            self._logger.error(
                "Failed to fetch chunks for chapter %s page range: %s",
                chapter_id,
                exc,
            )
            return []
        return [
            c
            for c in chunks
            if (c.get("page_number") or 0) >= start
            and (c.get("page_number") or 0) < end
            and c.get("chunk_role") in ("body", "caption")
        ]

    def _chapter_page_map(self, source_file: str) -> dict[int, int]:
        """Return a cached ``chapter_number -> start_pdf_page`` map for a source."""
        cached = self._chapter_map_cache.get(source_file)
        if cached is not None:
            return cached
        try:
            chunks = list(self._storage.find_chunks(source_file=source_file))
        except Exception as exc:
            self._logger.error(
                "Failed to fetch chunks for chapter map of %s: %s", source_file, exc
            )
            self._chapter_map_cache[source_file] = {}
            return {}
        page_map: dict[int, int] = {}
        ordered = sorted(chunks, key=lambda c: c.get("page_number") or 0)
        for c in ordered:
            if c.get("chunk_role") not in ("body", "caption"):
                continue
            m = _CHAPTER_START_RE.match((c.get("chunk_text") or "").lstrip())
            if not m:
                continue
            chapter_num = int(m.group(1))
            if chapter_num not in page_map:
                page_map[chapter_num] = c.get("page_number") or 0
        self._chapter_map_cache[source_file] = page_map
        return page_map

    def _collect_section_chunks(
        self, section_id: str, *, source_file: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all chunk dicts for the given section_id from storage.

        When *source_file* is provided, results are restricted to chunks
        from that specific source document.
        """
        try:
            return list(
                self._storage.find_chunks(
                    source_file=source_file,
                    section_id=section_id,
                )
            )
        except Exception as exc:
            self._logger.error("Failed to fetch section %s chunks: %s", section_id, exc)
            return []

    def _build_summary_prompt(self, excerpts: list[str], context: str) -> str:
        """Assemble a prompt string for the LLM summariser.

        Parameters
        ----------
        excerpts
            Textual excerpts already extracted from chunks, ordered by
            document position.
        context
            Additional free-form context prepended to the prompt.

        Returns
        -------
        str
            Assembled prompt string ready to send to the LLM.
        """
        joined = "\n---\n".join(excerpts)
        # Desired summary length: meaningful detail, upper-bounded so a huge
        # llm_max_tokens cap doesn't make the "target length" line absurd.
        target_tokens = max(300, min(self._max_tokens, 900))
        return SUMMARIZE_PROMPT.format(
            target_tokens=target_tokens,
            excerpts=f"{context}\n\n{joined}" if context else joined,
        )

    def _extract_excerpts(self, chunks: list[dict[str, Any]]) -> list[str]:
        """Return the ordered non-empty text excerpts from *chunks*."""
        excerpts: list[str] = []
        for chunk in chunks:
            text = chunk.get("chunk_text", chunk.get("text", ""))
            if text:
                excerpts.append(text)
        return excerpts

    async def _summarize(self, chunks: list[dict[str, Any]], context: str) -> str:
        """Summarize *chunks*, using map-reduce when input exceeds the budget.

        Single LLM call when the combined excerpts fit within
        ``self._max_input_chars``; otherwise the excerpts are split into
        bounded windows, each summarised separately, and the partials are
        folded back together via ``MERGE_SUMMARIES_PROMPT``. This prevents a
        chapter/section larger than the model's context window from being
        sent whole, which previously produced truncated, degenerate output.
        """
        excerpts = self._extract_excerpts(chunks)
        if not excerpts:
            return ""
        if self._fits_in_budget(excerpts):
            prompt = self._build_summary_prompt(excerpts, context)
            return await self._generate_with_guard(prompt)

        partials: list[str] = []
        for window in self._window_excerpts(excerpts):
            prompt = self._build_summary_prompt(window, context)
            partial = await self._generate_with_guard(prompt)
            if partial:
                partials.append(partial)

        if not partials:
            return ""
        if len(partials) == 1:
            return partials[0]
        return await self._generate_with_guard(self._build_merge_prompt(partials))

    def _fits_in_budget(self, excerpts: list[str]) -> bool:
        """Return True when the combined excerpts fit the single-call budget."""
        return sum(len(e) for e in excerpts) <= self._max_input_chars

    def _window_excerpts(self, excerpts: list[str]) -> list[list[str]]:
        """Greedily group *excerpts* into windows within the char budget.

        The number of windows is capped by ``self._max_windows``; when the
        source is so large that the windows would exceed that cap, trailing
        excerpts are dropped so the summariser never issues an unbounded
        number of LLM calls.
        """
        kept = excerpts
        hard_budget = self._max_input_chars * self._max_windows
        total = sum(len(e) for e in kept)
        if total > hard_budget:
            acc = 0
            kept = []
            for text in excerpts:
                if acc + len(text) > hard_budget:
                    break
                kept.append(text)
                acc += len(text)

        windows: list[list[str]] = []
        current: list[str] = []
        current_size = 0
        for text in kept:
            if current and current_size + len(text) > self._max_input_chars:
                windows.append(current)
                current = []
                current_size = 0
            current.append(text)
            current_size += len(text)
        if current:
            windows.append(current)
        return windows

    def _build_merge_prompt(self, partials: list[str]) -> str:
        """Build the fold prompt combining per-window partial summaries."""
        target_tokens = max(300, min(self._max_tokens, 900))
        numbered = "\n\n".join(
            f"--- Partial summary {i + 1} ---\n{p}" for i, p in enumerate(partials)
        )
        return MERGE_SUMMARIES_PROMPT.format(
            target_tokens=target_tokens,
            partials=numbered,
        )

    async def _generate_with_guard(self, prompt: str) -> str:
        """Generate a summary, rerunning once if the output looks degenerate.

        Option C (fail-closed + gibberish guard): if the first response fails
        the plausibility check, retry at a low temperature. If the retry is
        still implausible, return an empty string rather than surfacing
        token-soup to the caller.
        """
        text = cast(str, await self._llm.agenerate(
            prompt=prompt, temperature=0.5, max_tokens=self._max_tokens
        ))
        if self._is_plausible_summary(text):
            return text
        self._logger.warning(
            "Summariser output failed plausibility check; retrying at low temperature"
        )
        text = cast(str, await self._llm.agenerate(
            prompt=prompt, temperature=0.1, max_tokens=self._max_tokens
        ))
        if self._is_plausible_summary(text):
            return text
        self._logger.error("Summariser output still implausible; returning empty summary")
        return ""

    @staticmethod
    def _is_plausible_summary(text: str) -> bool:
        """Detect degenerate/token-soup output (repetitive or low-diversity text).

        A genuinely useful summary is non-trivial in length and lexically
        varied; repetitive or single-token-dominated output signals the kind
        of context-overflow degeneration the windowing is meant to prevent.
        """
        if not text or len(text.strip()) < 40:
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
    def _token_budget_for(n_chunks: int, total_budget: int) -> int:
        """Distribute *total_budget* evenly across *n_chunks*.

        Each chunk receives at least one token; remainder tokens are
        assigned round-robin.
        """
        if n_chunks <= 0:
            return 0
        base = total_budget // n_chunks
        remainder = total_budget % n_chunks
        # First 'remainder' chunks get one extra token
        return base + (1 if remainder > 0 else 0)
