"""Local LLM provider interface for RAG pipeline.

Defines the protocol that all local LLM providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Protocol


class LocalLLMProvider(Protocol):
    """Protocol for local LLM providers.

    All local LLM backends (Ollama, vLLM, llama.cpp, etc.) must implement
    this interface to be used with the RAG pipeline.
    """

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the LLM.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ConnectionError: If the LLM server is unreachable.
            TimeoutError: If the request times out.
            RuntimeError: If the LLM returns an error.
        """
        ...

    async def agenerate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async version of generate.

        Args:
            prompt: The prompt to send to the LLM.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Generated response text.
        """
        ...

    def health_check(self) -> bool:
        """Check if the LLM server is available.

        Returns:
            True if the server is responsive, False otherwise.
        """
        ...
