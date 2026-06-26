"""RAG pipeline for orchestrating retrieval and generation.

This module provides the RAGPipeline class that orchestrates the complete
Retrieval-Augmented Generation workflow for conversational Q&A.
"""

import logging
import time
from typing import Any

from secondbrain.config import config
from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.security_filter import SecurityFilter
from secondbrain.search import Searcher
from secondbrain.utils.perf_monitor import metrics
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)

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
        top_k: int = 5,
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
        self._llm_provider = llm_provider
        self._rewriter = rewriter
        self._top_k = top_k
        self._context_window = context_window
        self._config = config()
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
