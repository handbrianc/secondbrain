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


# Upper bound on how many independent map-reduce LLM calls one summarisation may
# issue.  Without this, a dense multi-chapter book or a chapter with many
# sections would fan out into dozens of sequential, thinking-mode LLM calls,
# making the chat appear frozen on "Thinking..." for minutes.
_MAX_MAP_REDUCE_WINDOWS = 50

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

# Function words used by the derailment detector.  Normal English prose keeps a
# steady share of determiners/pronouns/prepositions/auxiliaries sprinkled through
# it; a high-temperature "word-salad" degeneration crams content words together
# with almost none, and — unlike repetitive token-soup — stays high-diversity, so
# the repetition-based plausibility check alone misses it.  A trailing window low
# in function words is a strong signal that the stream has derailed.
_FUNCTION_WORDS = frozenset({
    "a", "an", "the", "this", "that", "these", "those", "some", "any", "no",
    "not", "none", "of", "in", "on", "at", "to", "for", "from", "by", "with",
    "without", "about", "into", "through", "over", "under", "between", "among",
    "across", "against", "during", "before", "after", "above", "below", "up",
    "down", "off", "out", "via", "per", "and", "or", "but", "nor", "so", "yet",
    "because", "while", "though", "although", "if", "than", "then", "when",
    "where", "which", "who", "whom", "whose", "what", "how", "why", "as", "is",
    "are", "was", "were", "be", "been", "being", "am", "do", "does", "did",
    "done", "have", "has", "had", "having", "will", "would", "can", "could",
    "shall", "should", "may", "might", "must", "it", "its", "he", "she", "they",
    "them", "their", "we", "us", "our", "you", "your", "i", "me", "my", "him",
    "her",
})

# A derailed trailing window is one whose function-word share falls below this
# fraction; normal prose (even dense technical writing) stays well above 0.1.
_DERAIL_FUNCTION_WORD_RATIO = 0.08

# ... or whose type-token ratio is this high.  A rambling "word-salad" stream
# keeps enough function words to defeat the ratio above, but it churns out an
# almost unbroken run of novel words, so nearly every token in a trailing window
# is unique — something normal prose (which reuses terms and closed-class words)
# never approaches.  This catches the high-diversity derailment the ratio alone
# misses.
_DERAIL_TYPE_TOKEN_RATIO = 0.85

# The type-token signal only counts as derailment when the window is ALSO low in
# function words (below this gate).  A genuinely useful summary — even a terse,
# varied one — still carries a normal share of determiners/prepositions; gating
# on it stops the novelty signal from firing on legitimate diverse prose and
# cutting a good section short, while still catching rambling word-salad, which
# drops well below this share of function words.
_DERAIL_TTR_FN_GATE = 0.25

# Correlation-like metrics are mathematically bounded to [-1, 1]: an information
# coefficient (IC) / rank-IC / correlation / R-squared can never exceed 1 in
# absolute value.  A small model under long or truncated context can emit a
# provably impossible value (e.g. "an average weekly IC of 3.32 and 6.68").  These
# patterns identify a value-bearing metric so the deterministic prune can strip
# anything outside the bound, with no reliance on the model.
_METRIC_BOUNDED_RE = re.compile(
    r"(?:information\s+coefficient|rank[\s-]?ic|\bic\b|correlation(?:\s+coefficient)?|"
    r"\br\s*squared\b|r\s*[²2]\b|coefficient\s+of\s+determination)",
    re.IGNORECASE,
)
_METRIC_VALUE_START_RE = re.compile(
    r"\s*(?:of|:|=|is)\s*-?\d+(?:[.,]\d+)?", re.IGNORECASE
)
_METRIC_VALUE_CONT_RE = re.compile(
    r"\s*(?:and|&|[,;/\u2013-]|\s)+\s*-?\d+(?:[.,]\d+)?", re.IGNORECASE
)
_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _prune_implausible_metric_figures(text: str) -> str:
    """Deterministically remove metric values that are physically impossible.

    Every generated summary figure is checked against the hard mathematical bound
    for correlation-like metrics (|value| <= 1).  Where a value violates it, the
    trailing numeric clause is dropped, leaving the metric named without a
    nonsensical number (e.g. "an average weekly IC of 3.32 and 6.68" becomes
    "an average weekly IC").  Applies regardless of what the model "believed",
    so a fabricated statistic can never reach the final answer.
    """
    if not text:
        return text
    parts: list[str] = []
    last = 0
    for match in _METRIC_BOUNDED_RE.finditer(text):
        rest = text[match.end() :]
        clause = _METRIC_VALUE_START_RE.match(rest)
        if not clause:
            continue
        end = match.end() + clause.end()
        span = text[end:]
        while True:
            cont = _METRIC_VALUE_CONT_RE.match(span)
            if not cont:
                break
            end += cont.end()
            span = text[end:]
        values = _NUM_RE.findall(text[match.end() + clause.start() : end])
        peak = 0.0
        for value in values:
            try:
                magnitude = abs(float(value.replace(",", "")))
            except ValueError:
                continue
            if magnitude > peak:
                peak = magnitude
        if peak > 1.0:
            parts.append(text[last : match.end()])
            last = end
    if not parts:
        return text
    parts.append(text[last:])
    return "".join(parts)


