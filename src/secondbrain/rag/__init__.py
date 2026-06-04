"""RAG (Retrieval Augmented Generation) pipeline for conversational Q&A.

This module provides:
- RAGPipeline: Orchestrates retrieval and generation
- LocalLLMProvider: Protocol for LLM backends
- LLMProviderFactory: Factory for creating providers
"""

from .interfaces import LocalLLMProvider
from .pipeline import RAGPipeline
from .providers.factory import LLMProviderFactory

__all__ = [
    "LLMProviderFactory",
    "LocalLLMProvider",
    "RAGPipeline",
]
