"""RAG (Retrieval Augmented Generation) pipeline for conversational Q&A.

This module provides:
- RAGPipeline: Orchestrates retrieval and generation
- LocalLLMProvider: Protocol for local LLM backends
- OpenAILLMProvider: OpenAI-compatible API implementation
- AnthropicLLMProvider: Anthropic Claude implementation
- LLMProviderFactory: Factory for creating providers
"""

from .interfaces import LocalLLMProvider
from .pipeline import RAGPipeline
from .providers.anthropic import AnthropicLLMProvider
from .providers.factory import LLMProviderFactory
from .providers.openai import OpenAILLMProvider

__all__ = [
    "AnthropicLLMProvider",
    "LLMProviderFactory",
    "LocalLLMProvider",
    "OpenAILLMProvider",
    "RAGPipeline",
]
