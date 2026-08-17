"""Cohesive helper-method mixins for the RAG pipeline.

These mixin classes group the RAG pipeline's pure/structural/fallback helpers so
:class:`secondbrain.rag.pipeline.RAGPipeline` can inherit them, decomposing the
former single massive class. Every method operates on ``self`` state that is
always present on the composed ``RAGPipeline`` instance.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import TYPE_CHECKING, Any, ClassVar

from secondbrain.config import config
from secondbrain.conversation import ConversationSession
from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.rag.pipeline._constants import (
    BROAD_COVERAGE_TRIGGERS,
    CHAPTER_ENUMERATION_PATTERNS,
    ENUMERATE_CHAPTER_SIGNALS,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    pass


class _FormattingMixin(_RAGPipelineState):
    """Context/prompt/history formatting helpers."""

    def _format_context(
        self,
        chunks: list[dict[str, Any]],
        max_chars: int | None = None,
    ) -> str:
        if max_chars is None:
            max_chars = self._config.rag_max_context_chars
        r"""Format retrieved chunks into context text.

        Args:
            chunks: List of search results with chunk_text, source_file.
            max_chars: Maximum context length.

        Returns:
            Formatted context string.

        Example:
            >>> chunks = [{"chunk_text": "Hello", "source_file": "doc.pdf", "page": 1}]
            >>> pipeline._format_context(chunks)
            'Source: doc.pdf (page 1)\nHello\n\n'
        """
        if not chunks:
            return ""

        context_parts = []
        total_chars = 0

        for chunk in chunks:
            chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
            source_file = chunk.get("source_file", chunk.get("source", "unknown"))
            page = chunk.get("page", chunk.get("page_number", "unknown"))
            chunk_role = chunk.get("chunk_role")

            # Truncate chunk if too long
            if len(chunk_text) > self._config.rag_chunk_preview_chars:
                chunk_text = chunk_text[: self._config.rag_chunk_preview_chars] + "..."

            tags: list[str] = []
            if chunk_role:
                tags.append(chunk_role)
            if chunk_role in ("heading", "toc_entry") or chunk_role is None:
                label = self._infer_section_label(chunk_text, chunk_role)
                if label:
                    tags.append(label)
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            source_line = f"Source: {source_file} (page {page}{tag_str})"
            chunk_entry = f"{source_line}\n{chunk_text}\n"

            # Check if adding this chunk exceeds max_chars
            if total_chars + len(chunk_entry) > max_chars:
                break

            context_parts.append(chunk_entry)
            total_chars += len(chunk_entry)

        return "\n\n".join(context_parts)

    def _build_prompt(
        self,
        query: str,
        context: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build prompt for LLM with context and query.

        Template:
        ```
        [System instructions about using context]

        === DOCUMENT CONTEXT START ===
        {context}
        === DOCUMENT CONTEXT END ===

        {conversation_history if present}

        Question: {query}

        Answer:
        ```

        Args:
            query: User query text.
            context: Formatted, context from retrieved chunks.
            conversation_history: Optional conversation history.

        Returns:
            Complete prompt text for LLM.

        Example:
            >>> prompt = pipeline._build_prompt("What is Python?", context)
            >>> "You are a helpful assistant" in prompt
            True
        """
        system_prompt = config().rag_system_prompt

        # Build prompt
        prompt_parts = [system_prompt]

        # Add context with clear delimiters
        if context:
            prompt_parts.append("\n\n=== DOCUMENT CONTEXT START ===\n")
            prompt_parts.append(context)
            prompt_parts.append("\n=== DOCUMENT CONTEXT END ===\n")
        else:
            prompt_parts.append(
                "\n\nNote: No relevant context was found in the documents."
            )

        # Add conversation history if present
        if conversation_history:
            history_text = self._format_history(conversation_history)
            prompt_parts.append(f"\n\nConversation History:\n{history_text}")

        # Add query
        prompt_parts.append(f"\n\nQuestion: {query}\n\nAnswer:")

        return "".join(prompt_parts)

    def _dedupe_by_text_hash(
        self, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate chunks by 512-byte text prefix hash.

        Used by iterative RAG to collapse repeated chunks across
        multiple per-section search iterations.

        Args:
            chunks: List of chunk dicts with 'chunk_text' key.

        Returns:
            Deduplicated list preserving first occurrence order.
        """
        seen: set[int] = set()
        result: list[dict[str, Any]] = []
        for chunk in chunks:
            text = chunk.get("chunk_text", "")[:512]
            h = hash(text)
            if h not in seen:
                seen.add(h)
                result.append(chunk)
        return result

    def _format_history(
        self,
        history: list[dict[str, Any]],
    ) -> str:
        """Format conversation history for prompt.

        Args:
            history: List of message dictionaries with role and content.

        Returns:
            Formatted history string.

        Example:
            >>> history = [{"role": "user", "content": "Hello"}]
            >>> pipeline._format_history(history)
            "User: Hello"
        """
        if not history:
            return ""

        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.capitalize()}: {content}")

        return "\n".join(lines)

    def _create_error_response(
        self,
        error: str,
        query: str,
    ) -> dict[str, Any]:
        """Create an error response with graceful degradation.

        Args:
            error: Error message describing the failure.
            query: The original query.

        Returns:
            Dictionary with error response data.

        Example:
            >>> pipeline._create_error_response("Connection failed", "test query")
            {"answer": "I apologize...", "query": "test query"}
        """
        return {
            "answer": f"I apologize, but I encountered an error: {error}. Please try again.",
            "query": query,
        }


class _StructureMixin(_RAGPipelineState):
    """Chapter/section detection and structural helpers."""

    def _derive_chapter_roster(self, structure_chunks: list[dict[str, Any]]) -> str:
        import re

        if self._chunks_are_code_like(structure_chunks):
            # No prose structure to enumerate (see _chunks_are_code_like) — emit
            # an empty header so the LLM never sees a fabricated chapter index.
            return ""

        ch_entries, ch_good, appendix_entries = self._derive_chapter_numbers(
            structure_chunks
        )
        ch_titles: dict[int, str] = {}
        for ch_num, _src, title in ch_entries:
            if ch_num in ch_good and ch_num not in ch_titles:
                ch_titles[ch_num] = title if title else "Unknown"

        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        sec_entries: list[tuple[int, str, str]] = []
        seen_sec: set[str] = set()
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if major < 1 or major > 30:
                    continue
                full_match = m.group(0)
                sec_num = full_match.split()[0] if full_match else ""
                raw_title = (m.group(3) or "").strip().rstrip(".")
                if len(raw_title) < 2:
                    continue
                sec_key = f"{major}.{sec_num.split('.')[1] if '.' in sec_num else '0'}"
                if sec_key not in seen_sec:
                    seen_sec.add(sec_key)
                    sec_entries.append((major, sec_num, raw_title))

        sec_entries.sort(key=lambda x: (x[0], *[int(p) for p in x[1].split(".") if p]))
        lines: list[str] = []
        prev_major: int | None = None
        for major, sn, title in sec_entries:
            if prev_major != major:
                ch_title = ch_titles.get(major)
                if ch_title:
                    lines.append(f"[Chapter {major}] {sn} — {ch_title}")
                else:
                    lines.append(f"[Chapter {major}] {sn} — {title}")
                prev_major = major
            else:
                lines.append(f"  {sn} — {title}")

        if appendix_entries:
            lines.append("")
            for label, _src, title in appendix_entries:
                lines.append(f"[Appendix {label}] — {title}")

        header = (
            "DOCUMENT STRUCTURE INDEX (enumerate ALL of the following in your answer):\n"
            + "\n".join(lines[:50])
            + "\n\n"
        )
        return header

    _SECTION_LABEL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Chapter|Section|Appendix|Part)\s+\S+",
        re.IGNORECASE,
    )

    @staticmethod
    def _infer_section_label(chunk_text: str, chunk_role: str | None) -> str | None:
        if chunk_role not in ("heading", "toc_entry"):
            return None
        m = _StructureMixin._SECTION_LABEL_RE.search(chunk_text[:200])
        if m:
            label = m.group(0)
            after = chunk_text[m.end() :].split("\n")[0].strip().rstrip(".:-—")
            if after:
                return f"{label}: {after}"
            return label
        return None

    def _is_enumerate_chapters_query(self, query: str) -> bool:
        """Detect queries explicitly requesting chapter-by-chapter enumeration.

        Matches phrases like "summarize all 21 chapters", "chapter 1", "give me an overview of each chapter".
        Returns True when query mentions chapter numbers AND implies enumeration (not just a single chapter lookup).

        Args:
            query: User query string.

        Returns:
            True if query explicitly enumerates chapters.
        """
        q = query.lower()
        has_chapter_ref = any(p.search(q) for p in CHAPTER_ENUMERATION_PATTERNS)
        has_enum_signal = any(t in q for t in ENUMERATE_CHAPTER_SIGNALS)
        return has_chapter_ref and has_enum_signal

    _APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s+(.{2,60})",
    )
    _BARE_APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:^|\n)\s*(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s*[.:-]?\s*(.{2,80})",
        re.MULTILINE,
    )

    @staticmethod
    def _chunks_are_code_like(structure_chunks: list[dict[str, Any]]) -> bool:
        """Return True when structure-probe chunks look like source code, not prose.

        Structural chapter extraction is only meaningful for prose manuals.
        Source code — especially bundled/minified output — sets off the
        chapter/section regexes on version numbers, identifiers and SVG/data
        path fragments (e.g. ``8.5``, ``7.0.0``, ``25.8``), producing
        hallucinated chapters for documents that have none.  This gate is
        intentionally conservative: it only fires on unambiguous code signals
        (near-zero whitespace density, or pervasive code punctuation), so
        genuine prose documents are never suppressed.

        Parameters
        ----------
        structure_chunks :
            List of probe chunk dicts (each with a ``chunk_text`` key).

        Returns
        -------
        bool
            True when the sampled content is clearly code, False otherwise.
        """
        if not structure_chunks:
            return False
        text = "".join(
            (c.get("chunk_text") or "")[:4000] for c in structure_chunks[:24]
        )
        n = len(text)
        if n < 200:
            # Too little signal to classify — never suppress a prose document.
            return False

        # Signal 1: bundled / minified output has almost no whitespace at all
        # (prose has a blank between essentially every word, ~15%+ whitespace).
        whitespace = sum(1 for ch in text if ch.isspace())
        if whitespace / n < 0.05:
            return True

        # Signal 2: code punctuation density.  Braces, semicolons, and
        # operators appear constantly in source code (formatted or not) but are
        # essentially absent from prose.  Parens and quotes are excluded as
        # they occur in ordinary writing.
        code_punct = "{};=<>&|#`"
        density = sum(1 for ch in text if ch in code_punct) / n
        return density > 0.02

    def _derive_chapter_numbers(
        self, structure_chunks: list[dict[str, Any]]
    ) -> tuple[list[tuple[int, str, str]], set[int], list[tuple[str, str, str]]]:
        """Return reliable chapter and appendix entries from structure chunks.

        Returns (entries, chapter_level_nums, appendix_entries) where
        chapter_level_nums are chapter numbers from CHAPTER_N_RE/BARE_CHAPTER_RE
        (reliable titles) and appendix_entries are (appendix_label, source, title).
        """
        import re

        if self._chunks_are_code_like(structure_chunks):
            # Code files (bundled JS, source, etc.) have no prose chapter
            # structure — the regexes below would just hallucinate chapters
            # from version numbers and identifiers.  Suppress entirely so the
            # pipeline falls through to generic search.
            return [], set(), []

        entries: list[tuple[int, str, str]] = []
        appendix_entries: list[tuple[str, str, str]] = []
        seen: set[tuple[int, str]] = set()
        seen_appendix: set[tuple[str, str]] = set()
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        chapter_n_re = re.compile(
            r"(?:Chapter\s+(\d+)\s*[:\-]?\s*|(?:Module|Lesson)\s+(\d+)\s*[:\-]\s*)"
            r"(.{2,60})",
            re.IGNORECASE,
        )
        bare_chapter_re = re.compile(
            r"(?:^|\n)\s*(\d{1,2})\.?\s+([A-Za-z][A-Za-z0-9\s\-\(\),'/:.\u2013\u2014]{4,80})",
            re.MULTILINE,
        )
        # Patterns for appendix detection
        appendix_n_re = self._APPENDIX_RE
        bare_appendix_re = self._BARE_APPENDIX_RE
        seen_sec: set[int] = set()
        sec_limit = 0

        # Pass 1: CHAPTER_N_RE + APPENDIX_N_RE (most reliable patterns)
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            for nm in chapter_n_re.finditer(raw):
                major = int(nm.group(1) or nm.group(2))
                if major < 1 or major > 30 or (major, source) in seen:
                    continue
                title = nm.group(3).strip().rstrip(".")
                if len(title) < 2:
                    continue
                fw = title.lower().split()[0] if title.split() else ""
                if fw in (
                    "contents",
                    "copyright",
                    "licensed",
                    "license",
                    "trolltech",
                    "red",
                    "bootstrap",
                ):
                    continue
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    continue
                seen.add((major, source))
                entries.append((major, source, title))
            for am in appendix_n_re.finditer(raw):
                label = am.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = am.group(2).strip().rstrip(".")
                if len(title) < 2:
                    continue
                # Skip false positives: mid-sentence references like
                # "Appendix A of the Specification" (title starts with
                # a preposition/article/conjunction, not a heading).
                _fpa = title.lower().split()[0] if title.split() else ""
                if _fpa in (
                    "of",
                    "to",
                    "in",
                    "for",
                    "the",
                    "and",
                    "or",
                    "by",
                    "with",
                    "from",
                    "at",
                    "on",
                    "is",
                    "are",
                    "its",
                    "this",
                    "that",
                    "was",
                    "were",
                    "been",
                ):
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

        # Pass 2: bare_chapter_re + bare_appendix_re
        ft_catch = re.compile(
            r"\d+\s+(\d{1,2})\s+([A-Za-z][A-Za-z0-9\s\-\(\),'/:.\u2013\u2014]{4,80})"
        )
        legal_starts = {
            "contents",
            "copyright",
            "licensed",
            "license",
            "trolltech",
            "red",
            "bootstrap",
            "a",
            "an",
            "the",
            "you",
            "your",
            "this",
            "each",
            "by",
            "if",
            "as",
            "subject",
            "whereas",
            "notwithstanding",
            "accepting",
            "submission",
            "disclaimer",
            "disclaimers",
            "limitation",
            "at",  # "15 At least moderately important"
            # Report / white-paper false-positive starters — these
            # first words appear in non-chapter section headings
            # (e.g. "8 Key findings", "22 Question:") and would
            # otherwise be hallucinated as chapter numbers.
            "key",
            "question",
            "questions",
            "figure",
            "table",
        }
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()

            for bm in bare_chapter_re.finditer(raw):
                major = int(bm.group(1))
                if major < 1 or major > 30 or (major, source) in seen:
                    continue
                title = bm.group(2).strip().rstrip(".")
                if len(title) < 4:
                    continue
                fw = (title.lower().split()[0] if title.split() else "").rstrip(":;,.")
                if fw in legal_starts:
                    continue
                if title[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title, re.IGNORECASE):
                    continue
                seen.add((major, source))
                entries.append((major, source, title))

            for bam in bare_appendix_re.finditer(raw):
                label = bam.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = bam.group(2).strip().rstrip(".")
                if len(title) < 4:
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

            for fm in ft_catch.finditer(raw):
                major_ft = int(fm.group(1))
                if major_ft < 1 or major_ft > 30 or (major_ft, source) in seen:
                    continue
                title_ft = fm.group(2).strip().rstrip(".")
                if len(title_ft) < 6:
                    continue
                fw_ft = (
                    title_ft.lower().split()[0] if title_ft.split() else ""
                ).rstrip(":;,.")
                if fw_ft in legal_starts:
                    continue
                if title_ft[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title_ft, re.IGNORECASE):
                    continue
                seen.add((major_ft, source))
                entries.append((major_ft, source, title_ft))

            seen_max = max([s[0] for s in seen], default=0)
            sec_limit = seen_max + 3 if seen_max > 0 else 999
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if (
                    major < 1
                    or major > 30
                    or major in seen_sec
                    or (major, source) in seen
                    or (seen_max > 0 and major > sec_limit)
                ):
                    continue
                raw_title = (m.group(3) or "").strip()
                clean_title = raw_title.rstrip(".")
                if len(clean_title) < 2:
                    continue
                fw = clean_title.lower().split()[0] if clean_title.split() else ""
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    clean_title = ""
                seen_sec.add(major)

        # Phase 3: chunk-boundary recovery for chapters
        if entries:
            found_nums = {e[0] for e in entries}
            all_seen = {s[0] for s in seen}
            lo = min(found_nums)
            hi = max(found_nums)
            for gap_n in range(lo + 1, hi):
                if gap_n in all_seen:
                    continue
                for i in range(len(structure_chunks) - 1):
                    cur = structure_chunks[i]
                    nxt = structure_chunks[i + 1]
                    cur_text = cur.get("chunk_text", "")
                    src_cur = cur.get("source_file", "")
                    if (
                        f"Chapter {gap_n}" not in cur_text
                        and f"chapter {gap_n}" not in cur_text
                    ):
                        continue
                    idx = cur_text.lower().find(f"chapter {gap_n}")
                    remaining = len(cur_text) - idx
                    if remaining > 80 or (gap_n, src_cur) in seen:
                        continue
                    nxt_text = nxt.get("chunk_text", "").strip()
                    first_line = nxt_text.split("\n")[0].strip()
                    if (
                        len(first_line) >= 4
                        and first_line[0].isupper()
                        and not first_line[0].islower()
                        and not re.search(r"^\d+\.\d+", first_line)
                    ):
                        title = re.sub(r"\s*\d+\s*$", "", first_line).rstrip(".")
                        seen.add((gap_n, src_cur))
                        entries.append((gap_n, src_cur, title))

        entries.sort(key=lambda x: x[0])
        appendix_entries.sort(key=lambda x: x[0])

        # Post-validation: drop outlier chapters that are likely false
        # positives from over-eager pass-2 regex patterns (bare_chapter_re,
        # ft_catch).  Find the longest consecutive run of chapter numbers;
        # if it accounts for >= 60 % of detected chapters AND there are
        # at least 5 total entries (too few data points makes the ratio
        # unreliable), exclude chapters outside that run.
        if len(entries) >= 5:
            all_nums = sorted({e[0] for e in entries})
            runs: list[list[int]] = [[all_nums[0]]]
            for n in all_nums[1:]:
                if n == runs[-1][-1] + 1:
                    runs[-1].append(n)
                else:
                    runs.append([n])
            main_run = max(runs, key=len)
            if len(main_run) / len(all_nums) >= 0.60:
                main_set = set(main_run)
                entries = [e for e in entries if e[0] in main_set]
                seen = {(n, s) for (n, s) in seen if n in main_set}

        # LLM fallback: classify unmatched appendix candidates
        if not appendix_entries and self._llm_provider is not None:
            llm_candidates: list[str] = []
            llm_sources: list[str] = []
            seen_keywords: set[str] = {str(e[0]) for e in entries}
            seen_keywords.update(al[0] for al in appendix_entries)
            for chunk in structure_chunks:
                raw = chunk.get("chunk_text", "").strip()
                src = chunk.get("source_file", "")
                first_line = raw.split("\n")[0].strip()
                if not first_line or len(first_line) > 120:
                    continue
                first_word = first_line.split()[0].lower() if first_line.split() else ""
                if first_word in seen_keywords:
                    continue
                if not any(
                    k in first_line.lower()
                    for k in ("appendix", "annex", "supplement", "supplementary")
                ):
                    continue
                candidate = first_line[:120]
                llm_candidates.append(candidate)
                llm_sources.append(src)

            if llm_candidates:
                candidates_prompt = (
                    "Classify each of the following document headings. "
                    "If it is an appendix, respond with APPENDIX:<label> on its own line, "
                    "where label is a single letter like A, B, C. "
                    "If it is a chapter heading, respond with CHAPTER. "
                    "If neither, respond with NONE. "
                    "One response per line, in order.\n\n"
                    + "\n".join(
                        f"{i + 1}. {c}" for i, c in enumerate(llm_candidates[:5])
                    )
                )
                try:
                    llm_reply = self._llm_provider.generate(
                        prompt=candidates_prompt,
                        temperature=0.1,
                        max_tokens=200,
                    )
                    for i, line in enumerate(llm_reply.strip().split("\n")):
                        line = line.strip()
                        if i >= len(llm_candidates):
                            break
                        if line.startswith("APPENDIX:"):
                            label = line.split(":", 1)[1].strip().upper()
                            if label and len(label) == 1 and label.isalpha():
                                candidate_text = llm_candidates[i]
                                parts = candidate_text.split(None, 2)
                                title = parts[-1] if len(parts) > 1 else candidate_text
                                title = title.rstrip(".:-")
                                key = (label, llm_sources[i])
                                if key not in seen_appendix:
                                    seen_appendix.add(key)
                                    appendix_entries.append(
                                        (label, llm_sources[i], title)
                                    )
                except Exception:
                    logger.debug("LLM appendix fallback failed", exc_info=True)

        return entries, {s[0] for s in seen}, appendix_entries

    def _is_broad_coverage_query(self, query: str) -> bool:
        q = query.lower().strip()
        return any(t in q for t in BROAD_COVERAGE_TRIGGERS)

    def _probe_document_structure(
        self,
        top_k: int = 10000,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Probe for document structural elements (TOC/section headers) via chunk_role.

        Attempts targeted structural-role filters first; falls back to raw
        top-K retrieval when few candidates are found (handles documents whose
        chunks lack explicit element_type/chunk_role markers).

        Args:
            top_k: How many structural candidates to retrieve (default 10000).
            source_filter: Optional source_file filter to scope to one document.

        Returns:
            List of chunk dicts with '_id', 'chunk_text', 'page_number',
            'source_file', 'chunk_id'.
        """
        from pymongo import MongoClient
        from pymongo import errors as mongo_errors

        from secondbrain.config import config

        cfg = config()
        try:
            client = MongoClient(
                cfg.mongo_uri, directConnection=True, serverSelectionTimeoutMS=2000
            )
            # Validate connection quickly
            client.admin.command("ping")
        except (
            mongo_errors.ConnectionFailure,
            mongo_errors.ServerSelectionTimeoutError,
            Exception,
        ):
            return []
        coll = client[cfg.mongo_db][cfg.mongo_collection]

        query_filter: dict[str, object] = {
            "$or": [
                {
                    "element_type": {
                        "$in": ["heading", "toc_entry", "body", "paragraph"]
                    }
                },
                {
                    "chunk_role": {
                        "$in": ["body", "caption", "navigation", "heading", "toc_entry"]
                    }
                },
            ]
        }
        if source_filter:
            query_filter["source_file"] = {"$regex": f"^{re.escape(source_filter)}"}

        cursor = (
            coll.find(
                query_filter,
                {
                    "_id": 0,
                    "chunk_text": 1,
                    "chunk_role": 1,
                    "page_number": 1,
                    "source_file": 1,
                    "chunk_id": 1,
                },
            )
            .sort("page_number", 1)
            .limit(10000)
        )
        result = list(cursor)
        if len(result) < 5:
            fallback_filter: dict[str, object] = {}
            if source_filter:
                fallback_filter["source_file"] = {
                    "$regex": f"^{re.escape(source_filter)}"
                }
            result = list(
                coll.find(
                    fallback_filter,
                    {
                        "_id": 0,
                        "chunk_text": 1,
                        "chunk_role": 1,
                        "page_number": 1,
                        "source_file": 1,
                        "chunk_id": 1,
                    },
                ).limit(top_k)
            )
        return result

    def _generic_one_shot(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        """Fallback one-shot retrieval when document structure probing fails."""
        chunks = self._searcher.search(
            query,
            top_k=top_k,
            source_filter=source_filter,
        )
        if not self._has_relevant_chunks(chunks):
            return {"answer": self._handle_no_results(query), "query": query}
        context = self._format_context(chunks)
        prompt = self._build_prompt(query, context)
        answer = self._llm_provider.generate(
            prompt=prompt,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )
        result: dict[str, Any] = {"answer": answer, "query": query}
        if show_sources:
            result["sources"] = chunks
        return result


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
            "knowledge, answer the user's question if you have enough information "
            "to do so accurately. If you do NOT have enough information, reply "
            "with a short, honest statement that you do not have information on "
            "it. Do not fabricate facts or present guesswork as established "
            "knowledge."
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
            answer = self._generate(prompt)
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

    def _has_relevant_chunks(self, chunks: list[dict[str, Any]]) -> bool:
        """Return True if any retrieved chunk meets the relevance score threshold.

        A chunk counts as relevant when its cosine-similarity ``score`` is at
        least ``rag_min_similarity_threshold``. When none of the chunks carry a
        ``score`` they are all treated as relevant, so existing behaviour is
        preserved for score-less context (e.g. unit-test fixtures). When at least
        one chunk has a score, only the scored chunks are evaluated — a single
        score-less chunk cannot bypass the threshold gate on an otherwise-scored
        batch. Returns False only when *chunks* is empty or every scored chunk
        falls below the threshold.

        Args:
            chunks: Retrieved chunk dicts (each may carry a ``score``).

        Returns:
            True if there is usable relevant context, False otherwise.
        """
        if not chunks:
            return False
        scored = [c["score"] for c in chunks if c.get("score") is not None]
        if not scored:
            return True  # no score signal at all -> do not gate (backward compatible)
        return any(s >= self._config.rag_min_similarity_threshold for s in scored)

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
            llm_answer = self._generate(prompt)
        except Exception as exc:
            logger.warning(
                "LLM knowledge fallback failed for query %r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return notice

        return self._apply_llm_fallback(notice, llm_answer)

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


class _RoutingMixin(_RAGPipelineState):
    """Document routing and source-filter helpers."""

    def _get_document_router(self) -> DocumentRouter:
        """Return the DocumentRouter, creating it lazily if needed."""
        if self._document_router is None:
            try:
                self._document_router = DocumentRouter(
                    storage=self._searcher.storage,
                )
            except Exception:
                self._document_router = DocumentRouter()
        return self._document_router

    def _resolve_source_filter(self, query: str) -> str | None:
        """Resolve a user query to a source_file filter if a doc is named.

        Returns a source_file path string or None if no document is referenced.
        """
        router = self._get_document_router()
        doc_name = router.extract_document_name(query)
        if doc_name is not None:
            return router.resolve_source_file(doc_name)
        return None

    def _rewrite_query_with_history(
        self,
        query: str,
        session: ConversationSession,
    ) -> str:
        """Rewrite query using conversation history.

        Args:
            query: Current user query.
            session: ConversationSession with history.

        Returns:
            Rewritten query or original if rewriter not available.

        Example:
            >>> session = ConversationSession.create("test", storage)
            >>> pipeline._rewrite_query_with_history("What about it?", session)
            "What about it?"  # No rewriter, returns original
        """
        if self._rewriter is None:
            return query

        history = session.get_history(limit=self._context_window)
        if not history:
            return query

        try:
            return self._rewriter.rewrite_query(query, history)
        except Exception as e:
            logger.warning("Query rewriting failed: %s: %s", type(e).__name__, e)
            return query
