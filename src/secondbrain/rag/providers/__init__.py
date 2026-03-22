"""Local LLM provider implementations for RAG pipeline.

This module provides implementations for various local LLM backends:
- OllamaLLMProvider: Ollama implementation (default)
- Future providers: vLLM, llama.cpp, etc.
"""

from .ollama import OllamaLLMProvider
from .factory import LLMProviderFactory

__all__ = [
    "OllamaLLMProvider",
    "LLMProviderFactory",
]
