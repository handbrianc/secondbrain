"""Context/prompt/history formatting mixin for the RAG pipeline."""

from __future__ import annotations

from typing import Any

from secondbrain.config import config
from secondbrain.rag.pipeline._attributes import _RAGPipelineState


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
                Chunks may also carry an optional non-empty ``heading_path``
                string, appended last to the source-line tags as a structural
                scope label; chunks without it format exactly as before.
            max_chars: Maximum context length.

        Returns:
            Formatted context string.

        Example:
            >>> chunks = [{"chunk_text": "Hello", "source_file": "doc.pdf", "page": 1}]
            >>> pipeline._format_context(chunks)
            'Source: doc.pdf (page 1)\nHello\n'
            >>> chunks = [{
            ...     "chunk_text": "Snapshot mode stores VM state.",
            ...     "source_file": "doc.pdf",
            ...     "page": 12,
            ...     "chunk_role": "body",
            ...     "heading_path": "Chapter 16 > Backup Modes > snapshot mode",
            ... }]
            >>> pipeline._format_context(chunks)
            'Source: doc.pdf (page 12 [body, Chapter 16 > Backup Modes > snapshot mode])\nSnapshot mode stores VM state.\n'
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
            heading_path = chunk.get("heading_path")
            if heading_path:
                tags.append(heading_path)
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
