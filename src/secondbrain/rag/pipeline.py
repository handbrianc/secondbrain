"""RAG pipeline for orchestrating retrieval and generation.

This module provides the RAGPipeline class that orchestrates the complete
Retrieval-Augmented Generation workflow for conversational Q&A.
"""

import logging
import re
import time
from contextlib import suppress
from typing import Any

from secondbrain.config import config
from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.intent_parser import IntentDecision, QueryIntent, StructuralIntentParser
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.security_filter import SecurityFilter
from secondbrain.document.scoped_retriever import ScopedRetriever
from secondbrain.search import Searcher
from secondbrain.utils.perf_monitor import metrics
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)

BROAD_COVERAGE_TRIGGERS: frozenset[str] = frozenset(
    [
        "all",
        "every",
        "each",
        "summarize each",
        "summary of each",
        "list every",
        "list all sections",
        "list all chapters",
        "brief on each",
        "overview of all",
        "give me an overview",
        "comprehensive summary",
    ]
)

CHAPTER_ENUMERATION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"chapter", re.I),
    re.compile(r"\bch\.?\s*\d+\b", re.I),
    re.compile(
        r"(?<!\w)(\d{1,2})\s*\.{1,3}(?:intro|overview|summary|introduction)",
        re.I,
    ),
]

ENUMERATE_CHAPTER_SIGNALS: frozenset[str] = frozenset(
    [
        "all",
        "every",
        "each",
        "list",
        "summarize",
        "overview",
        "summary",
        "give me",
        "enumerate",
    ]
)

__all__ = ["RAGPipeline"]


