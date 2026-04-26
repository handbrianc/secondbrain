"""Mock embedding generator for fast tests.

This provides deterministic, fast embeddings for unit tests that don't
need to test actual embedding quality.
"""

import hashlib
from typing import Any

import numpy as np


class MockEmbeddingGenerator:
    """Fast mock embedding generator for testing.

    Generates deterministic pseudo-random embeddings based on input text.
    Much faster than real embedding models (microseconds vs seconds).
    """

    def __init__(self, model_name: str = "mock-embedding", dimension: int = 384):
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

    def close(self) -> None:
        """Clean up resources."""
        pass

    def __repr__(self) -> str:
        return f"MockEmbeddingGenerator(model={self.model_name}, dimension={self.dimension})"


# For backwards compatibility
MockLocalEmbeddingGenerator: Any = MockEmbeddingGenerator
