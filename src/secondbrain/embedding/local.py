"""Local embedding generator using sentence-transformers."""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any

logger = logging.getLogger(__name__)

# Target embedding dimensions (truncate to match expected dimensions)
TARGET_EMBEDDING_DIMENSIONS = 384

# Connection cache TTL (seconds)
CONNECTION_CACHE_TTL = 300  # 5 minutes


class LocalEmbeddingGenerator:
    """Local embedding generator using sentence-transformers.

    Runs entirely in Python with no HTTP calls.
    Uses all-MiniLM-L6-v2 model by default (~80MB, fast, good quality).
    Truncates embeddings to 384 dimensions for compatibility.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize local embedding generator."""
        self.model_name = model_name
        self._model: Any = None
        self._connection_valid: bool | None = None
        self._connection_checked_at: float = 0.0
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    @property
    def model(self) -> Any:
        """Get or create the model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)  # type: ignore[operator]
        return self._model

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Truncates to TARGET_EMBEDDING_DIMENSIONS (384) for compatibility.
        """
        embedding: list[float] = self.model.encode(text, convert_to_numpy=True).tolist()
        return embedding[:TARGET_EMBEDDING_DIMENSIONS]

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Truncates each embedding to TARGET_EMBEDDING_DIMENSIONS (384).
        """
        if not texts:
            return []
        embeddings = self.model.encode(
            [t for t in texts if t.strip()],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        # Truncate all embeddings to target dimensions
        return [emb[:TARGET_EMBEDDING_DIMENSIONS] for emb in embeddings.tolist()]

    def validate_connection(self, force: bool = False) -> bool:
        """Check if the embedding model is available and working.

        Args:
            force: If True, bypass cache and revalidate.

        Returns
        -------
            True if model is available and can generate embeddings, False otherwise.
        """
        current_time = monotonic()

        # Check cache first
        if (
            not force
            and self._connection_valid is not None
            and current_time - self._connection_checked_at < CONNECTION_CACHE_TTL
        ):
            return self._connection_valid

        try:
            # Test with a simple text
            test_text = "test"
            _ = self.model.encode(test_text, convert_to_numpy=True)
            self._connection_valid = True
            logger.debug("Embedding model validation successful")
        except Exception as e:
            logger.warning(
                "Embedding model validation failed: %s: %s", type(e).__name__, e
            )
            self._connection_valid = False

        self._connection_checked_at = current_time
        return self._connection_valid

    def close(self) -> None:
        """Close the model and release resources."""
        if self._model is not None:
            logger.info("Closing embedding model: %s", self.model_name)
            # SentenceTransformer doesn't have a close() method, but we can delete the reference
            # to allow garbage collection
            self._model = None
            self._connection_valid = None
            self._connection_checked_at = 0.0
            logger.info("Embedding model closed successfully")
