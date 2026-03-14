"""Embedding generation module for Ollama integration.

This module provides embedding generation functionality using Ollama API.
Public API is re-exported from submodules for clean imports.
"""

import httpx

from secondbrain.exceptions import EmbeddingGenerationError, OllamaUnavailableError

from .generator import EmbeddingGenerator
from .models import EmbeddingResult
from .rate_limiter import RateLimiter

__all__ = [
    "EmbeddingGenerationError",
    "EmbeddingGenerator",
    "EmbeddingResult",
    "OllamaUnavailableError",
    "RateLimiter",
    "httpx",
]
