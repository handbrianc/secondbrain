"""RAG pipeline for orchestrating retrieval and generation.

This module provides the RAGPipeline class that orchestrates the complete
Retrieval-Augmented Generation workflow for conversational Q&A.
"""

import logging
from typing import Any

from secondbrain.config import get_config
from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.search import Searcher

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
        llm_provider: OllamaLLMProvider for generation.
        rewriter: Optional QueryRewriter for context-aware queries.
        top_k: Default number of context chunks to retrieve.
        context_window: Number of messages to keep in conversation context.

    Example:
        >>> searcher = Searcher()
        >>> llm_provider = OllamaLLMProvider()
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
        context_window: int = 10,
    ) -> None:
        """Initialize RAG pipeline with components.

        Args:
            searcher: Searcher instance for semantic search.
            llm_provider: OllamaLLMProvider for generation.
            rewriter: QueryRewriter for context-aware queries (optional).
            top_k: Number of chunks to retrieve (default: 5).
            context_window: Messages to keep in context (default: 10).

        Example:
            >>> searcher = Searcher()
            >>> llm_provider = OllamaLLMProvider()
            >>> pipeline = RAGPipeline(searcher, llm_provider, top_k=10)
        """
        self._searcher = searcher
        self._llm_provider = llm_provider
        self._rewriter = rewriter
        self._top_k = top_k
        self._context_window = context_window
        self._config = get_config()

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
        try:
            effective_top_k = top_k if top_k is not None else self._top_k

            # Step 1: Retrieve chunks via searcher.search()
            chunks = self._searcher.search(query, top_k=effective_top_k)

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

            # Step 5: Generate answer via llm_provider.generate()
            answer = self._llm_provider.generate(
                prompt=prompt,
                temperature=self._config.llm_temperature,
                max_tokens=self._config.llm_max_tokens,
            )

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
            chunks = self._searcher.search(rewritten_query, top_k=effective_top_k)

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

            # Step 6: Generate answer via llm_provider.chat()
            answer = self._llm_provider.generate(
                prompt=prompt,
                temperature=self._config.llm_temperature,
                max_tokens=self._config.llm_max_tokens,
            )

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
        max_chars: int = 8000,
    ) -> str:
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
            if len(chunk_text) > 500:
                chunk_text = chunk_text[:500] + "..."

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
        You are a helpful assistant. Answer questions based on the
        provided context from documents. If the answer is not in the
        context, say "I cannot find the answer in the provided documents."

        Context:
        {context}

        {conversation_history if present}

        Question: {query}

        Answer:
        ```

        Args:
            query: User query text.
            context: Formatted context from retrieved chunks.
            conversation_history: Optional conversation history.

        Returns:
            Complete prompt text for LLM.

        Example:
            >>> prompt = pipeline._build_prompt("What is Python?", context)
            >>> "You are a helpful assistant" in prompt
            True
        """
        # Build system instruction
        system_prompt = (
            "You are a helpful assistant. Answer questions based on the "
            "provided context from documents. If the answer is not in the "
            'context, say "I cannot find the answer in the provided documents."'
        )

        # Build prompt
        prompt_parts = [system_prompt]

        # Add context
        if context:
            prompt_parts.append(f"\n\nContext:\n{context}")
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
