"""Public entry-point orchestration for the RAG pipeline.

The ``query``/``chat`` flows (sync and async) that tie retrieval,
relevance filtering, and generation together. Split out of the former
2450-line ``__init__`` so the pipeline core (``_pipeline.py``) and the
flow orchestration stay independently readable.
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any

from secondbrain.conversation import ConversationSession
from secondbrain.rag.intent_parser import QueryIntent
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.utils.perf_monitor import metrics
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)


class _OrchestrationMixin(_RAGPipelineState):
    """Orchestrates retrieval and generation for conversational RAG.

    Inherits cohesive helper-method mixins; public entry points live on
    ``_OrchestrationMixin`` (``_orchestration.py``).
    """

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

            # --- Page-number lookup: "what is on page 500" ---
            page_result = self._answer_page_query(query)
            if page_result is not None:
                return page_result

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
                    # Scoped retrieval embeds the name-stripped query (path
                    # tokens pollute the embedding); prompts/results/logs keep
                    # the original query.
                    search_query = (
                        self._scoped_search_query(query) if source_filter else query
                    )
                    chunks = self._searcher.search(
                        search_query,
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
            if not self._has_relevant_chunks(
                chunks, threshold=self._relevance_gate_threshold(source_filter)
            ):
                fallback_answer = self._handle_no_results(query)
                result: dict[str, Any] = {"answer": fallback_answer, "query": query}
                if show_sources:
                    result["sources"] = []
                return result

            # Definition queries recall chapter-opener body chunks (a manual's
            # own definitions) so "what is X" never answers from the LLM's
            # general knowledge when the document opens with the definition.
            chunks = self._union_opener_chunks(
                query, chunks, source_filter, top_k=effective_top_k
            )
            chunks = self._apply_heading_diversity(chunks)

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
                                if self._on_chunk and (content or _reasoning):
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

            # --- Page-number lookup: "what is on page 500" ---
            page_result = self._answer_page_query(query)
            if page_result is not None:
                return page_result

            # --- B4: Iterative RAG for broad-coverage and chapter/section-enumeration queries ---
            intent_result = self._intent_parser.parse(query)
            if intent_result.intent is QueryIntent.LIST_SOURCES:
                listing = self._list_sources_result(query)
                self._save_turn(session, query, listing.get("answer", ""))
                return listing
            if intent_result.intent in (
                QueryIntent.BROAD_COVERAGE,
                QueryIntent.CHAPTER_ENUMERATE,
                QueryIntent.SECTION_ENUMERATE,
            ):
                iterative = self._iterative_query(
                    query,
                    top_k=effective_top_k,
                    show_sources=show_sources,
                    source_filter=source_filter,
                )
                self._save_turn(session, query, iterative.get("answer", ""))
                return iterative

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
                    # Scoped retrieval embeds the name-stripped query (path
                    # tokens pollute the embedding); prompts/results/logs keep
                    # the rewritten query as-is.
                    scoped_rewritten = (
                        self._scoped_search_query(rewritten_query)
                        if source_filter
                        else rewritten_query
                    )
                    chunks = self._searcher.search(
                        scoped_rewritten,
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
            if not self._has_relevant_chunks(
                chunks, threshold=self._relevance_gate_threshold(source_filter)
            ):
                # First attempt a grounded re-retrieval: disambiguate the query
                # from conversation history and re-query the vector DB so a
                # multi-turn follow-up can retrieve the actual source document.
                # Only if that returns nothing relevant do we fall through to the
                # knowledge fallback below.
                history = session.get_history(limit=self._context_window)
                grounded: dict[str, Any] | None = None
                if self._config.rag_llm_fallback_enabled:
                    grounded = self._grounded_context_retry(
                        query,
                        conversation_history=history,
                        top_k=effective_top_k,
                        show_sources=show_sources,
                    )
                if grounded is not None:
                    self._save_turn(session, query, grounded.get("answer", ""))
                    return grounded
                # Thread conversation history so the LLM knowledge fallback can
                # leverage prior turns for this multi-turn chat follow-up.
                fallback_answer = self._handle_no_results(
                    query,
                    conversation_history=history,
                )
                self._save_turn(session, query, fallback_answer)
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
            prompt = self._build_prompt(query, context_text, history)

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
                                    if self._on_chunk and (content or _reasoning):
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
                    self._save_turn(session, query, fallback_answer)
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
            self._save_turn(session, query, answer)

            # Step 8: Build result dict
            result = {"answer": answer, "rewritten_query": rewritten_query}
            if show_sources:
                result["sources"] = chunks

            return result

        except Exception as e:
            logger.error("Chat failed: %s: %s", type(e).__name__, e)
            return self._create_error_response(str(e), query)

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

            # --- Page-number lookup: "what is on page 500" ---
            page_result = await self._answer_page_query_async(query)
            if page_result is not None:
                return page_result

            retrieval_start = time.perf_counter()
            try:
                with trace_operation("rag_retrieval_async") as span:
                    if span:
                        span.set_attribute("rag.query", query)
                        span.set_attribute("rag.top_k", effective_top_k)
                        span.set_attribute("rag.is_chat", False)
                        span.set_attribute("rag.is_async", True)
                        span.set_attribute("rag.source_filter", source_filter or "")
                    # Scoped retrieval embeds the name-stripped query (path
                    # tokens pollute the embedding); prompts/results/logs keep
                    # the original query.
                    search_query = (
                        self._scoped_search_query(query) if source_filter else query
                    )
                    chunks = await self._searcher.search_async(
                        search_query,
                        top_k=effective_top_k,
                        source_filter=source_filter,
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not self._has_relevant_chunks(
                chunks, threshold=self._relevance_gate_threshold(source_filter)
            ):
                fallback_answer = await self._handle_no_results_async(query)
                result: dict[str, Any] = {"answer": fallback_answer, "query": query}
                if show_sources:
                    result["sources"] = []
                return result

            chunks = self._union_opener_chunks(
                query, chunks, source_filter, top_k=effective_top_k
            )
            chunks = self._apply_heading_diversity(chunks)

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
                                if self._on_chunk and (content or _reasoning):
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

            # --- Page-number lookup: "what is on page 500" ---
            page_result = await self._answer_page_query_async(query)
            if page_result is not None:
                return page_result

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
                    # Scoped retrieval embeds the name-stripped query (path
                    # tokens pollute the embedding); prompts/results/logs keep
                    # the rewritten query as-is.
                    scoped_rewritten = (
                        self._scoped_search_query(rewritten_query)
                        if source_filter
                        else rewritten_query
                    )
                    chunks = await self._searcher.search_async(
                        scoped_rewritten,
                        top_k=effective_top_k,
                        source_filter=source_filter,
                    )
                    if span and chunks:
                        span.set_attribute("rag.chunks_returned", len(chunks))
            finally:
                retrieval_duration = time.perf_counter() - retrieval_start
                metrics.record("retrieval_latency_async", retrieval_duration)
                logger.debug("retrieval_latency_async: %.3fs", retrieval_duration)

            if not self._has_relevant_chunks(
                chunks, threshold=self._relevance_gate_threshold(source_filter)
            ):
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

            chunks = self._union_opener_chunks(
                rewritten_query, chunks, source_filter, top_k=effective_top_k
            )
            chunks = self._apply_heading_diversity(chunks)

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
                                if self._on_chunk and (content or _reasoning):
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
