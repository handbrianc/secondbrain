"""Local LLM provider implementations for RAG pipeline.

This module provides implementations for various local LLM backends:
- OllamaLLMProvider: Ollama implementation (default)
- Future providers: vLLM, llama.cpp, etc.
"""

from __future__ import annotations

from .factory import LLMProviderFactory
from .ollama import OllamaLLMProvider

__all__ = [
    "LLMProviderFactory",
    "OllamaLLMProvider",
]
