"""Query rewriter for context-aware query expansion.

This module provides QueryRewriter class that rewrites queries using
conversation history for better context and search results.
"""

import logging
import re
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from secondbrain.rag.providers.ollama import OllamaLLMProvider

logger = logging.getLogger(__name__)

__all__ = ["QueryRewriter"]


class QueryRewriter:
    """Rewrites queries using conversation context for better retrieval.

    This class rewrites queries using conversation history to create
    more contextually appropriate queries for search and RAG systems.
    It uses template-based context expansion with LLM-powered rewriting
    and falls back to the original query on failure.

    Attributes:
        llm_provider: Ollama LLM provider for generating rewrites.
        context_window: Number of recent turns to use for context.

    Example:
        >>> from secondbrain.rag.providers.ollama import OllamaLLMProvider
        >>> provider = OllamaLLMProvider()
        >>> rewriter = QueryRewriter(provider, context_window=5)
        >>> history = [
        ...     {"role": "user", "content": "Tell me about ACME contract"},
        ...     {"role": "assistant", "content": "The ACME contract..."},
        ... ]
        >>> rewritten = rewriter.rewrite("What about pricing?", history)
        >>> print(rewritten)
        "What about the pricing of the ACME contract?"
    """

    # Template for standalone query rewriting
    REWRITE_TEMPLATE = (
        "Conversation Context:\n{context}\n\n"
        "Current Question: {query}\n\n"
        "Rewrite the current question as a standalone question that "
        "preserves context from the conversation. Be concise."
    )

    # Pronouns and ambiguous references that indicate need for context
    PRONOUN_PATTERNS: ClassVar[list[str]] = [
        r"\bit\b",  # it
        r"\bthis\b",  # this
        r"\bthat\b",  # that
        r"\bthese\b",  # these
        r"\bthose\b",  # those
        r"\bhe\b",  # he
        r"\bshe\b",  # she
        r"\bthey\b",  # they
        r"\bhim\b",  # him
        r"\bher\b",  # her
        r"\bthem\b",  # them
        r"\bhis\b",  # his
        r"\bhers\b",  # hers
        r"\btheir\b",  # their
        r"\btheirs\b",  # theirs
        r"\bit's\b",  # it's
        r"\bthey're\b",  # they're
        r"\bthey've\b",  # they've
        r"\bthey'd\b",  # they'd
        r"\bwould it\b",  # would it
        r"\bcould it\b",  # could it
        r"\bshould it\b",  # should it
        r"\bthe contract\b",  # the contract (ambiguous without context)
        r"\bthe document\b",  # the document (ambiguous without context)
        r"\bthe file\b",  # the file (ambiguous without context)
        r"\bthe project\b",  # the project (ambiguous without context)
        r"\bthe company\b",  # the company (ambiguous without context)
        r"\bthe deal\b",  # the deal (ambiguous without context)
        r"\bthe agreement\b",  # the agreement (ambiguous without context)
    ]

    def __init__(
        self,
        llm_provider: "OllamaLLMProvider",
        context_window: int = 5,
    ) -> None:
        """Initialize rewriter with LLM provider.

        Args:
            llm_provider: OllamaLLMProvider instance for generating rewrites
            context_window: Number of recent turns to use for context (default: 5)

        Example:
            >>> from secondbrain.rag.providers.ollama import OllamaLLMProvider
            >>> provider = OllamaLLMProvider()
            >>> rewriter = QueryRewriter(provider, context_window=10)
        """
        self._llm_provider = llm_provider
        self._context_window = context_window

    def rewrite(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
    ) -> str:
        """Rewrite a query using conversation context.

        Args:
            query: Current user query
            conversation_history: List of recent {role, content} dicts

        Returns:
            Rewritten query that is standalone and context-aware

        Example:
            >>> history = [
            ...     {"role": "user", "content": "Tell me about ACME contract"},
            ...     {"role": "assistant", "content": "The ACME contract..."},
            ... ]
            >>> rewriter.rewrite("What about pricing?", history)
            "What about the pricing of the ACME contract?"
        """
        # If history is empty, return query as-is
        if not conversation_history or not isinstance(conversation_history, list):
            logger.debug("No conversation history provided, returning original query")
            return query

        # Limit history to context_window messages
        recent_history = (
            conversation_history[-self._context_window :]
            if len(conversation_history) > self._context_window
            else conversation_history
        )

        # Build prompt with conversation context
        prompt = self._build_rewrite_prompt(query, recent_history)

        # Call LLM to rewrite query
        try:
            rewritten = self._call_llm_safely(prompt)

            # Clean up the response
            rewritten = self._clean_llm_response(rewritten)

            # Validate the rewrite is meaningful
            if self._is_valid_rewrite(query, rewritten):
                logger.info(f"Query rewritten: '{query}' -> '{rewritten}'")
                return rewritten
            else:
                logger.warning(
                    f"LLM rewrite not meaningful, falling back to original: {query}"
                )
                return query

        except Exception as e:
            logger.warning(f"Query rewrite failed: {e}, using original query")
            return query

    def rewrite_query(
        self,
        query: str,
        conversation_history: list[dict[str, Any]],
    ) -> str:
        """Alias for rewrite() method.

        Provides a more descriptive name for use in RAGPipeline.

        Args:
            query: Current user query
            conversation_history: List of recent {role, content} dicts

        Returns:
            Rewritten query that is standalone and context-aware
        """
        return self.rewrite(query, conversation_history)

    def _build_rewrite_prompt(
        self,
        query: str,
        history: list[dict[str, Any]],
    ) -> str:
        r"""Build prompt for query rewriting.

        Template:
        ```
        Conversation Context:
        {history formatted as "User: ...\nAssistant: ..."}

        Current Question: {query}

        Rewrite the current question as a standalone question that
        preserves context from the conversation. Be concise.
        ```

        Args:
            query: Current user query
            history: List of recent conversation messages

        Returns:
            Complete prompt string for LLM

        Example:
            >>> rewriter = QueryRewriter(provider)
            >>> history = [{"role": "user", "content": "What is AI?"}]
            >>> prompt = rewriter._build_rewrite_prompt("How does it work?", history)
        """
        # Format history
        context = self._format_history(history)

        # Build template
        return self.REWRITE_TEMPLATE.format(context=context, query=query)

    def _format_history(self, history: list[dict[str, Any]]) -> str:
        r"""Format conversation history as text.

        Args:
            history: List of conversation messages

        Returns:
            Formatted string representation

        Example:
            >>> history = [
            ...     {"role": "user", "content": "Hello"},
            ...     {"role": "assistant", "content": "Hi there!"}
            ... ]
            >>> rewriter._format_history(history)
            "User: Hello\n\nAssistant: Hi there!"
        """
        context_lines = []

        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if content:
                context_lines.append(f"{role.capitalize()}: {content}")

        return "\n\n".join(context_lines)

    def _call_llm_safely(self, prompt: str) -> str:
        """Call the LLM provider with error handling.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            Generated response text

        Raises:
            Exception: If generation fails
        """
        return self._llm_provider.generate(
            prompt=prompt,
            temperature=0.1,  # Deterministic for rewrites
            max_tokens=200,  # Limit output for rewrites
        )

    def _clean_llm_response(self, response: str) -> str:
        r"""Clean up LLM response text.

        Removes extra whitespace, newlines, and common prefixes/suffixes.

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned response text

        Example:
            >>> rewriter = QueryRewriter(provider)
            >>> cleaned = rewriter._clean_llm_response("  \n\nThe answer is 42\n\n  ")
            >>> cleaned
            "The answer is 42"
        """
        # Strip whitespace
        cleaned = response.strip()

        # Remove common prefixes that LLMs sometimes add
        prefixes = [
            "Here is the rewritten question:",
            "Rewritten question:",
            "The question is:",
            "Question:",
            "Standalone question:",
        ]

        for prefix in prefixes:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix) :].strip()
                break

        # Remove extra newlines
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned

    def _is_valid_rewrite(self, original: str, rewritten: str) -> bool:
        """Validate that a rewrite is meaningful.

        Args:
            original: The original query
            rewritten: The rewritten query

        Returns:
            True if the rewrite appears valid and meaningful

        Example:
            >>> rewriter = QueryRewriter(provider)
            >>> rewriter._is_valid_rewrite("What?", "What is machine learning?")
            True
            >>> rewriter._is_valid_rewrite("Hello", "")
            False
        """
        # Check if rewritten is empty or just whitespace
        if not rewritten or not rewritten.strip():
            return False

        # Check if rewritten is too short (likely not useful)
        if len(rewritten.strip()) < 3:
            return False

        # Check if it's just a copy of the original (which is fine)
        if rewritten.strip().lower() == original.strip().lower():
            return True

        # Check for obvious failure patterns
        failure_patterns = [
            "i cannot",
            "i can't",
            "i am unable",
            "sorry",
            "i don't know",
            "not sure",
            "i don't understand",
        ]

        rewritten_lower = rewritten.lower()
        return all(pattern not in rewritten_lower for pattern in failure_patterns)

    def _is_standalone_query(self, query: str) -> bool:
        """Check if query appears to be standalone (no context needed).

        Returns False if query contains pronouns like "it", "this", "that",
        or references like "the contract", "the document" without context.

        Args:
            query: Query to check

        Returns:
            True if query appears standalone, False if it needs context

        Example:
            >>> rewriter = QueryRewriter(provider)
            >>> rewriter._is_standalone_query("What is Python?")
            True
            >>> rewriter._is_standalone_query("What about pricing?")
            True  # "pricing" alone is not a pronoun
            >>> rewriter._is_standalone_query("How does it work?")
            False
        """
        # Simple heuristic: check for pronouns and ambiguous references
        query_lower = query.lower()

        for pattern in self.PRONOUN_PATTERNS:
            if re.search(pattern, query_lower):
                return False

        return True

    def should_rewrite(self, query: str) -> bool:
        """Determine if query needs rewriting.

        Args:
            query: Query to check

        Returns:
            True if query needs context, False if standalone

        Example:
            >>> rewriter = QueryRewriter(provider)
            >>> rewriter.should_rewrite("What is Python?")
            False
            >>> rewriter.should_rewrite("How does it work?")
            True
        """
        # Use _is_standalone_query to decide
        # Return True if rewriting needed (i.e., NOT standalone)
        return not self._is_standalone_query(query)

    @property
    def context_window(self) -> int:
        """Get the context window size."""
        return self._context_window
