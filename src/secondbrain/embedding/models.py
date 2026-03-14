"""Embedding models and data structures."""

from typing import TypedDict


class EmbeddingResult(TypedDict):
    """Typed dictionary for embedding result.

    Attributes
    ----------
        embedding: List of float values representing the embedding vector.
    """

    embedding: list[float]
