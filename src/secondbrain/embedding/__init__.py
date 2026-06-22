"""Embedding generation with pluggable provider support.

This module provides embedding providers for generating text embeddings:
- OpenAIEmbeddingProvider: OpenAI API or OpenAI-compatible endpoints (default)
- MockEmbeddingProvider: Fast mock embeddings for testing

The EmbeddingProviderFactory creates provider instances based on configuration.
"""

from .interfaces import EmbeddingProvider
from .mock import MockEmbeddingGenerator, MockEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderFactory",
    "MockEmbeddingGenerator",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
]


def __getattr__(name: str):
    """Lazy import for EmbeddingProviderFactory and OpenAIEmbeddingProvider to avoid circular imports."""
    if name == "EmbeddingProviderFactory":
        from .providers.factory import EmbeddingProviderFactory

        return EmbeddingProviderFactory
    elif name == "OpenAIEmbeddingProvider":
        from .providers.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")