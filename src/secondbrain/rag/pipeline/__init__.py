"""RAG pipeline for orchestrating retrieval and generation.

This module provides the RAGPipeline class that orchestrates the complete
Retrieval-Augmented Generation workflow for conversational Q&A.
"""

import logging
import time
from contextlib import suppress
from typing import Any, cast

from secondbrain.config import config
from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.document.scoped_retriever import ScopedRetriever
from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.intent_parser import QueryIntent, StructuralIntentParser
from secondbrain.rag.interfaces import LocalLLMProvider, StreamingCallback
from secondbrain.rag.security_filter import SecurityFilter
from secondbrain.search import Searcher
from secondbrain.utils.perf_monitor import metrics
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)


from secondbrain.rag.pipeline._constants import (  # noqa: E402
    filter_chapters_by_target,
)
from secondbrain.rag.pipeline._mixins import (  # noqa: E402
    _FallbackMixin,
    _FormattingMixin,
    _RoutingMixin,
    _StructureMixin,
)


class RAGPipeline(
    _FormattingMixin,
    _StructureMixin,
    _FallbackMixin,
    _RoutingMixin,
):
    """Orchestrates retrieval and generation for conversational RAG.

    Inherits cohesive helper-method mixins from ``_mixins``.
    """

    def __init__(
        self,
        searcher: Searcher,
        llm_provider: LocalLLMProvider,
        rewriter: QueryRewriter | None = None,
        top_k: int | None = None,
        context_window: int = 5,
        on_chunk: StreamingCallback | None = None,
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
        self._on_chunk = on_chunk
        # Lazily-initialized DocumentRouter for document-scoped retrieval.
        # Created on first use so that the pipeline can be constructed without
        # a running MongoDB connection (e.g. during CLI help / --version).
        self._document_router: DocumentRouter | None = None

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

            # --- Resolve document-scoped source_filter from query ---
            source_filter = self._resolve_source_filter(query)

            # --- B4: Iterative RAG for broad-coverage and chapter/section-enumeration queries ---
            intent_result = self._intent_parser.parse(query)
            if intent_result.intent is QueryIntent.LIST_SOURCES:
                return self._list_sources_result(query)
            if intent_result.intent in (
                QueryIntent.BROAD_COVERAGE,
                QueryIntent.CHAPTER_ENUMERATE,
                QueryIntent.SECTION_ENUMERATE,
            ):
                return self._iterative_query(
                    query,
                    top_k=effective_top_k,
                    show_sources=show_sources,
                    source_filter=source_filter,
                )

            # Step 1: Retrieve chunks via searcher.search()
            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval") as span:
                    if span:
                        span.set_attribute("rag.query", query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.source_filter", source_filter or "")
                    chunks = self._searcher.search(
                        query,
                        top_k=effective_top_k,
                        source_filter=source_filter,
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency", retrieval_duration)
                logger.debug("retrieval_latency: %.3fs", retrieval_duration)

            # Step 2: Handle no results
            if not self._has_relevant_chunks(chunks):
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
                                if self._on_chunk and content:
                                    self._on_chunk(content, _reasoning)

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

            # --- Resolve document-scoped source_filter from query ---
            source_filter = self._resolve_source_filter(query)

            # --- B4: Iterative RAG for broad-coverage and chapter/section-enumeration queries ---
            intent_result = self._intent_parser.parse(query)
            if intent_result.intent is QueryIntent.LIST_SOURCES:
                return self._list_sources_result(query)
            if intent_result.intent in (
                QueryIntent.BROAD_COVERAGE,
                QueryIntent.CHAPTER_ENUMERATE,
                QueryIntent.SECTION_ENUMERATE,
            ):
                return self._iterative_query(
                    query,
                    top_k=effective_top_k,
                    show_sources=show_sources,
                    source_filter=source_filter,
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
                        span.set_attribute("rag.source_filter", source_filter or "")
                    chunks = self._searcher.search(
                        rewritten_query,
                        top_k=effective_top_k,
                        source_filter=source_filter,
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
            if not self._has_relevant_chunks(chunks):
                # First attempt a grounded re-retrieval: disambiguate the query
                # from conversation history and re-query the vector DB so a
                # multi-turn follow-up can retrieve the actual source document.
                # Only if that returns nothing relevant do we fall through to the
                # knowledge fallback below.
                history = session.get_history(limit=self._context_window)
                grounded: dict[str, Any] | None = None
                if self._config.rag_llm_fallback_enabled:
                    grounded = self._grounded_context_retry(
                        rewritten_query,
                        conversation_history=history,
                        top_k=effective_top_k,
                        show_sources=show_sources,
                    )
                if grounded is not None:
                    return grounded
                # Thread conversation history so the LLM knowledge fallback can
                # leverage prior turns for this multi-turn chat follow-up.
                fallback_answer = self._handle_no_results(
                    rewritten_query,
                    conversation_history=history,
                )
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
                                    if self._on_chunk and content:
                                        self._on_chunk(content, _reasoning)

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
                            if self._on_chunk and answer:
                                self._on_chunk(answer, None)

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
                    fallback_answer = self._handle_no_results(
                        query, allow_llm_fallback=False
                    )
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

    def _iterative_query(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
        source_filter: str | None = None,
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
        structure_chunks = self._probe_document_structure(
            top_k=400,
            source_filter=source_filter,
        )
        if not structure_chunks:
            # Fall back to generic one-shot if no structure found
            return self._generic_one_shot(
                query,
                top_k,
                show_sources,
                source_filter=source_filter,
            )

        intent_decision = self._intent_parser.parse(query)

        # When enumerating a single chapter, boost top_k so the bucket
        # collection captures enough breadth across the page range
        # instead of saturating on the first few pages.
        if (
            intent_decision.intent == QueryIntent.CHAPTER_ENUMERATE
            and intent_decision.target is not None
        ):
            top_k = max(top_k, 40)

        # 2a. Branch: chapter-enumeration query — per-chapter keyword search
        # If the user asked for a specific section (e.g. "section 11.33"),
        # extract the chapter number ("11") and enumerate that chapter.
        enum_target = intent_decision.target
        raw_section_target: str | None = None
        if enum_target is None and intent_decision.intent in (
            QueryIntent.BROAD_COVERAGE,
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
        ):
            # BROAD_COVERAGE only extracts "chapter N" targets, not
            # "section 11.33".  Check the raw query for a section number.
            import re

            sec_m = re.search(r"(\d+(?:\.\d+)+)", query)
            if sec_m:
                enum_target = sec_m.group(1)
                raw_section_target = enum_target  # preserve before truncation
        if enum_target and "." in enum_target:
            enum_target = enum_target.split(".")[0]
        # Also catch broad-coverage queries with section numbers like
        # "summarize section 11.33" — route through chapter enumeration
        # for precise page-range retrieval instead of the generic search.
        has_section_target = enum_target is not None and intent_decision.intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
            QueryIntent.SECTION_ENUMERATE,
        )
        if has_section_target or intent_decision.intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
        ):
            chapters_to_cover, good_title_nums, appendix_entries = (
                self._derive_chapter_numbers(structure_chunks)
            )

            # Scope to specific target chapter when one is specified (e.g. "chapter 11")
            chapters_to_cover, good_title_nums = filter_chapters_by_target(
                chapters_to_cover,
                good_title_nums,
                enum_target,
            )
            if enum_target is not None:
                appendix_entries = []

            if chapters_to_cover:
                from pymongo import MongoClient
                from pymongo import errors as mongo_errors

                from secondbrain.config import config

                cfg_ = config()
                try:
                    client_ = MongoClient(
                        cfg_.mongo_uri,
                        directConnection=True,
                        serverSelectionTimeoutMS=2000,
                    )
                    client_.admin.command("ping")
                except (
                    mongo_errors.ConnectionFailure,
                    mongo_errors.ServerSelectionTimeoutError,
                    Exception,
                ):
                    return self._generic_one_shot(
                        query, top_k, show_sources, source_filter=source_filter
                    )
                coll_ = client_[cfg_.mongo_db][cfg_.mongo_collection]

                # Use explicit source_filter if provided (from DocumentRouter),
                # otherwise pick the source with the most body chunks.
                if source_filter:
                    src = source_filter
                else:
                    sources_set = {entry[1] for entry in chapters_to_cover}
                    src = max(
                        (s for s in sources_set),
                        key=lambda s: coll_.count_documents(
                            {"source_file": s, "chunk_role": "body"}
                        ),
                    )

                import re

                # Pre-populate chapter_first_pg from reliable CHAPTER_N_RE titles
                # (e.g. "Chapter 5 Importing...") so SEC_HEADER_RE doesn't overwrite
                # them with section-number false matches (e.g. "5.1 Running a VM"
                # which is actually a section of a different chapter).
                # BARE_CHAPTER_RE titles (e.g. "5 Working with VMs") are NOT included
                # here — they're less reliable and may conflict with other chapters.
                chapter_first_pg: dict[int, int] = {}
                # Title-anchored detection: the numbered chapter-title heading
                # (e.g. "13 Troubleshooting", "12 Customizing Oracle VirtualBox") is
                # the single most reliable chapter-start signal.  Section-number
                # scanning below (SEC_HEADER_RE / BARE_CHAPTER_RE) mistakes TOC
                # dot-leader entries and in-body cross-references (e.g. "see 15.16")
                # for chapter starts, pinning chapters to the wrong page — especially
                # for books whose chapters are numbered without the word "Chapter"
                # (so they are invisible to CHAPTER_N_RE).  Find each chapter's
                # title heading on a body page (skipping TOC dot-leader lines) and
                # pre-populate, so the noisy scans cannot override it.
                dot_leader_ = re.compile(r"\.{2,}")
                body_all_ = list(
                    coll_.find(
                        {"source_file": src, "chunk_role": "body"},
                        {"_id": 0, "chunk_text": 1, "page_number": 1},
                    )
                    .sort("page_number", 1)
                    .limit(3500)
                )
                for tn_ in chapters_to_cover:
                    tn, ts_, tt_ = tn_
                    if ts_ != src or not tt_ or len(tt_) < 4:
                        continue
                    anchor_ = re.compile(
                        rf"(?:^|\n)\s*{tn}\.?\s+{re.escape(tt_)}",
                        re.IGNORECASE,
                    )
                    for bc_ in body_all_:
                        btext_ = bc_.get("chunk_text", "")
                        bm_ = anchor_.search(btext_)
                        if not bm_:
                            continue
                        ble_ = btext_.find("\n", bm_.end())
                        brest_ = btext_[bm_.end() : ble_ if ble_ != -1 else len(btext_)]
                        if dot_leader_.search(brest_) or re.match(
                            r"^\s*\d{1,3}\s*$", brest_
                        ):
                            continue
                        chapter_first_pg[tn] = bc_.get("page_number", 0)
                        break
                ch_n = re.compile(
                    r"(?:Chapter\s+(\d+)\s*[:\-]?\s*|(?:Module|Lesson)\s+(\d+)"
                    r"\s*[:\-]\s*)(.{2,60})",
                    re.IGNORECASE,
                )
                # Slide decks are extracted without heading/toc roles — every
                # slide is real content, so an early "Module 1"/"Module 2"
                # heading (page <10) is genuine, not a TOC entry.  Keep the
                # TOC-page guard for manuals, which do carry heading/toc roles.
                is_deck = not any(
                    c.get("chunk_role") in ("heading", "toc_entry")
                    for c in structure_chunks
                )
                for sc in structure_chunks:
                    txt = sc.get("chunk_text", "")
                    pg = sc.get("page_number", 0)
                    role = sc.get("chunk_role", "")
                    # Reject TOC page numbers (typically < 10) — a chapter_n_re
                    # match on page 3 is almost certainly a TOC entry, not the
                    # actual chapter start page. Without this guard, Phase 1's
                    # sec_header_re body-chunk scan would find the wrong start.
                    if pg < 10 and not is_deck:
                        continue
                    # TOC / front-structure chunks list every chapter on one
                    # page (dot-leader "Chapter N" captions) and are never the
                    # real opening of a chapter.  Some books carry no heading /
                    # toc_entry roles (front matter is tagged "caption" or
                    # "navigation"), so is_deck becomes True and the pg<10 guard
                    # above is skipped — rejecting these roles keeps that
                    # protection.
                    if role in ("toc_entry", "caption", "navigation"):
                        continue
                    for nm in ch_n.finditer(txt):
                        ch = int(nm.group(1) or nm.group(2))
                        if ch in good_title_nums and ch not in chapter_first_pg:
                            # "Chapter N," (comma right after the number) is a
                            # preface / cross-reference summary sentence
                            # (e.g. "Chapter 4, The pandas I/O System, shows …"),
                            # NOT a chapter-opening heading.  Matching those pins
                            # every chapter to a front-matter page and starves the
                            # real chapter of its page range.  Real headings use a
                            # colon, period, or plain space after the number.
                            if re.match(r"Chapter\s+\d+,", nm.group(0), re.IGNORECASE):
                                continue
                            chapter_first_pg[ch] = pg

                # Phase 1: find chapter start pages from body chunk subsection headers like "1.1 " or "11.1.1 "
                # Use \b (word boundary) + search() instead of ^ + match() because docling
                # often embeds section numbers in the middle of paragraph text rather than
                # at the start of a chunk (e.g. "... features. 11.1 CPU Hot-Plugging ...").
                # NOTE: chapters already in chapter_first_pg (from ch_n above) are
                # skipped — their pages are more reliable.
                sec_header_re = re.compile(r"\b(\d+)\.\d+(?:\.\d+)?\s")
                # Parallel scan for letter-prefixed section numbers (e.g. "A.1", "B.2.3")
                # to detect appendix labels from actual document body content.  This is the
                # most universal approach — works for any document regardless of TOC format.
                appendix_sec_re = re.compile(r"\b([A-Za-z])\.\d+\s")
                appendix_labels_found: set[str] = set()
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

                    # Detect appendix labels from body section numbering
                    am = appendix_sec_re.search(txt)
                    if am:
                        appendix_labels_found.add(am.group(1).upper())

                    m = sec_header_re.search(txt)
                    if m:
                        ch = int(m.group(1))
                        if 1 <= ch <= 30 and ch not in chapter_first_pg:
                            # Skip cross-references like "9.2 Virtual
                            # Networking Hardware on page 144" which
                            # appear on pages belonging to OTHER chapters.
                            after = txt[m.end() : m.end() + 60]
                            has_on_page = bool(re.search(r"\bon\s+page\s+\d+", after))
                            if has_on_page:
                                continue
                            chapter_first_pg[ch] = page
                            if len(chapter_first_pg) >= 25:
                                break

                # Phase 2: post-loop targeted scan for chapters known to exist but not yet found
                # Only scans up to max(chapters_to_cover) + 1 to avoid phantom chapters
                missing = [
                    n
                    for n in range(
                        1, max({ct[0] for ct in chapters_to_cover}, default=0) + 1
                    )
                    if n not in chapter_first_pg
                ]
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
                            pat = re.compile(rf"\b{ch_num}\D")
                            if pat.search(txt):
                                chapter_first_pg[ch_num] = c.get("page_number", 0)
                                missing.remove(ch_num)
                        if not missing:
                            break

                # Merge appendix labels detected from body section numbering
                # into appendix_entries (from _derive_chapter_numbers).
                seen_appendix_labels: set[str] = {al[0] for al in appendix_entries}
                for label in sorted(appendix_labels_found):
                    if label not in seen_appendix_labels:
                        seen_appendix_labels.add(label)
                        appendix_entries.append((label, src, f"Appendix {label}"))

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
                        k: v
                        for k, v in chapter_first_pg.items()
                        if main_run[0] <= k <= main_run[-1]
                    }
                # Drop chapters with duplicate first-word (≥ 6 chars).
                # "VBoxManage CLI Reference" and "VBoxManage Command Reference"
                # both start with "VBoxManage" → ch19 excluded from unique_nums.
                seen_first: set[str] = set()
                unique_nums: set[int] = set()
                for ct in chapters_to_cover:
                    if ct[1] != src or len(ct[2]) < 3:
                        continue
                    fw = ct[2].lower().split()[0]
                    if len(fw) >= 6 and fw in seen_first:
                        continue
                    seen_first.add(fw)
                    unique_nums.add(ct[0])
                if unique_nums:
                    max_unique = max(unique_nums)
                    # NOTE: sec_buffer = max_unique + 3 assumes sequential chapter
                    # numbering (no gap >3 between any two mapped chapters).
                    # If chapter numbers jump e.g. ch1→ch11→ch25 and ch11 is the
                    # only target, Pass 1 drops ch25 (>14), leaving ch11 as the
                    # last entry in sorted_pgs → end page falls back to 700,
                    # re-introducing cross-chapter leakage.  A production doc
                    # with such sparse numbering would need a smarter ceiling.
                    sec_buffer = max_unique + 3  # Match SEC_RE's extension range
                    # Pass 1: auto-keep known + within SEC_RE range, drop beyond
                    for k in list(chapter_first_pg):
                        if k in unique_nums:
                            continue
                        if k > sec_buffer:
                            del chapter_first_pg[k]
                    # Pass 2: drop SEC_RE-only chapters with first-word collisions
                    # (catches ch19 "VBoxManage" dup with ch15 while keeping ch17-18)
                    for k in list(chapter_first_pg):
                        if k in unique_nums or k <= max_unique:
                            continue
                        kt = next(
                            (
                                ct[2]
                                for ct in chapters_to_cover
                                if ct[0] == k and ct[1] == src
                            ),
                            "",
                        )
                        if kt:
                            kw = kt.lower().split()[0]
                            if len(kw) >= 6 and kw in seen_first:
                                del chapter_first_pg[k]
                # Pass 3: keep boundary chapters for page-range interpolation
                # even when they are not target chapters, then restrict the
                # output page ranges to only target chapters below.
                target_ch_nums = {ct[0] for ct in chapters_to_cover}

                # Build sorted page ranges from ALL boundary chapters
                sorted_pgs = sorted(chapter_first_pg.items(), key=lambda x: x[1])
                chapter_ranges_: dict[int, tuple[int, int]] = {}
                # Build boundary page mapping for end-page computation.
                # Keep ALL chapter boundaries so that end-page calculation for a
                # target chapter can see the next non-target chapter boundary.
                # We guard against sec_header_re false positives (which produce
                # start>end ranges) by skipping any next-chapter boundary whose
                # page number is <= the current chapter's start page.
                boundary_pgs = dict(chapter_first_pg)
                max_ch_ = max(boundary_pgs) if boundary_pgs else 0
                for ch_, start_pg_ in sorted_pgs:
                    # Only build ranges for target chapters
                    if ch_ not in target_ch_nums:
                        continue
                    # Find the next chapter IN SEQUENCE (ch+1, ch+2, ...) in the
                    # boundary map — NOT the next entry in page-sorted order.
                    # Otherwise interleaved page numbers produce wrong end pages
                    # (e.g. ch5 at p51 with ch1 at p56 in page order → end=55).
                    # Skip any boundary whose page is <= start_pg_ to avoid
                    # false positives producing start>end ranges.
                    end_pg_ = 700
                    for nxt in range(ch_ + 1, max_ch_ + 2):
                        if nxt in boundary_pgs and boundary_pgs[nxt] > start_pg_:
                            end_pg_ = boundary_pgs[nxt] - 1
                            break
                    chapter_ranges_[ch_] = (start_pg_, end_pg_)

                chapter_keys = sorted(chapter_ranges_.keys())
                # Per-chapter bucket limit: when targeting a single chapter, scale
                # up so content spans more of the page range instead of saturating
                # at the first few chunks (all from the same starting page).
                # For multi-chapter, keep the original 4-chunk cap to prevent
                # any single chapter from dominating the round-robin merge.
                single_section_mode = len(chapter_keys) <= 2
                per_chapter_limit = 150 if single_section_mode else 4
                # Per-chapter page cap.  A small cap (2) kept only ~1/3 of the
                # chunks on a dense page (troubleshooting chapters have many
                # short sections per page), silently dropping whole sections from
                # a single-chapter summary.  Raised for single-chapter mode so
                # every section on a page is captured, bounded overall by
                # per_chapter_limit; multi-chapter keeps 2 for fair round-robin.
                page_cap = 12 if single_section_mode else 2
                page_count_per_ch: dict[int, dict[int, int]] = {
                    ch: {} for ch in chapter_keys
                }
                chapter_buckets: dict[int, list[dict[str, Any]]] = {
                    ch: [] for ch in chapter_keys
                }
                for c in (
                    coll_.find(
                        {"source_file": src, "chunk_role": "body"},
                        {
                            "_id": 0,
                            "chunk_text": 1,
                            "page_number": 1,
                            "source_file": 1,
                            "chunk_id": 1,
                        },
                    )
                    .sort("page_number", 1)
                    .limit(6000)
                ):
                    pg = c.get("page_number", 0)
                    for ch_num in chapter_keys:
                        rng = chapter_ranges_[ch_num]
                        if rng[0] <= pg <= rng[1]:
                            if len(chapter_buckets[ch_num]) < per_chapter_limit:
                                per_page = page_count_per_ch[ch_num]
                                if per_page.get(pg, 0) < page_cap:
                                    per_page[pg] = per_page.get(pg, 0) + 1
                                    c["score"] = 0.5
                                    chapter_buckets[ch_num].append(c)
                                else:
                                    # Page at cap — promote header chunks over
                                    # footers/captions that were collected first.
                                    # Use a broader match: docling often embeds
                                    # section headers (e.g. "11.2 CPU Hot-Plugging")
                                    # in the middle of paragraph text rather than
                                    # at the start of a segment.
                                    txt = c.get("chunk_text", "")
                                    sec_pat = re.compile(
                                        rf"\b{ch_num}\.\d+(?:\.\d+)?\s"
                                    )
                                    if sec_pat.search(txt):
                                        replaced = False
                                        for i, existing in enumerate(
                                            chapter_buckets[ch_num]
                                        ):
                                            if existing.get(
                                                "page_number"
                                            ) == pg and not sec_pat.search(
                                                existing.get("chunk_text", "")
                                            ):
                                                c["score"] = 0.5
                                                chapter_buckets[ch_num][i] = c
                                                replaced = True
                                                break
                                        # All existing page entries are also section
                                        # headers — grant extra slots to avoid losing
                                        # genuine section content. Allow up to 4 per
                                        # page for pages with dense section headers
                                        # (e.g. VirtualBox ch11 p186 has 4: 11.6.3,
                                        # 11.6.4, 11.6.4.1, 11.6.5).
                                        if not replaced:
                                            if per_page.get(pg, 0) < page_cap + 2:
                                                per_page[pg] = per_page.get(pg, 0) + 1
                                                c["score"] = 0.5
                                                chapter_buckets[ch_num].append(c)
                                            else:
                                                logger.debug(
                                                    "Page %s at cap (%s slots), section header "
                                                    "'%s...' dropped (all %s existing entries "
                                                    "also have section numbers)",
                                                    pg,
                                                    per_page.get(pg, 0),
                                                    txt[:60],
                                                    len(chapter_buckets[ch_num]),
                                                )
                            break

                # Post-processing: inject missing section headers.
                # Docling sometimes drops section numbers from body chunks
                # (e.g. "11.1 Automated Guest Logins" loses its "11.1 " prefix).
                # For each chapter, check if the expected first section (ch.1)
                # is missing from the bucket; if so, prepend it to the first
                # chunk that lacks a section header.
                # NOTE: Use \b{ch_num}\.1\b (not \b{ch_num}\.\d+) to avoid
                # matching e.g. 11.10 when 11.1 is actually missing.
                for ch_num in chapter_keys:
                    sec_pat_inject = re.compile(rf"\b{ch_num}\.1\b")
                    has_first = any(
                        sec_pat_inject.search(c.get("chunk_text", ""))
                        for c in chapter_buckets[ch_num]
                    )
                    if not has_first:
                        for c in chapter_buckets[ch_num]:
                            ct = c.get("chunk_text", "")
                            if not sec_pat_inject.search(ct) and ct.strip():
                                c["chunk_text"] = f"{ch_num}.1 " + ct
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
                # Use the larger of top_k and per_chapter_limit for the final
                # trim so single-chapter targets don't lose their spread.
                final_chunks = accumulated[: max(top_k, per_chapter_limit)]

                # Reorder chunks interleaving pages (round-robin by page) so the
                # LLM sees content from diverse pages early rather than sequential
                # page order. This prevents recency bias where the first few pages'
                # sections (e.g. ch5 section 5.1 across pages 51-59) dominate the
                # LLM's output.
                if len(chapter_keys) <= 2:
                    pg_groups: dict[int, list[dict[str, Any]]] = {}
                    for fc in final_chunks:
                        p = fc.get("page_number", fc.get("page", 0))
                        pg_groups.setdefault(p, []).append(fc)
                    interleaved: list[dict[str, Any]] = []
                    max_per_pg = max((len(g) for g in pg_groups.values()), default=0)
                    for slot in range(max_per_pg):
                        for pg in sorted(pg_groups):
                            if slot < len(pg_groups[pg]):
                                interleaved.append(pg_groups[pg][slot])
                    final_chunks = interleaved

                if appendix_entries:
                    # Use only target chapters for the appendix start page.
                    # Non-target chapters from sec_header_re false positives
                    # (e.g. a phantom "22.3" at the very end of the document)
                    # would push the start page past all appendix content.
                    appendix_start_pg = max(
                        (
                            chapter_first_pg.get(k, 0)
                            for k in target_ch_nums
                            if k in chapter_first_pg
                        ),
                        default=0,
                    )
                    _max_appendix = 200
                    appendix_body_chunks = list(
                        coll_.find(
                            {
                                "source_file": src,
                                "chunk_role": "body",
                                "page_number": {"$gte": appendix_start_pg},
                            },
                            {
                                "_id": 0,
                                "chunk_text": 1,
                                "page_number": 1,
                                "source_file": 1,
                                "chunk_id": 1,
                            },
                        )
                        .sort("page_number", 1)
                        .limit(_max_appendix)
                    )
                    final_chunks.extend(appendix_body_chunks)
                    # Re-deduplicate to remove any overlap between appendix
                    # chunks and already-selected body chunks.
                    _seen_ids: set[str] = set()
                    _deduped: list[dict[str, Any]] = []
                    for c in final_chunks:
                        cid = c.get("chunk_id")
                        if cid is None or cid not in _seen_ids:
                            if cid is not None:
                                _seen_ids.add(cid)
                            _deduped.append(c)
                    final_chunks = _deduped

                # Build chapter roster
                ch_titles: dict[int, str] = {}
                for ct in chapters_to_cover:
                    if ct[0] in good_title_nums and ct[0] not in ch_titles:
                        ch_titles[ct[0]] = ct[2]
                chapter_roster_lines = []
                for ch_num in sorted(chapter_ranges_.keys()):
                    pg_start = chapter_ranges_[ch_num][0]
                    title = ch_titles.get(ch_num, "")
                    if title:
                        dot = title.find(". ")
                        if 10 < dot < 150:
                            title = title[:dot]
                        dup = re.search(r"\s+\d{1,2}\s+", title[5:])
                        if dup:
                            title = title[: 5 + dup.start()].strip()
                        if len(title) > 100:
                            title = title[:100].rsplit(" ", 1)[0]
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} — {title} (approx pages {pg_start}+)"
                        )
                    else:
                        chapter_roster_lines.append(
                            f"Chapter {ch_num} — No official title (approx pages {pg_start}+)"
                        )
                chapter_roster = "\n".join(chapter_roster_lines)

                if appendix_entries:
                    chapter_roster += "\n\n" + "\n".join(
                        f"Appendix {label} — {title}"
                        for label, _src, title in appendix_entries
                    )
                chapter_roster += "\n"

                # Single-chapter enumeration needs more context window to fit
                # sampled chunks from across the full page range.
                # Use *3 to balance coverage with LLM latency: *6 (96000 chars)
                # caused request timeouts (24000 input + 32768 output tokens
                # ≈ 56K total, exceeding the LLM provider's time budget).
                # *3 = 48000 chars ≈ 12000 input tokens; at 600 chars/page
                # covers ~80 pages — enough for most chapters.
                enum_max_chars = (
                    self._config.rag_max_context_chars * 3
                )  # ~48000 chars, balanced for 120s LLM timeout
                body_content = self._format_context(
                    final_chunks, max_chars=enum_max_chars
                )

                ql = query.lower()
                # "by section X.Y" means focus on that section, not enumerate all
                wants_sections = (
                    any(
                        p in ql
                        for p in (
                            "by sections",
                            "by section",
                            "list sections",
                            "list all sections",
                            "list section",
                            "sections of",
                            "show sections",
                            "enumerate sections",
                            "section listing",
                        )
                    )
                    and not bool(
                        re.search(r"by section \d+", ql)
                    )  # "by section 5.1" → focus
                )

                # Determine whether this is a multi-chapter query (e.g. "summarize by chapter"
                # with no specific chapter target) vs a single-chapter query.
                is_multi_chapter = not intent_decision.target and not has_section_target

                if has_section_target and raw_section_target:
                    # User asked about a specific section (e.g. "summarize section 11.16").
                    section_prompt = (
                        f"The user asked for a summary of section {raw_section_target}. "
                        f"Below is the content of chapter {enum_target}, which contains "
                        f"section {raw_section_target}. Provide a detailed, focused summary "
                        f"of section {raw_section_target} specifically. Include its key "
                        f"topics, instructions, and any important details.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif has_section_target:
                    # User asked about a specific chapter (e.g. "tell me about chapter 11").
                    # Provide a thorough section-level breakdown instead of a concise summary.
                    section_prompt = (
                        "__DETAILED_CHAPTER_SUMMARY_INSTRUCTIONS__\n"
                        + f"The user asked for details about chapter {enum_target}. "
                        + "Below is the content of that chapter. Provide a thorough, detailed "
                        + "summary of the chapter's content, organized by its numbered sections. "
                        + "For each section, include its number, title, and a description of its "
                        + "key topics and important details. Do NOT omit any section.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif wants_sections:
                    # Section enumeration — list every section concisely.
                    # Use adjective clauses (", which covers …") to keep each line
                    # short while still adding value, staying well within the token
                    # budget so the LLM doesn't truncate mid-way through the chapter.
                    section_prompt = (
                        "__ENUMERATION INSTRUCTIONS__\n"
                        + "The user asked for a section listing. "
                        + "List every numbered section below on its own line. "
                        + "For each section, include its number (e.g. 11.1) followed by "
                        + "a brief one-line description. Do NOT omit any section.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                elif is_multi_chapter:
                    # Multi-chapter ("summarize by chapter"): ask the LLM to give
                    # a concise overview of each chapter found in the body content.
                    section_prompt = (
                        "__CHAPTER_SUMMARY_INSTRUCTIONS__\n"
                        + "The user asked for a chapter-by-chapter overview. "
                        + "Below is the document's content organized by chapter. "
                        + "For each chapter listed in the roster above, provide "
                        + "a brief one-line summary of its key topics. "
                        + "Keep each chapter summary concise.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                else:
                    # Single-chapter summary (no section request).
                    section_prompt = (
                        "Keep your answer concise. Do NOT list numbered sections or provide "
                        "a section-by-section breakdown. Instead, give a brief paragraph "
                        "summarizing the overall content of the chapter.\n"
                        + "=== BODY CONTENT ===\n"
                    )
                context_text = chapter_roster + section_prompt + body_content

                llm_fallback_roster = "\n".join(chapter_roster_lines)
                if appendix_entries:
                    llm_fallback_roster += "\n\n" + "\n".join(
                        f"Appendix {label} — {title}"
                        for label, _src, title in appendix_entries
                    )
                llm_fallback_roster += "\n"

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

                                def on_chunk(
                                    content: str, _reasoning: str | None
                                ) -> None:
                                    if content:
                                        accumulated_resp.append(content)
                                    if self._on_chunk and content:
                                        self._on_chunk(content, _reasoning)

                                enum_max_tokens = self._config.llm_max_tokens
                                self._llm_provider.stream_chat(
                                    messages=messages,
                                    on_chunk=on_chunk,
                                    temperature=self._config.llm_temperature,
                                    max_tokens=enum_max_tokens,
                                )
                                answer = "".join(accumulated_resp)
                            except Exception:
                                answer = ""

                        if not answer or not answer.strip():
                            enum_max_tokens = self._config.llm_max_tokens
                            answer = self._llm_provider.generate(
                                prompt=prompt,
                                temperature=self._config.llm_temperature,
                                max_tokens=enum_max_tokens,
                            )
                            if self._on_chunk and answer:
                                self._on_chunk(answer, None)
                except Exception as e:
                    logger.error(
                        "Iterative query generation failed: %s: %s", type(e).__name__, e
                    )
                    answer = f"An error occurred during generation: {e}"
                finally:
                    metrics.record(
                        "generation_latency", time.perf_counter() - generation_start
                    )

                # If the LLM returned empty (transient failure, cold start, etc.),
                # fall back to the chapter roster so the user gets something useful.
                if not answer or not answer.strip():
                    answer = llm_fallback_roster

                result: dict[str, Any] = {"answer": answer, "query": query}
                if show_sources:
                    result["sources"] = final_chunks
                return result
            else:
                # No chapters were detected/covered. If the user explicitly
                # requested a specific chapter (e.g. "chapter 5") that does
                # not exist, report it. Otherwise (e.g. "summarize X" with no
                # chapter number), fall through to the generic top-k search
                # below instead of emitting a misleading "couldn't find
                # chapter" error.
                if intent_decision.target is not None:
                    target_label = f"chapter {intent_decision.target}"
                    return {
                        "answer": f"I couldn't find {target_label} in the document.",
                        "query": query,
                    }
                # else: fall through to generic search (Branch B) below

        # 2. Generic top-k search: one embedding call, no per-page
        # iteration (which would make 8000+ embedding requests).
        accumulated = self._searcher.search(
            query,
            top_k=top_k,
            source_filter=source_filter,
        )

        # 4. Sort by score descending and trim to top_k
        accumulated.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        final_chunks = self._dedupe_by_text_hash(accumulated)[:top_k]

        if not self._has_relevant_chunks(final_chunks):
            return {
                "answer": self._handle_no_results(query),
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
                        accumulated_resp = []

                        def on_chunk(content: str, _reasoning: str | None) -> None:
                            if content:
                                accumulated_resp.append(content)
                            if self._on_chunk and content:
                                self._on_chunk(content, _reasoning)

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
                    if self._on_chunk and answer:
                        self._on_chunk(answer, None)
        except Exception as e:
            logger.error(
                "Iterative query generation failed: %s: %s", type(e).__name__, e
            )
            answer = f"An error occurred during generation: {e}"
        finally:
            metrics.record("generation_latency", time.perf_counter() - generation_start)

        # 7. Build result
        result = cast(dict[str, Any], {"answer": answer, "query": query})
        if show_sources:
            result["sources"] = final_chunks

        return result

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

            # --- Resolve document-scoped source_filter from query ---
            source_filter = self._resolve_source_filter(query)

            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval_async") as span:
                    if span:
                        span.set_attribute("rag.query", query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", False)
                        span.set_attribute("rag.is_async", True)
                        span.set_attribute("rag.source_filter", source_filter or "")
                    chunks = await self._searcher.search_async(
                        query, top_k=effective_top_k, source_filter=source_filter
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not self._has_relevant_chunks(chunks):
                fallback_answer = await self._handle_no_results_async(query)
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
                                if self._on_chunk and content:
                                    self._on_chunk(content, _reasoning)

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
                        if self._on_chunk and answer:
                            self._on_chunk(answer, None)

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

            # --- Resolve document-scoped source_filter from query ---
            source_filter = self._resolve_source_filter(query)

            rewritten_query = self._rewrite_query_with_history(query, session)

            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval_async") as span:
                    if span:
                        span.set_attribute("rag.query", rewritten_query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", True)
                        span.set_attribute("rag.is_async", True)
                        span.set_attribute("rag.source_filter", source_filter or "")
                    chunks = await self._searcher.search_async(
                        rewritten_query,
                        top_k=effective_top_k,
                        source_filter=source_filter,
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not self._has_relevant_chunks(chunks):
                # First attempt a grounded re-retrieval: disambiguate the query
                # from conversation history and re-query the vector DB so a
                # multi-turn follow-up can retrieve the actual source document.
                # Only if that returns nothing relevant do we fall through to the
                # knowledge fallback below.
                history = session.get_history(limit=self._context_window)
                grounded: dict[str, Any] | None = None
                if self._config.rag_llm_fallback_enabled:
                    grounded = await self._grounded_context_retry_async(
                        rewritten_query,
                        conversation_history=history,
                        top_k=effective_top_k,
                        show_sources=show_sources,
                    )
                if grounded is not None:
                    return grounded
                # Thread conversation history so the LLM knowledge fallback can
                # leverage prior turns for this multi-turn chat follow-up.
                fallback_answer = await self._handle_no_results_async(
                    rewritten_query,
                    conversation_history=history,
                )
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
                                if self._on_chunk and content:
                                    self._on_chunk(content, _reasoning)

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
                        if self._on_chunk and answer:
                            self._on_chunk(answer, None)

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


__all__ = ["RAGPipeline", "filter_chapters_by_target"]
