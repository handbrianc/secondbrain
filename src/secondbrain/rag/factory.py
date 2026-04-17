"""Factory module for creating RAG pipeline components.

This module provides factory functions for creating LLM providers and query
rewriters used in the RAG pipeline. It centralizes component creation logic
and provides sensible defaults based on project configuration.

Usage:
    from secondbrain.rag.factory import create_llm_provider, create_query_rewriter

    llm_provider = create_llm_provider()
    rewriter = create_query_rewriter(llm_provider)
"""

from secondbrain.config import config
from secondbrain.conversation import QueryRewriter
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.providers.factory import LLMProviderFactory


def create_llm_provider() -> LocalLLMProvider:
    """Create an LLM provider based on project configuration.

    This function reads the project configuration and creates the appropriate
    LLM provider instance. It supports multiple backends including Ollama
    (default) and OpenAI.

    Returns:
        Configured LocalLLMProvider instance.

    Raises:
        ValueError: If the configured provider type is not supported.
        RuntimeError: If provider initialization fails.

    Example:
        >>> provider = create_llm_provider()
        >>> response = provider.generate("Hello")
        >>> print(response)
    """
    cfg = config()

    try:
        provider = LLMProviderFactory.create_from_config(cfg)
        return provider
    except ValueError as e:
        raise ValueError(
            f"Failed to create LLM provider: {e}. "
            f"Check SECONDBRAIN_LLM_PROVIDER configuration."
        ) from e
    except Exception as e:
        raise RuntimeError(f"Failed to initialize LLM provider: {e}") from e


def create_query_rewriter(llm_provider: LocalLLMProvider) -> QueryRewriter:
    """Create a query rewriter for context-aware query expansion.

    Query rewriter enhances queries by incorporating conversation history
    and context, improving retrieval accuracy for multi-turn conversations.

    Args:
        llm_provider: Configured LLM provider to use for rewriting.

    Returns:
        Configured QueryRewriter instance.

    Example:
        >>> provider = create_llm_provider()
        >>> rewriter = create_query_rewriter(provider)
        >>> rewritten = rewriter.rewrite_query("What about it?", history)
    """
    try:
        rewriter = QueryRewriter(llm_provider=llm_provider)
        return rewriter
    except Exception as e:
        raise RuntimeError(f"Failed to create query rewriter: {e}") from e


__all__ = [
    "create_llm_provider",
    "create_query_rewriter",
]
