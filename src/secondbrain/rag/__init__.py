"""RAG (Retrieval Augmented Generation) pipeline for conversational Q&A.

This module provides:
- RAGPipeline: Orchestrates retrieval and generation
- LocalLLMProvider: Protocol for local LLM backends
- OllamaLLMProvider: Ollama implementation
- LLMProviderFactory: Factory for creating providers
"""

from .interfaces import LocalLLMProvider
from .pipeline import RAGPipeline
from .providers.factory import LLMProviderFactory
from .providers.ollama import OllamaLLMProvider

__all__ = [
    "LLMProviderFactory",
    "LocalLLMProvider",
    "OllamaLLMProvider",
    "RAGPipeline",
]
