"""Embedding provider interface for pluggable embedding backends.

This module defines the EmbeddingProvider protocol that all embedding
implementations must follow, enabling support for multiple embedding
backends (local sentence-transformers, OpenAI API, etc.).
"""

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    All embedding backends (local sentence-transformers, OpenAI API, etc.)
    must implement this interface to be used with the search and ingestion pipeline.

    This protocol defines the contract for:
    - Single text embedding generation (sync and async)
    - Batch embedding generation (sync and async)
    - Connection validation
    - Resource cleanup
    """

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ConnectionError: If API is unreachable (for remote providers).
            RuntimeError: If embedding generation fails.
        """
        ...  # pragma: no cover

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.
        """
        ...  # pragma: no cover

    async def generate_async(self, text: str) -> list[float]:
        """Async version of generate.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        ...  # pragma: no cover

    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Async version of generate_batch.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.
        """
        ...  # pragma: no cover

    def validate_connection(self, force: bool = False) -> bool:
        """Check if the embedding service is available.

        Args:
            force: If True, bypass cache and revalidate.

        Returns:
            True if service is available, False otherwise.
        """
        ...  # pragma: no cover

    def close(self) -> None:
        """Close resources and release connections.

        This method should be called when the provider is no longer needed
        to release any held resources (network connections, model memory, etc.).
        """
        ...  # pragma: no cover