class _StreamAbortError(Exception):
    """Internal control-flow signal to stop a streaming window early."""


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

        # When authoritative "Chapter N" headings were detected, section numbers
        # from any other major are body-text noise (dataframe dumps, page stubs),
        # not real chapters — they must not spawn fabricated `[Chapter N]` lines.
        if ch_good:
            sec_entries = [s for s in sec_entries if s[0] in ch_good]

        # Group detected subsections by their parent chapter.
        sec_by_major: dict[int, list[tuple[str, str]]] = {}
        for major, sn, title in sec_entries:
            sec_by_major.setdefault(major, []).append((sn, title))

        # Build the index from the UNION of reliably-detected chapter headings
        # (ch_good) and chapters that have recognised subsections, so a chapter
        # whose heading was detected but whose section headers were not seen in
        # the probe chunks still appears instead of silently vanishing.
        chapter_nums = sorted(set(ch_good) | set(sec_by_major))

        lines: list[str] = []
        # Cap subsection detail per chapter so one long chapter cannot starve
        # the rest of the index, but never drop a chapter heading itself.
        max_subsections_per_chapter = 30
        for major in chapter_nums:
            sections = sec_by_major.get(major, [])
            ch_title = ch_titles.get(major)
            if ch_title and sections:
                first, _t = sections[0]
                lines.append(f"[Chapter {major}] {first} — {ch_title}")
            elif ch_title:
                lines.append(f"[Chapter {major}] — {ch_title}")
            elif sections:
                sn, title = sections[0]
                lines.append(f"[Chapter {major}] {sn} — {title}")
            else:
                continue
            for sn, title in sections[1 : max_subsections_per_chapter]:
                lines.append(f"  {sn} — {title}")

        if appendix_entries:
            lines.append("")
            for label, _src, title in appendix_entries:
                lines.append(f"[Appendix {label}] — {title}")

        header = (
            "DOCUMENT STRUCTURE INDEX (enumerate ALL of the following in your answer):\n"
            + "\n".join(lines)
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

    @staticmethod
    def _clean_chapter_title(title: str) -> str:
        """Return a TOC chapter title with its dot-leader and trailing page number removed.

        Table-of-contents chapter heads look like ``Chapter 8 The ML4T Workflow ....... 223``
        where the trailing digits are the page number.  Stripping the dot leader and page
        number yields a clean title (``The ML4T Workflow``) so every heading is consistent.
        """
        title = re.sub(r"\s*\.{2,}[.\-\u2013\u2014]*", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        title = re.sub(r"[\s.\u2026:\-\u2013\u2014]*\d+\s*$", "", title)
        return title.strip(" \t\r\n.:;-\u2013\u2014")

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
            r"((?:(?!\.{2,})(?!\s+\d{1,4}\s*[\r\n])(?!\n\s*(?:\n|(?:Chapter|Module|Lesson|Appendix)\s+\d+))"
            r"[A-Za-z0-9 ,'\-():/\s.\u2013\u2014]){2,120})",
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
                title = self._clean_chapter_title(nm.group(3))
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
                title = self._clean_chapter_title(am.group(2))
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

        # Authoritative "Chapter N" headings (from chapter_n_re in pass 1) define
        # the true chapter span.  When present, bare-number and section matches
        # may corroborate within that span but must not invent chapters beyond
        # it — otherwise noisy body text (e.g. "12 Selection and Assignment" or
        # dataframe dumps) fabricates chapters for books whose chapters are all
        # explicitly labeled "Chapter N".
        auth_max = max((e[0] for e in entries), default=0)

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
                if (
                    major < 1
                    or major > 30
                    or (auth_max > 0 and major > auth_max)
                    or (major, source) in seen
                ):
                    continue
                title = self._clean_chapter_title(bm.group(2))
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
                title = self._clean_chapter_title(bam.group(2))
                if len(title) < 4:
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

            for fm in ft_catch.finditer(raw):
                major_ft = int(fm.group(1))
                if (
                    major_ft < 1
                    or major_ft > 30
                    or (auth_max > 0 and major_ft > auth_max)
                    or (major_ft, source) in seen
                ):
                    continue
                title_ft = self._clean_chapter_title(fm.group(2))
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
            List of chunk dicts with 'chunk_text', 'page_number',
            'source_file', 'chunk_id'.
        """
        # Structural roles that signal TOC/section/heading content.  The Qdrant
        # OR-filter matches a chunk when its element_type OR chunk_role is one of
        # these — identical to the former Mongo "$or" query.
        element_types = [
            "heading",
            "toc_entry",
            "body",
            "paragraph",
            "title",
            "section",
            "header",
        ]
        chunk_roles = [
            "body",
            "caption",
            "navigation",
            "heading",
            "toc_entry",
            "title",
            "section",
            "header",
        ]
        storage = self._searcher.storage
        try:
            result = list(
                storage.find_structural_chunks(
                    element_types=element_types,
                    chunk_roles=chunk_roles,
                    source_prefix=source_filter,
                    limit=10000,
                )
            )
            if len(result) < 5:
                # Fall back to ALL chunks for the source (or all chunks when no
                # source_filter given), ordered by page and limited to top_k —
                # preserves the former Mongo fallback query.
                result = list(
                    storage.find_structural_chunks(
                        source_prefix=source_filter,
                        limit=top_k,
                    )
                )
        except Exception:  # storage unavailable → no structure to probe
            logger.debug("Structure probing failed", exc_info=True)
            return []
        return [dict(c) for c in result]

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
        answer, streamed = self._stream_generate(prompt)
        if not streamed and self._on_chunk and answer:
            self._on_chunk(answer, None)
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
                    prefix == "" or prefix.endswith((".", "!", "?")) or prefix.endswith("\n")
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
        temp = (
            temperature
            if temperature is not None
            else self._config.llm_temperature
        )
        tokens = (
            max_tokens if max_tokens is not None else self._config.llm_max_tokens
        )
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
        """Produce a chapter-by-chapter overview via one bounded call per chapter.

        Map-reduce for broad-coverage "summarize by chapter" queries. Instead of
        sending every chapter's content to the LLM in a single prompt (which
        overflows the output token budget and degenerates into token-soup after a
        few chapters), each chapter is summarised independently from just its own
        bucket, then the results are concatenated under chapter headings.  The
        number of windows is guarded by ``_MAX_MAP_REDUCE_WINDOWS`` — a generous
        safety ceiling there to bound pathological fan-out, not a normal limit —
        so a full book summarized by chapter is processed in full.
        """
        items: list[tuple[str, str]] = []
        for ch_num in chapter_keys:
            bucket = chapter_buckets.get(ch_num)
            if not bucket:
                continue
            ctx = self._format_context(
                bucket, max_chars=self._config.rag_summary_context_chars
            )
            if not ctx.strip():
                continue
            title = ch_titles.get(ch_num, "")
            heading = f"Chapter {ch_num}" + (f" — {title}" if title else "")
            prompt = self._build_prompt(
                (
                    f"Provide a brief, focused summary of {heading} using ONLY "
                    "the document content below. 2-4 sentences. Never add "
                    "information from outside this document or from prior "
                    "knowledge."
                ),
                ctx,
            )
            items.append((heading, prompt))

        return _prune_implausible_metric_figures(self._map_reduce_stream(items))

    def _generate_single_chapter_summary(
        self,
        chunks: list[dict[str, Any]],
        chapter_num: int | str,
        chapter_title: str,
    ) -> str:
        """Produce a detailed, section-by-section summary of one chapter.

        Map-reduce within a single chapter.  Feeding a whole chapter in one call
        makes the model enumerate every section in a single long response, which
        degrades; instead the chapter's chunks are grouped by their section and
        each section is summarised independently, then concatenated under
        ``Section 18.N`` headings.  Unlabeled chunks are folded into the section
        they follow, and the sections are ordered numerically so the output reads
        top-to-bottom regardless of the order the chunks arrived in.  Groups are
        guarded by ``_MAX_MAP_REDUCE_WINDOWS`` — a generous safety ceiling against
        pathological fan-out, not a normal limit.
        """
        by_label: dict[str, list[dict[str, Any]]] = {}
        current_label: str | None = None
        for chunk in chunks:
            text = chunk.get("chunk_text", chunk.get("text", ""))
            label = self._detect_section_label(text, chapter_num)
            if label is not None:
                current_label = label
            key = current_label if current_label is not None else "__overview__"
            by_label.setdefault(key, []).append(chunk)

        # Order numerically: the unlabeled overview block first, then sections in
        # ascending section number (18.1, 18.2, ... 18.15), independent of the
        # order the chunks were retrieved in.
        def _order_key(key: str) -> tuple[int, int]:
            if key == "__overview__":
                return (0, 0)
            return (1, int(key.split(".")[1]))

        logger.info(
            "single-chapter summary: %d chunk(s) -> %d section group(s): %s",
            len(chunks),
            len(by_label),
            sorted(by_label, key=_order_key),
        )

        items: list[tuple[str, str]] = []
        for key in sorted(by_label, key=_order_key):
            heading = (
                f"Chapter {chapter_num} (overview)"
                if key == "__overview__"
                else f"Section {key}"
            )
            ctx = self._format_context(
                by_label[key],
                max_chars=self._config.rag_summary_context_chars,
            )
            if not ctx.strip():
                continue
            prompt = self._build_prompt(
                (
                    f"Summarize {heading} of chapter {chapter_num} "
                    f"({chapter_title}) comprehensively, using ONLY the document "
                    "content below. Cover the main topics, key concepts, and "
                    "important details in a clear, well-organized overview. Be "
                    "thorough but focused; do not pad. Write the ENTIRE summary "
                    "once, in a single response: do not produce multiple drafts "
                    "and do not re-summarize or restate the chapter a second "
                    "time. Never add information from outside this document or "
                    "from prior knowledge. Do not invent specific figures such "
                    "as accuracy percentages, parameter counts, epoch counts, "
                    "years, number of classes, or dataset sizes: only cite a "
                    "number if you can read it directly in the provided content, "
                    "otherwise describe the point qualitatively. Do not try to "
                    "recall, verify, or second-guess exact figures: if a number "
                    "is not clearly written in the provided content, move on "
                    "without guessing. Do not repeat points you have already "
                    "covered. Present the overview as one confident, flowing "
                    "response."
                ),
                ctx,
            )
            items.append((heading, prompt))

        # Figure re-grounding targets the whole-chapter-in-one-window case (no
        # sections detected), where a small model can misstate numbers.  Sectioned
        # output is already summarized per-section from a small context, so it is
        # more grounded and needs no extra pass.
        result = self._map_reduce_stream(items)
        if set(by_label) == {"__overview__"}:
            result = self._refine_figures(result, chunks)
        return _prune_implausible_metric_figures(result)

    def _refine_figures(
        self,
        text: str,
        chunks: list[dict[str, Any]],
    ) -> str:
        """Re-ground the figures in a draft summary against the source content.

        A summary window sees only a bounded slice of a chapter, so a small model can
        misstate a number (e.g. write "2021 ILSVRC, top-5 42%" for AlexNet when the
        source says 2012 / 16%). This focused, low-temperature pass re-reads the draft
        alongside the same source content and corrects ONLY the figures (years,
        percentages, parameter counts, epoch counts, dataset sizes, class counts),
        leaving all other wording and structure intact. It is guarded to fall back to
        the draft unchanged whenever the correction is unusable or collapses, so it can
        never make the summary worse.
        """
        if not text or not text.strip():
            return text
        ctx = self._format_context(
            chunks, max_chars=self._config.rag_summary_context_chars
        )
        if not ctx.strip():
            return text
        draft = text if len(text) <= 6000 else text[:6000]
        query = (
            "Correct the factual figures in the draft chapter summary below so they "
            "exactly match the provided source content. Fix ONLY numbers: years, "
            "percentages, parameter counts, epoch counts, dataset sizes, and class "
            "counts. Where a figure in the draft differs from the source, write the "
            "source's value; where the draft gives a figure the source does not "
            "contain, rephrase that point qualitatively without a number. Change "
            "nothing else — keep the same wording, structure, heading, and overall "
            "length. Output only the corrected summary, with no preamble or notes."
            f"\n\nDRAFT SUMMARY:\n{draft}"
        )
        prompt = self._build_prompt(query, ctx)
        corrected = self._llm_provider.generate(
            prompt=prompt,
            temperature=0.2,
            max_tokens=_RETRY_MAX_TOKENS,
        )
        if (
            corrected
            and self._is_acceptable(corrected)
            and len(corrected) >= len(text) * 0.5
        ):
            return corrected.strip()
        logger.warning("figure-refinement pass unusable; keeping draft unchanged")
        return text

    @staticmethod
    def _detect_section_label(
        text: str, chapter_num: int | str
    ) -> str | None:
        """Return the section key (e.g. ``"18.2"``) a chunk belongs to, if any.

        Only honours a section number that appears at a *heading* position (start
        of the chunk or start of a line), where true section headers live.  A
        line-start ``18.N`` is ignored when the preceding text is a
        figure/table/equation/listing reference (e.g. a wrapped "Figure [newline]
        18.2"), which would otherwise fabricate phantom sections from captions;
        such content folds into the chapter overview.
        """
        chapter_s = str(chapter_num)
        heading_re = re.compile(
            rf"(?:^|\n)\s*{re.escape(chapter_s)}\.(\d+)\b"
        )
        ref_indicator = re.compile(
            r"(figure|table|equation|listing|eq\.?|page|p\.)\s*$",
            re.IGNORECASE,
        )
        for m in heading_re.finditer(text):
            if ref_indicator.search(text[: m.start()]):
                continue
            return f"{chapter_s}.{m.group(1)}"
        return None

    def _map_reduce_stream(self, items: list[tuple[str, str]]) -> str:
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

        Returns the concatenated answer (falling back to it when no content was
        streamed at all).
        """
        if not items:
            return ""
        capped = items[:_MAX_MAP_REDUCE_WINDOWS]
        parts: list[tuple[str, str]] = []
        for heading, prompt in capped:
            summary = self._trim_rehashed_tail(
                self._generate_window_guarded(prompt, heading)
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
        Sampling uses the summary-specific ``llm_summary_temperature`` /
        ``llm_max_tokens`` (unless overridden) — summary windows run at a lower
        temperature than general chat to avoid mid-summary degeneration.

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
        temp = temperature if temperature is not None else self._config.llm_summary_temperature
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

        buffered: list[str] = []  # everything streamed (incl. any derailed tail)
        clean: list[str] = []  # longest prefix that stayed acceptable as it streamed
        heading_shown = False
        derailed = False

        def on_chunk(content: str, reasoning: str | None) -> None:
            nonlocal heading_shown
            if reasoning and self._on_chunk:
                self._on_chunk("", reasoning)
            if content:
                buffered.append(content)
                # Flush before streaming a chunk that would trip the flood guard,
                # so a derailed tail is never surfaced, and never reaches `clean`.
                if self._is_flooding("".join(buffered)):
                    raise _StreamAbortError()
                if self._on_chunk:
                    if not heading_shown:
                        self._on_chunk(f"{heading}\n\n", None)
                        heading_shown = True
                    self._on_chunk(content, None)
                clean.append(content)

        messages = [{"role": "user", "content": prompt}]
        try:
            self._llm_provider.stream_chat(
                messages=messages,
                on_chunk=on_chunk,
                temperature=temp,
                max_tokens=tokens,
            )
        except _StreamAbortError:
            derailed = True
        except RuntimeError as e:
            if not isinstance(e.__cause__, _StreamAbortError):
                raise
            derailed = True

        # A window that derailed mid-stream is incomplete: the clean prefix ends
        # at the degradation point, dropping whatever the chapter covered after it.
        # Retry at low temperature to salvage a complete, stable summary instead of
        # surfacing a chapter cut off mid-way.  Only when the retry is also unusable
        # do we fall back to the clean prefix (or skip).
        if derailed:
            logger.warning(
                "RAG window degraded mid-stream; retrying at low temperature for a complete summary"
            )
            retry = self._low_temp_retry(prompt, heading_shown, heading, max_tokens=tokens)
            if retry is not None:
                return retry

        # Word-salad is judged on this COMPLETED window — reliable, unlike a
        # mid-stream partial — so a legitimate dense summary passes here, while a
        # genuine whole-window salad falls through to a low-temperature retry below.
        text = "".join(clean)
        if self._is_plausible_summary(text) and not self._looks_derailed(text):
            return text
        logger.warning(
            "RAG window derailed before producing usable content; retrying at low temperature"
        )
        retry = self._low_temp_retry(prompt, heading_shown, heading, max_tokens=_RETRY_MAX_TOKENS)
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
        retry = self._llm_provider.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        if not self._is_acceptable(retry):
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
        if not self._is_plausible_summary(text):
            return True
        return self._is_extreme_salad(text)

    def _is_extreme_salad(self, text: str) -> bool:
        """Return True when recent text is agrammatic word-salad.

        The mid-stream guard is repetition-agnostic, so high-diversity salad can
        pass the plausibility check and stream unbounded.  This catches the
        low-function-word signal on its own.  The threshold is deliberately
        extreme (< 8% function words) so a legitimate dense technical summary,
        which always retains a normal share of determiners/prepositions, is never
        truncated.
        """
        if len(text.strip()) < _STREAM_FLOOD_MIN_CHARS:
            return False
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())[-150:]
        if len(tokens) < 60:
            return False
        function_count = sum(1 for t in tokens if t in _FUNCTION_WORDS)
        return function_count / len(tokens) < _DERAIL_FUNCTION_WORD_RATIO

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

    def _list_sources_result(self, query: str) -> dict[str, Any]:
        """Build a deterministic answer enumerating ALL distinct sources.

        Routes around vector search on purpose: semantic search is bounded by
        ``top_k`` and relevance, so it would silently drop sources as the
        corpus grows. A native ``distinct`` aggregation returns every unique
        source regardless of database size.

        Returns a result dict whose "answer" is a numbered enumeration of the
        source files (no LLM call, no embedding generation).
        """
        try:
            source_files: list[str] = list(self._searcher.list_source_files())
        except Exception as e:
            logger.warning("list_source_files failed: %s: %s", type(e).__name__, e)
            return {
                "answer": "I couldn't list the stored sources right now. Please try again.",
                "query": query,
                "list_sources": True,
            }

        source_files = sorted({s for s in source_files if s}, key=str.lower)

        if not source_files:
            return {
                "answer": (
                    "I don't have any documents stored yet. "
                    "Ingest some with `secondbrain ingest <path>` first."
                ),
                "query": query,
                "list_sources": True,
            }

        plural = "source" if len(source_files) == 1 else "sources"
        lines = [f"I found {len(source_files)} unique {plural}:"]
        lines.extend(f"  {i}. {s}" for i, s in enumerate(source_files, 1))
        return {
            "answer": "\n".join(lines),
            "query": query,
            "list_sources": True,
        }

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
