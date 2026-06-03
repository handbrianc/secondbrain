"""Mock embedding provider for fast tests.

This provides deterministic, fast embeddings for unit tests that don't
need to test actual embedding quality.
"""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from .interfaces import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """Fast mock embedding provider for testing.

    Generates deterministic pseudo-random embeddings based on input text.
    Much faster than real embedding models (microseconds vs seconds).

    This class implements the EmbeddingProvider protocol for compatibility
    with the provider factory pattern.
    """

    def __init__(self, model_name: str = "mock-embedding", dimension: int = 384):
        """Initialize mock embedding provider.

        Args:
            model_name: Mock model name (for identification).
            dimension: Embedding dimension (default: 384).
        """
        self.model_name = model_name
        self.dimension = dimension

    def generate(self, text: str) -> list[float]:
        """Generate a deterministic embedding for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        # Create deterministic hash-based embedding
        hash_bytes = hashlib.sha256(text.encode()).digest()
        # Convert to normalized vector
        vector = (
            np.frombuffer(hash_bytes[:32], dtype=np.uint8).astype(np.float32) / 255.0
        )
        # Pad or truncate to target dimension
        if len(vector) < self.dimension:
            vector = np.pad(vector, (0, self.dimension - len(vector)))
        else:
            vector = vector[: self.dimension]
        # Normalize to unit vector
        vector = vector / np.linalg.norm(vector)
        return vector.tolist()

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors.
        """
        return [self.generate(text) for text in texts]

    async def generate_async(self, text: str) -> list[float]:
        """Async version of generate.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        # Mock is so fast that async adds no value, just call sync version
        return self.generate(text)

    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Async version of generate_batch.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors.
        """
        return self.generate_batch(texts)

    def validate_connection(self, force: bool = False) -> bool:
        """Mock connection validation (always returns True).

        Args:
            force: Ignored for mock provider.

        Returns:
            Always True (mock is always available).
        """
        return True

    def close(self) -> None:
        """Clean up resources."""
        pass

    def __repr__(self) -> str:
        # Use old class name in repr for backward compatibility
        return f"MockEmbeddingGenerator(model={self.model_name}, dimension={self.dimension})"


# Backward compatibility alias
MockEmbeddingGenerator = MockEmbeddingProvider
MockLocalEmbeddingGenerator: Any = MockEmbeddingProvider
