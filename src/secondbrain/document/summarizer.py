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

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from secondbrain.logging import get_logger

SUMMARIZE_PROMPT = """\
You are a knowledgeable research assistant.
Read the following excerpts from a document and produce a concise summary.

Target length: {max_tokens} tokens. Respond in the same language as the excerpts.

## Excerpts
{excerpts}

## Summary:
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
    """

    def __init__(
        self,
        llm_provider: Any,
        embedder: Any,
        storage: Any,
        *,
        max_summary_tokens: int = 512,
        summary_model: str | None = None,
    ) -> None:
        self._llm = llm_provider
        self._embedder = embedder
        self._storage = storage
        self._max_tokens = max_summary_tokens
        self._model = summary_model
        self._logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def summarize_by_chapter(
        self,
        chapter_id: int,
        *,
        include_subsections: bool = True,
    ) -> ChapterSummary:
        """Produce a single summary paragraph covering all section content in this chapter.

        Parameters
        ----------
        chapter_id
            Numeric chapter identifier, e.g. ``3`` for chapter 3.
        include_subsections
            When True (the default), gather all chunks belonging to any
            subsection of the given chapter (``3.1``, ``3.9.11``, …).

        Returns
        -------
        ChapterSummary
            Concise paragraph-level summary plus metadata.
        """
        chapter_title = f"Chapter {chapter_id}"
        chunks = self._collect_chapter_chunks(
            chapter_id,
            include_subsections=include_subsections,
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
        summary_text = await self._llm.agenerate(
            prompt=self._build_summary_prompt(chunks, context),
            temperature=0.5,
            max_tokens=self._max_tokens,
        )

        return ChapterSummary(
            chapter_id=chapter_id,
            chapter_title=chapter_title,
            summary=summary_text,
            chunk_count=len(chunks),
            token_budget_used=self._max_tokens,
        )

    async def summarize_by_section(self, section_id: str) -> SectionSummary:
        """Produce a focused summary of one section's content.

        Parameters
        ----------
        section_id
            Dot-separated section path, e.g. ``"3.9.11"``.

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
        chunks = self._collect_section_chunks(section_id)

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
        summary_text = await self._llm.agenerate(
            prompt=self._build_summary_prompt(chunks, context),
            temperature=0.5,
            max_tokens=self._max_tokens,
        )

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
    ) -> list[dict[str, Any]]:
        """Fetch all chunk dicts for the given chapter from storage.

        Storage is queried by ``chapter_id`` metadata.
        When *include_subsections* is True, all subsections whose number
        starts with ``{chapter_id}.`` are also included.
        """
        query: dict[str, Any] = {"metadata.chapter_id": chapter_id}
        raw: list[dict[str, Any]] = []

        try:
            raw = self._storage.find_chunks_by_metadata(query)
        except Exception:
            self._logger.debug("find_chunks_by_metadata not available, trying find()")

        # Fallback: use synchronous find() on the underlying collection
        if not raw:
            try:
                cursor = self._storage.collection.find(query)
                raw = list(cursor)
            except Exception as exc:
                self._logger.error(
                    "Failed to fetch chapter %s chunks: %s", chapter_id, exc
                )
                return []

        if not include_subsections:
            return raw

        # Gather subsections (e.g. chapter_id==3 → section_prefix=="3.")
        section_prefix = f"{chapter_id}."
        subsection_query: dict[str, Any] = {
            "metadata.section_id": {"$regex": rf"^{section_prefix}"}
        }
        try:
            cursor = self._storage.collection.find(subsection_query)
            subsections = list(cursor)
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

        return combined

    def _collect_section_chunks(self, section_id: str) -> list[dict[str, Any]]:
        """Fetch all chunk dicts for the given section_id from storage."""
        query: dict[str, Any] = {"metadata.section_id": section_id}
        raw: Any = []
        try:
            raw = self._storage.find_chunks_by_metadata(query)
        except Exception:
            self._logger.debug("find_chunks_by_metadata not available, trying find()")

        if raw:
            return cast("list[dict[str, Any]]", raw)

        try:
            cursor = self._storage.collection.find(query)
            return cast("list[dict[str, Any]]", list(cursor))
        except Exception as exc:
            self._logger.error("Failed to fetch section %s chunks: %s", section_id, exc)
            return []

    def _build_summary_prompt(self, chunks: list[dict[str, Any]], context: str) -> str:
        """Assemble a prompt string for the LLM summariser.

        Parameters
        ----------
        chunks
            List of chunk dictionaries; each must contain a ``chunk_text``
            key with the textual content.
        context
            Additional free-form context prepended to the prompt.

        Returns
        -------
        str
            Assembled prompt string ready to send to the LLM.
        """
        excerpts: list[str] = []
        for chunk in chunks:
            text = chunk.get("chunk_text", chunk.get("text", ""))
            if text:
                excerpts.append(text)

        joined = "\n---\n".join(excerpts)
        return SUMMARIZE_PROMPT.format(
            max_tokens=self._max_tokens,
            excerpts=f"{context}\n\n{joined}" if context else joined,
        )

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