class RAGPipeline:
    """Orchestrates retrieval and generation for conversational RAG.

    The RAGPipeline coordinates the complete RAG workflow:
    1. Query rewriting (for multi-turn conversations)
    2. Context retrieval from vector storage via Searcher
    3. Prompt building with context and history
    4. Response generation using local LLM

    Supports both single-turn queries and multi-turn chat sessions.

    Attributes:
        searcher: Searcher instance for semantic search.
        llm_provider: LocalLLMProvider for generation.
        rewriter: Optional QueryRewriter for context-aware queries.
        top_k: Default number of context chunks to retrieve.
        context_window: Number of messages to keep in conversation context.

    Example:
        >>> searcher = Searcher()
        >>> # llm_provider = get_llm_provider()  # Get your configured provider
        >>> rewriter = QueryRewriter(llm_provider)
        >>> pipeline = RAGPipeline(searcher, llm_provider, rewriter)
        >>> result = pipeline.query("What is machine learning?")
        >>> print(result["answer"])
    """

    def __init__(
        self,
        searcher: Searcher,
        llm_provider: LocalLLMProvider,
        rewriter: QueryRewriter | None = None,
        top_k: int | None = None,
        context_window: int = 5,
    ) -> None:
        """Initialize RAG pipeline with components.

        Args:
            searcher: Searcher instance for semantic search.
            llm_provider: LocalLLMProvider for generation.
            rewriter: QueryRewriter for context-aware queries (optional).
            top_k: Number of chunks to retrieve (default: 5).
            context_window: Messages to keep in context (default: 5 per spec).

        Example:
            >>> searcher = Searcher()
            >>> # llm_provider = get_llm_provider()  # Get your configured provider
            >>> pipeline = RAGPipeline(searcher, llm_provider, top_k=10)
        """
        self._searcher = searcher
        self._scoper = ScopedRetriever(inner=self._searcher)  # type: ignore[arg-type]
        self._llm_provider = llm_provider
        self._rewriter = rewriter
        self._top_k = top_k if top_k is not None else config().default_top_k
        self._context_window = context_window
        self._config = config()
        self._intent_parser = StructuralIntentParser(self._config)
        self._security_filter = SecurityFilter()

    def query(
        self,
        query: str,
        top_k: int | None = None,
        show_sources: bool = False,
    ) -> dict[str, Any]:
        """Perform single-turn RAG query.

        Args:
            query: User query text.
            top_k: Override default number of chunks to retrieve.
            show_sources: Include retrieved chunks in response.

        Returns:
            Dict with keys:
            - "answer": Generated answer text
            - "sources": List of retrieved chunks (if show_sources=True)
            - "query": Original query (or rewritten if applicable)

        Example:
            >>> pipeline = RAGPipeline(searcher, llm_provider)
            >>> result = pipeline.query("What is secondbrain?")
            >>> result["answer"]
            "SecondBrain is a document intelligence CLI tool..."
        """
        # Validate query is not empty or whitespace-only
        if not query or not query.strip():
            return {
                "answer": "Query cannot be empty. Please provide a valid question.",
                "query": query,
                "validation_error": True,
            }

        try:
            violations = self._security_filter.validate_query(query)
            if violations:
                logger.warning(
                    "Security violation detected: %s",
                    [v.violation_type for v in violations],
                )
                return {
                    "answer": self._security_filter.get_safe_response(),
                    "query": query,
                    "security_blocked": True,
                }

            effective_top_k = top_k if top_k is not None else self._top_k

            # --- B4: Iterative RAG for broad-coverage and chapter-enumeration queries ---
            intent_result = self._intent_parser.parse(query)
            if intent_result.intent in (
                QueryIntent.BROAD_COVERAGE,
                QueryIntent.CHAPTER_ENUMERATE,
            ):
                return self._iterative_query(
                    query,
                    top_k=effective_top_k,
                    show_sources=show_sources,
                )

            # Step 1: Retrieve chunks via searcher.search()
            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval") as span:
                    if span:
                        span.set_attribute("rag.query", query)
                        span.set_attribute("rag.top_k", effective_top_k)
                    chunks = self._searcher.search(query, top_k=effective_top_k)
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency", retrieval_duration)
                logger.debug("retrieval_latency: %.3fs", retrieval_duration)

            # Step 2: Handle no results
            if not chunks:
                fallback_answer = self._handle_no_results(query)
                result: dict[str, Any] = {"answer": fallback_answer, "query": query}
                if show_sources:
                    result["sources"] = []
                return result

            # Step 3: Format context from chunks
            context_text = self._format_context(chunks)

            # Step 4: Build prompt with context + query
            prompt = self._build_prompt(query, context_text)

            # Step 5: Generate answer via llm_provider.generate() OR stream_chat()
            generation_start = time.perf_counter()
            answer = ""
            try:
                with trace_operation("rag_generation") as span:
                    if span:
                        span.set_attribute("rag.prompt_length", len(prompt))
                        span.set_attribute(
                            "rag.temperature", self._config.llm_temperature
                        )
                        span.set_attribute(
                            "rag.max_tokens", self._config.llm_max_tokens
                        )

                    if self._config.streaming_enabled and hasattr(
                        self._llm_provider, "stream_chat"
                    ):
                        try:
                            messages = [{"role": "user", "content": prompt}]
                            accumulated: list[str] = []

                            def on_chunk(content: str, _reasoning: str | None) -> None:
                                if content:
                                    accumulated.append(content)

                            self._llm_provider.stream_chat(
                                messages=messages,
                                on_chunk=on_chunk,
                                temperature=self._config.llm_temperature,
                                max_tokens=self._config.llm_max_tokens,
                            )
                            answer = "".join(accumulated)
                        except Exception as streaming_err:
                            logger.warning(
                                "Streaming failed, falling back to generate(): %s: %s",
                                type(streaming_err).__name__,
                                streaming_err,
                            )
                            answer = ""

                    if not answer or not answer.strip():
                        answer = self._llm_provider.generate(
                            prompt=prompt,
                            temperature=self._config.llm_temperature,
                            max_tokens=self._config.llm_max_tokens,
                        )

                    if span:
                        span.set_attribute("rag.answer_length", len(answer))
            finally:
                generation_duration = time.perf_counter() - generation_start
                metrics.record("generation_latency", generation_duration)
                logger.debug("generation_latency: %.3fs", generation_duration)

            # Step 6: Build result dict
            result = {"answer": answer, "query": query}
            if show_sources:
                result["sources"] = chunks

            return result

        except Exception as e:
            logger.error("Query failed: %s: %s", type(e).__name__, e)
            return self._create_error_response(str(e), query)

    def chat(
        self,
        query: str,
        session: ConversationSession,
        top_k: int | None = None,
        show_sources: bool = False,
    ) -> dict[str, Any]:
        """Perform multi-turn conversational RAG.

        Args:
            query: Current user query.
            session: ConversationSession with history.
            top_k: Override default number of chunks.
            show_sources: Include retrieved chunks.

        Returns:
            Dict with keys:
            - "answer": Generated answer
            - "sources": Retrieved chunks (if show_sources)
            - "rewritten_query": Query after rewriting (if applicable)

        Example:
            >>> session = ConversationSession.load("session-123", storage)
            >>> result = pipeline.chat("What about pricing?", session)
            >>> result["answer"]
            "The ACME contract pricing is $100/month..."
        """
        try:
            effective_top_k = top_k if top_k is not None else self._top_k

            # --- B4: Iterative RAG for broad-coverage and chapter-enumeration queries ---
            intent_result = self._intent_parser.parse(query)
            if intent_result.intent in (
                QueryIntent.BROAD_COVERAGE,
                QueryIntent.CHAPTER_ENUMERATE,
            ):
                return self._iterative_query(
                    query,
                    top_k=effective_top_k,
                    show_sources=show_sources,
                )

            # Step 1: Rewrite query using conversation history (if rewriter available)
            rewritten_query = self._rewrite_query_with_history(query, session)

            # Step 2: Retrieve chunks via searcher.search()
            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval") as span:
                    if span:
                        span.set_attribute("rag.query", rewritten_query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", True)
                    chunks = self._searcher.search(
                        rewritten_query, top_k=effective_top_k
                    )

                    # --- C2: Track seen pages in session ---
                    if session is not None and chunks:
                        with suppress(Exception):
                            session.mark_pages_seen(chunks)

                    # --- C3: Bias toward unseen pages (reshuffle so unseen float to top) ---
                    if session is not None and session.seen_pages and chunks:
                        unseen_first: list[dict[str, Any]] = []
                        seen_last: list[dict[str, Any]] = []
                        for c in chunks:
                            sp = c.get("page_number")
                            sf = c.get("source_file", "")
                            if (
                                sp is not None
                                and sf in session.seen_pages
                                and sp in session.seen_pages[sf]
                            ):
                                seen_last.append(c)
                            else:
                                unseen_first.append(c)
                        # Bias: unseen pages preferred, seen pages kept at end of results
                        chunks = unseen_first + seen_last

                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency", retrieval_duration)
                logger.debug("retrieval_latency: %.3fs", retrieval_duration)

            # Step 3: Handle no results
            if not chunks:
                fallback_answer = self._handle_no_results(query)
                result: dict[str, Any] = {
                    "answer": fallback_answer,
                    "rewritten_query": rewritten_query,
                }
                if show_sources:
                    result["sources"] = []
                return result

            # Step 4: Format context from chunks + conversation history
            context_text = self._format_context(chunks)
            history = session.get_history(limit=self._context_window)

            # Step 5: Build prompt with system instruction + context + query
            prompt = self._build_prompt(rewritten_query, context_text, history)

            # Step 6: Generate answer via llm_provider.generate() OR stream_chat() with retry logic
            generation_start = time.perf_counter()
            answer = ""
            max_retries = self._config.rag_max_retries
            retry_count = 0
            try:
                while retry_count < max_retries:
                    with trace_operation("rag_generation") as span:
                        if span:
                            span.set_attribute("rag.prompt_length", len(prompt))
                            span.set_attribute(
                                "rag.temperature", self._config.llm_temperature
                            )
                            span.set_attribute(
                                "rag.max_tokens", self._config.llm_max_tokens
                            )
                            span.set_attribute("rag.is_chat", True)
                            span.set_attribute("rag.retry_attempt", retry_count + 1)

                        if self._config.streaming_enabled and hasattr(
                            self._llm_provider, "stream_chat"
                        ):
                            try:
                                messages = [{"role": "user", "content": prompt}]
                                accumulated: list[str] = []

                                def on_chunk(
                                    content: str, _reasoning: str | None
                                ) -> None:
                                    if content:
                                        accumulated.append(content)  # noqa: B023

                                self._llm_provider.stream_chat(
                                    messages=messages,
                                    on_chunk=on_chunk,
                                    temperature=self._config.llm_temperature,
                                    max_tokens=self._config.llm_max_tokens,
                                )
                                answer = "".join(accumulated)
                            except Exception as streaming_err:
                                logger.warning(
                                    "Streaming failed on attempt %d, falling back to generate(): %s: %s",
                                    retry_count + 1,
                                    type(streaming_err).__name__,
                                    streaming_err,
                                )
                                answer = ""

                        if not answer or not answer.strip():
                            answer = self._llm_provider.generate(
                                prompt=prompt,
                                temperature=self._config.llm_temperature,
                                max_tokens=self._config.llm_max_tokens,
                            )

                        if span:
                            span.set_attribute("rag.answer_length", len(answer))

                    if answer and answer.strip():
                        logger.debug(
                            "Generation successful on attempt %d, answer length: %d",
                            retry_count + 1,
                            len(answer),
                        )
                        break

                    retry_count += 1
                    logger.warning(
                        "Empty LLM response received (attempt %d/%d). Retrying...",
                        retry_count,
                        max_retries,
                    )

                    if retry_count < max_retries:
                        time.sleep(0.5)

                if not answer or not answer.strip():
                    logger.error(
                        "Empty LLM response after %d attempts. Returning fallback response.",
                        max_retries,
                    )
                    fallback_answer = self._handle_no_results(query)
                    result = {
                        "answer": fallback_answer,
                        "rewritten_query": rewritten_query,
                        "empty_response_retries": max_retries,
                    }
                    if show_sources:
                        result["sources"] = chunks
                    return result

            finally:
                generation_duration = time.perf_counter() - generation_start
                metrics.record("generation_latency", generation_duration)
                logger.debug("generation_latency: %.3fs", generation_duration)
                if retry_count > 0:
                    metrics.record("generation_retries", retry_count)

            # Step 7: Add answer to session via session.add_message()
            session.add_message("user", query)
            session.add_message("assistant", answer)

            # Step 8: Build result dict
            result = {"answer": answer, "rewritten_query": rewritten_query}
            if show_sources:
                result["sources"] = chunks

            return result

        except Exception as e:
            logger.error("Chat failed: %s: %s", type(e).__name__, e)
            return self._create_error_response(str(e), query)

    def _derive_chapter_roster(self, structure_chunks: list[dict[str, Any]]) -> str:
        import re

        entries: list[tuple[int, str, str]] = []

        def _parse_chunk(chunk_text: str) -> tuple[str, str]:
            if not chunk_text:
                return "", "Unknown"
            cleaned = re.sub(r'^[. ]+', '', chunk_text)
            if not cleaned:
                return "", "Unknown"
            i = 0
            while i < len(cleaned):
                if not cleaned[i].isdigit():
                    i += 1
                    continue
                j = i
                while j < len(cleaned) and cleaned[j].isdigit():
                    j += 1
                if j >= len(cleaned) or cleaned[j] != '.':
                    i = j if j < len(cleaned) else i + 1
                    continue
                k = j + 1
                has_subseg = False
                while k < len(cleaned) and cleaned[k].isdigit():
                    has_subseg = True
                    k += 1
                    while k < len(cleaned) and cleaned[k] == '.':
                        k += 1
                        while k < len(cleaned) and cleaned[k].isdigit():
                            k += 1
                section_num = cleaned[i:k]
                after = cleaned[k:]
                if not has_subseg:
                    if k < len(cleaned) and not cleaned[k].isspace():
                        i = k + 1
                        continue
                if section_num.count('.') >= 2:
                    i = k + 1
                    continue
                title_candidate = after.lstrip()
                title_candidate = re.sub(r'\s+\.{2,}', ' ', title_candidate)
                title_candidate = re.sub(r'\s+\d{1,3}\s*$', '', title_candidate)
                title_candidate = title_candidate.rstrip('.').rstrip()[:200]
                if len(title_candidate) < 4 or not title_candidate[0].isalpha():
                    i = k + 1
                    continue
                break
            else:
                return "", "Unknown"
            return section_num, title_candidate

        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            sn, title = _parse_chunk(raw)
            if sn:
                try:
                    major = int(sn.split(".")[0])
                except ValueError:
                    major = 999
                if major > 30:
                    continue
                entries.append((major, sn, title))
        entries.sort(key=lambda x: (x[0], *[int(p) for p in x[1].split(".") if p]))
        lines: list[str] = []
        prev_major: int | None = None
        for _, sn, title in entries:
            major = int(sn.split(".")[0]) if sn else 0
            if prev_major != major:
                lines.append(f"[Chapter {major}] {sn} — {title}")
                prev_major = major
            else:
                lines.append(f"  {sn} — {title}")
        header = (
            "CHAPTER/SECTION INDEX (enumerate ALL of the following in your answer):\n"
            + "\n".join(lines[:50])
            + "\n\n"
        )
        return header

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

            # Truncate chunk if too long
            if len(chunk_text) > self._config.rag_chunk_preview_chars:
                chunk_text = chunk_text[: self._config.rag_chunk_preview_chars] + "..."

            source_line = f"Source: {source_file} (page {page})"
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

    def _derive_chapter_numbers(
            self, structure_chunks: list[dict[str, Any]]
        ) -> list[tuple[int, str, str]]:
            import re
            entries: list[tuple[int, str, str]] = []
            seen: set[tuple[int, str]] = set()
            DOT_LEADER = re.compile(r"\.{2,}[.\-]+")
            SEC_RE = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
            CHAPTER_N_RE = re.compile(r"Chapter\s+(\d+)\s+(.{2,60})", re.IGNORECASE)
            BARE_CHAPTER_RE = re.compile(
                r"(?:^|\n)\s*(\d{1,2})[\.\s]+\s*([A-Z][A-Za-z0-9\s\-\(\),'/]{4,80})",
                re.MULTILINE,
            )
            seen_sec: set[int] = set()
            for chunk in structure_chunks:
                raw = chunk.get("chunk_text", "")
                source = chunk.get("source_file", "")
                cleaned = DOT_LEADER.sub("", raw, count=1).strip()

                for nm in CHAPTER_N_RE.finditer(raw):
                    major = int(nm.group(1))
                    if major < 1 or major > 30 or (major, source) in seen:
                        continue
                    title = nm.group(2).strip().rstrip(".")
                    if len(title) < 2:
                        continue
                    seen.add((major, source))
                    entries.append((major, source, title))

                for bm in BARE_CHAPTER_RE.finditer(raw):
                    major = int(bm.group(1))
                    if major < 1 or major > 30 or (major, source) in seen:
                        continue
                    title = bm.group(2).strip().rstrip(".")
                    if len(title) < 4:
                        continue
                    seen.add((major, source))
                    entries.append((major, source, title))

                for m in SEC_RE.finditer(cleaned):
                    major = int(m.group(1))
                    # Skip if chapter already found by CHAPTER_N_RE/BARE_CHAPTER_RE
                    # (those have better titles than subsection-level SEC_RE)
                    if major < 1 or major > 30 or major in seen_sec or (major, source) in seen:
                        continue
                    raw_title = (m.group(3) or "").strip()
                    clean_title = raw_title.rstrip(".")
                    if len(clean_title) < 2:
                        continue
                    seen_sec.add(major)
                    entries.append((major, source, clean_title))

            entries.sort(key=lambda x: x[0])
            return entries

    def _is_broad_coverage_query(self, query: str) -> bool:
        q = query.lower().strip()
        return any(t in q for t in BROAD_COVERAGE_TRIGGERS)

    def _probe_document_structure(self, top_k: int = 400) -> list[dict[str, Any]]:
        """Probe for document structural elements (TOC/section headers) via chunk_role.

        Attempts targeted structural-role filters first; falls back to raw
        top-K retrieval when few candidates are found (handles documents whose
        chunks lack explicit element_type/chunk_role markers).

        Args:
            top_k: How many structural candidates to retrieve (default 400).

        Returns:
            List of chunk dicts with '_id', 'chunk_text', 'page_number',
            'source_file', 'chunk_id'.
        """
        from pymongo import MongoClient
        from secondbrain.config import config
        cfg = config()
        client = MongoClient(cfg.mongo_uri, directConnection=True)
        coll = client[cfg.mongo_db][cfg.mongo_collection]
        cursor = (
            coll.find(
                {
                    "$or": [
                        {"element_type": {"$in": ["heading", "toc_entry", "body", "paragraph"]}},
                        {"chunk_role": {"$in": ["body", "caption", "navigation", "heading", "toc_entry"]}},
                    ]
                },
                {"_id": 0, "chunk_text": 1, "page_number": 1, "source_file": 1, "chunk_id": 1},
            )
            .limit(400)
        )
        result = list(cursor)
        if len(result) < 5:
            result = list(
                coll.find(
                    {},
                    {"_id": 0, "chunk_text": 1, "page_number": 1, "source_file": 1, "chunk_id": 1},
                ).limit(top_k)
            )
        return result

    def _generic_one_shot(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any]:
        """Fallback one-shot retrieval when document structure probing fails."""
        chunks = self._searcher.search(query, top_k=top_k)
        if not chunks:
            return {"answer": f"No relevant documents found for: {query}", "query": query}
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

    def _iterative_query(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any]:
        """Handle broad-coverage queries via iterative structural traversal.

        Instead of one-shot top-k similarity, walks document structure
        by probing TOC/section elements and querying per-section ranges,
        then deduplicates across iterations.

        Args:
            query: Original user query.
            top_k: Number of chunks to aim for overall.
            show_sources: Whether to include sources in response.

        Returns:
            dict with 'answer', 'query', 'sources' (if show_sources).
        """
        # 1. Probe document structure for TOC/chapter chunks via chunk_role
        structure_chunks = self._probe_document_structure(top_k=400)
        if not structure_chunks:
            # Fall back to generic one-shot if no structure found
            return self._generic_one_shot(query, top_k, show_sources)

        intent_decision = self._intent_parser.parse(query)

        # 2a. Branch: chapter-enumeration query — per-chapter keyword search
        if intent_decision.intent == QueryIntent.CHAPTER_ENUMERATE:
            chapters_to_cover = self._derive_chapter_numbers(structure_chunks)

            if chapters_to_cover:
                from pymongo import MongoClient
                from secondbrain.config import config
                cfg_ = config()
                client_ = MongoClient(cfg_.mongo_uri, directConnection=True)
                coll_ = client_[cfg_.mongo_db][cfg_.mongo_collection]

                # Pick the source with the most body chunks (most substantive document)
                sources_set = {entry[1] for entry in chapters_to_cover}
                src = max(
                    (s for s in sources_set),
                    key=lambda s: coll_.count_documents(
                        {"source_file": s, "chunk_role": "body"}
                    ),
                )

                import re
                # Phase 1: find chapter start pages from body chunk subsection headers like "1.1 "
                SEC_HEADER_RE = re.compile(r"^\s*(\d+)\.\d+\s")
                chapter_first_pg: dict[int, int] = {}

                for c in (
                    coll_.find(
                        {"source_file": src, "chunk_role": "body"},
                        {"_id": 0, "chunk_text": 1, "page_number": 1},
                    )
                    .sort("page_number", 1)
                    .limit(3500)
                ):
                    txt = c.get("chunk_text", "")[:150]
                    page = c.get("page_number", 0)

                    m = SEC_HEADER_RE.match(txt)
                    if m:
                        ch = int(m.group(1))
                        if 1 <= ch <= 30 and ch not in chapter_first_pg:
                            chapter_first_pg[ch] = page
                            if len(chapter_first_pg) >= 25:
                                break

                # Phase 2: post-loop targeted scan for chapters 1-30 not yet found
                # Runs as a separate scan so it isn't cut off by the phase 1 break
                # Uses \D (non-digit) separator to avoid matching "200 " for chapter "20"
                missing = [n for n in range(1, 31) if n not in chapter_first_pg]
                if missing:
                    for c in (
                        coll_.find(
                            {"source_file": src, "chunk_role": "body"},
                            {"_id": 0, "chunk_text": 1, "page_number": 1},
                        )
                        .sort("page_number", 1)
                        .limit(3500)
                    ):
                        txt = c.get("chunk_text", "")[:150]
                        for ch_num in list(missing):
                            pat = re.compile(rf"^\s*{ch_num}\D")
                            if pat.match(txt):
                                chapter_first_pg[ch_num] = c.get("page_number", 0)
                                missing.remove(ch_num)
                        if not missing:
                            break

                # Phase 3: interpolate page numbers for chapters still missing
                # Only interpolates chapters known to exist (from _derive_chapter_numbers)
                # Using hardcoded 1-21 would create phantom chapters for shorter docs
                for n in sorted({ct[0] for ct in chapters_to_cover}):
                    if n in chapter_first_pg:
                        continue
                    before = max([k for k in chapter_first_pg if k < n], default=None)
                    after = min([k for k in chapter_first_pg if k > n], default=None)
                    bp = chapter_first_pg[before] if before is not None else None
                    ap = chapter_first_pg[after] if after is not None else None
                    if bp is not None and ap is not None:
                        chapter_first_pg[n] = (bp + ap) // 2
                    elif bp is not None:
                        chapter_first_pg[n] = bp + 1
                    elif ap is not None:
                        chapter_first_pg[n] = max(1, ap - 1)

                # Drop stragglers (e.g. ch24 after ch18) via long-consecutive-run
                sorted_chs = sorted(chapter_first_pg)
                if sorted_chs:
                    runs: list[list[int]] = [[sorted_chs[0]]]
                    for i in range(1, len(sorted_chs)):
                        if sorted_chs[i] - sorted_chs[i - 1] == 1:
                            runs[-1].append(sorted_chs[i])
                        else:
                            runs.append([sorted_chs[i]])
                    main_run = max(runs, key=len)
                    chapter_first_pg = {
                        k: v for k, v in chapter_first_pg.items()
                        if main_run[0] <= k <= main_run[-1]
                    }
                # Build sorted page ranges
                sorted_pgs = sorted(chapter_first_pg.items(), key=lambda x: x[1])
                chapter_ranges_: dict[int, tuple[int, int]] = {}
                for idx_, (ch_, start_pg_) in enumerate(sorted_pgs):
                    end_pg_ = (
                        sorted_pgs[idx_ + 1][1] - 1
                        if idx_ + 1 < len(sorted_pgs)
                        else 700
                    )
                    chapter_ranges_[ch_] = (start_pg_, end_pg_)

                chapter_keys = sorted(chapter_ranges_.keys())
                # Fair round-robin: grab one chunk per chapter in cycles until budget exhausted
                chapter_buckets: dict[int, list] = {ch: [] for ch in chapter_keys}
                for c in (
                    coll_.find(
                        {"source_file": src, "chunk_role": "body"},
                        {"_id": 0, "chunk_text": 1, "page_number": 1, "source_file": 1, "chunk_id": 1},
                    )
                    .sort("page_number", 1)
                    .limit(6000)
                ):
                    pg = c.get("page_number", 0)
                    for ch_num in chapter_keys:
                        rng = chapter_ranges_[ch_num]
                        if rng[0] <= pg <= rng[1]:
                            if len(chapter_buckets[ch_num]) < 4:
                                c["score"] = 0.5
                                chapter_buckets[ch_num].append(c)
                            break

                # Merge buckets in round-robin order
                unique_by_hash: dict[int, dict[str, Any]] = {}
                hashes_seen: set[int] = set()
                max_bucket = max(len(b) for b in chapter_buckets.values())
                for slot in range(max_bucket):
                    for ch_num in chapter_keys:
                        bucket = chapter_buckets[ch_num]
                        if slot < len(bucket):
                            c = bucket[slot]
                            h = hash(c.get("chunk_text", "")[:512])
                            if h not in hashes_seen:
                                hashes_seen.add(h)
                                unique_by_hash[h] = c

                accumulated = list(unique_by_hash.values())
                accumulated.sort(key=lambda c: c.get("score", 0.0), reverse=True)
                final_chunks = accumulated[:top_k]

                # Build chapter roster with titles from _derive_chapter_numbers results
                ch_titles: dict[int, str] = {}
                for ct in chapters_to_cover:
                    ch_titles[ct[0]] = ct[2]
                chapter_roster_lines = []
                for ch_num in sorted(chapter_ranges_.keys()):
                    pg_start = chapter_ranges_[ch_num][0]
                    title = ch_titles.get(ch_num, "")
                    if title:
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} — {title} (approx pages {pg_start}+)"
                        )
                    else:
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} (approx pages {pg_start}+)"
                        )
                chapter_roster = "\n".join(chapter_roster_lines) + "\n"
                context_text = chapter_roster + self._format_context(final_chunks)
                prompt = self._build_prompt(query, context_text)

                generation_start = time.perf_counter()
                answer = ""
                try:
                    with trace_operation("rag_generation_iterative") as span:
                        if span:
                            span.set_attribute("rag.iterative_mode", True)
                            span.set_attribute("rag.enumeration_mode", True)
                            span.set_attribute("rag.top_k", top_k)

                        if self._config.streaming_enabled and hasattr(
                            self._llm_provider, "stream_chat"
                        ):
                            try:
                                messages = [{"role": "user", "content": prompt}]
                                accumulated_resp: list[str] = []

                                def on_chunk(content: str, _reasoning: str | None) -> None:
                                    if content:
                                        accumulated_resp.append(content)

                                self._llm_provider.stream_chat(
                                    messages=messages,
                                    on_chunk=on_chunk,
                                    temperature=self._config.llm_temperature,
                                    max_tokens=self._config.llm_max_tokens,
                                )
                                answer = "".join(accumulated_resp)
                            except Exception:
                                answer = ""

                        if not answer or not answer.strip():
                            answer = self._llm_provider.generate(
                                prompt=prompt,
                                temperature=self._config.llm_temperature,
                                max_tokens=self._config.llm_max_tokens,
                            )
                except Exception as e:
                    logger.error(
                        "Iterative query generation failed: %s: %s", type(e).__name__, e
                    )
                    answer = f"An error occurred during generation: {e}"
                finally:
                    metrics.record(
                        "generation_latency", time.perf_counter() - generation_start
                    )

                result = {"answer": answer, "query": query}
                if show_sources:
                    result["sources"] = final_chunks
                return result
            else:
                pass  # Fall through to existing structural iteration

        # 2. Collect chunks iterating across structure elements
        unique_by_hash: dict[int, dict[str, Any]] = {}
        hashes_seen: set[int] = set()

        for struct_chunk in structure_chunks:
            # Build a scoped query referencing this section
            page = struct_chunk.get("page_number", 0)
            source = struct_chunk.get("source_file", "")

            section_scope = f"{query} focusing on page {page} section content"
            section_chunks = self._searcher.search(section_scope, top_k=5)

            for c in section_chunks:
                h = hash(c.get("chunk_text", "")[:512])
                if h not in hashes_seen:
                    hashes_seen.add(h)
                    unique_by_hash[h] = c

        # 3. Fill remaining slots with generic top-k if undersubscribed
        accumulated = list(unique_by_hash.values())
        if len(accumulated) < top_k:
            generic_chunks = self._searcher.search(query, top_k=top_k)
            for c in generic_chunks:
                h = hash(c.get("chunk_text", "")[:512])
                if h not in hashes_seen:
                    hashes_seen.add(h)
                    unique_by_hash[h] = c
            accumulated = list(unique_by_hash.values())

        # 4. Sort by score descending and trim to top_k
        accumulated.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        final_chunks = self._dedupe_by_text_hash(accumulated)[:top_k]

        if not final_chunks:
            return {
                "answer": f"I couldn't find relevant documents for your query: {query}",
                "query": query,
            }

        chapter_roster = self._derive_chapter_roster(structure_chunks)
        context_text = chapter_roster + self._format_context(final_chunks)
        prompt = self._build_prompt(query, context_text)

        # 6. Generate answer (same LLM call as query() uses)
        generation_start = time.perf_counter()
        answer = ""
        try:
            with trace_operation("rag_generation_iterative") as span:
                if span:
                    span.set_attribute("rag.iterative_mode", True)
                    span.set_attribute("rag.top_k", top_k)

                if self._config.streaming_enabled and hasattr(
                    self._llm_provider, "stream_chat"
                ):
                    try:
                        messages = [{"role": "user", "content": prompt}]
                        accumulated_resp: list[str] = []

                        def on_chunk(content: str, _reasoning: str | None) -> None:
                            if content:
                                accumulated_resp.append(content)

                        self._llm_provider.stream_chat(
                            messages=messages,
                            on_chunk=on_chunk,
                            temperature=self._config.llm_temperature,
                            max_tokens=self._config.llm_max_tokens,
                        )
                        answer = "".join(accumulated_resp)
                    except Exception:
                        answer = ""

                if not answer or not answer.strip():
                    answer = self._llm_provider.generate(
                        prompt=prompt,
                        temperature=self._config.llm_temperature,
                        max_tokens=self._config.llm_max_tokens,
                    )
        except Exception as e:
            logger.error(
                "Iterative query generation failed: %s: %s", type(e).__name__, e
            )
            answer = f"An error occurred during generation: {e}"
        finally:
            metrics.record("generation_latency", time.perf_counter() - generation_start)

        # 7. Build result
        result: dict[str, Any] = {"answer": answer, "query": query}
        if show_sources:
            result["sources"] = final_chunks

        return result

    def _handle_no_results(
        self,
        query: str,
    ) -> str:
        """Handle case when no documents retrieved.

        Args:
            query: Original query.

        Returns:
            Fallback response text.

        Example:
            >>> pipeline._handle_no_results("What is Python?")
            "I couldn't find relevant documents for your query: What is Python?"
        """
        return f"I couldn't find relevant documents for your query: {query}"

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

    async def query_async(
        self,
        query: str,
        top_k: int | None = None,
        show_sources: bool = False,
    ) -> dict[str, Any]:
        """Perform single-turn async RAG query.

        Args:
            query: User query text.
            top_k: Override default number of chunks to retrieve.
            show_sources: Include retrieved chunks in response.

        Returns:
            Dict with keys: "answer", "sources" (if show_sources), "query".
        """
        # Validate query is not empty or whitespace-only
        if not query or not query.strip():
            return {
                "answer": "Query cannot be empty. Please provide a valid question.",
                "query": query,
                "validation_error": True,
            }

        try:
            effective_top_k = top_k if top_k is not None else self._top_k

            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval_async") as span:
                    if span:
                        span.set_attribute("rag.query", query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", False)
                        span.set_attribute("rag.is_async", True)
                    chunks = await self._searcher.search_async(
                        query, top_k=effective_top_k
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not chunks:
                fallback_answer = self._handle_no_results(query)
                result: dict[str, Any] = {"answer": fallback_answer, "query": query}
                if show_sources:
                    result["sources"] = []
                return result

            context_text = self._format_context(chunks)
            prompt = self._build_prompt(query, context_text)

            generation_start = time.perf_counter()
            answer = ""
            try:
                with trace_operation("rag_generation_async") as span:
                    if span:
                        span.set_attribute("rag.prompt_length", len(prompt))
                        span.set_attribute(
                            "rag.temperature", self._config.llm_temperature
                        )
                        span.set_attribute(
                            "rag.max_tokens", self._config.llm_max_tokens
                        )
                        span.set_attribute("rag.is_async", True)

                    if self._config.streaming_enabled and hasattr(
                        self._llm_provider, "stream_chat_async"
                    ):
                        try:
                            messages = [{"role": "user", "content": prompt}]
                            accumulated: list[str] = []

                            def on_chunk(content: str, _reasoning: str | None) -> None:
                                if content:
                                    accumulated.append(content)

                            await self._llm_provider.stream_chat_async(
                                messages=messages,
                                on_chunk=on_chunk,
                                temperature=self._config.llm_temperature,
                                max_tokens=self._config.llm_max_tokens,
                            )
                            answer = "".join(accumulated)
                        except Exception as streaming_err:
                            logger.warning(
                                "Async streaming failed, falling back to agenerate(): %s: %s",
                                type(streaming_err).__name__,
                                streaming_err,
                            )
                            answer = ""

                    if not answer or not answer.strip():
                        answer = await self._llm_provider.agenerate(
                            prompt=prompt,
                            temperature=self._config.llm_temperature,
                            max_tokens=self._config.llm_max_tokens,
                        )

                    if span:
                        span.set_attribute("rag.answer_length", len(answer))
            finally:
                generation_duration = time.perf_counter() - generation_start
                metrics.record("generation_latency_async", generation_duration)
                logger.debug("generation_latency_async: %.3fs", generation_duration)

            result = {"answer": answer, "query": query}
            if show_sources:
                result["sources"] = chunks

            return result

        except Exception as e:
            logger.error("Async query failed: %s: %s", type(e).__name__, e)
            return self._create_error_response(str(e), query)

    async def chat_async(
        self,
        query: str,
        session: ConversationSession,
        top_k: int | None = None,
        show_sources: bool = False,
    ) -> dict[str, Any]:
        """Perform multi-turn async conversational RAG.

        Args:
            query: Current user query.
            session: ConversationSession with history.
            top_k: Override default number of chunks.
            show_sources: Include retrieved chunks.

        Returns:
            Dict with keys: "answer", "sources" (if show_sources), "rewritten_query".
        """
        try:
            effective_top_k = top_k if top_k is not None else self._top_k

            rewritten_query = self._rewrite_query_with_history(query, session)

            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval_async") as span:
                    if span:
                        span.set_attribute("rag.query", rewritten_query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", True)
                        span.set_attribute("rag.is_async", True)
                    chunks = await self._searcher.search_async(
                        rewritten_query, top_k=effective_top_k
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not chunks:
                fallback_answer = self._handle_no_results(query)
                result: dict[str, Any] = {
                    "answer": fallback_answer,
                    "rewritten_query": rewritten_query,
                }
                if show_sources:
                    result["sources"] = []
                return result

            context_text = self._format_context(chunks)
            history = session.get_history(limit=self._context_window)
            prompt = self._build_prompt(rewritten_query, context_text, history)

            generation_start = time.perf_counter()
            answer = ""
            try:
                with trace_operation("rag_generation_async") as span:
                    if span:
                        span.set_attribute("rag.prompt_length", len(prompt))
                        span.set_attribute(
                            "rag.temperature", self._config.llm_temperature
                        )
                        span.set_attribute(
                            "rag.max_tokens", self._config.llm_max_tokens
                        )
                        span.set_attribute("rag.is_chat", True)
                        span.set_attribute("rag.is_async", True)

                    if self._config.streaming_enabled and hasattr(
                        self._llm_provider, "stream_chat_async"
                    ):
                        try:
                            messages = [{"role": "user", "content": prompt}]
                            accumulated: list[str] = []

                            def on_chunk(content: str, _reasoning: str | None) -> None:
                                if content:
                                    accumulated.append(content)

                            await self._llm_provider.stream_chat_async(
                                messages=messages,
                                on_chunk=on_chunk,
                                temperature=self._config.llm_temperature,
                                max_tokens=self._config.llm_max_tokens,
                            )
                            answer = "".join(accumulated)
                        except Exception as streaming_err:
                            logger.warning(
                                "Async streaming failed, falling back to agenerate(): %s: %s",
                                type(streaming_err).__name__,
                                streaming_err,
                            )
                            answer = ""

                    if not answer or not answer.strip():
                        answer = await self._llm_provider.agenerate(
                            prompt=prompt,
                            temperature=self._config.llm_temperature,
                            max_tokens=self._config.llm_max_tokens,
                        )

                    if span:
                        span.set_attribute("rag.answer_length", len(answer))
            finally:
                generation_duration = time.perf_counter() - generation_start
                metrics.record("generation_latency_async", generation_duration)
                logger.debug("generation_latency_async: %.3fs", generation_duration)

            session.add_message("user", query)
            session.add_message("assistant", answer)

            result = {"answer": answer, "rewritten_query": rewritten_query}
            if show_sources:
                result["sources"] = chunks

            return result

        except Exception as e:
            logger.error("Async chat failed: %s: %s", type(e).__name__, e)
            return self._create_error_response(str(e), query)
