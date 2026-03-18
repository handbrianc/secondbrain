"""Local embedding generator using sentence-transformers."""

import logging

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Target embedding dimensions (truncate to match expected dimensions)
TARGET_EMBEDDING_DIMENSIONS = 384


class LocalEmbeddingGenerator:
    """Local embedding generator using sentence-transformers.

    Runs entirely in Python with no HTTP calls.
    Uses all-MiniLM-L6-v2 model by default (~80MB, fast, good quality).
    Truncates embeddings to 384 dimensions for compatibility.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        """Initialize local embedding generator."""
        self.model_name = model_name
        self._model: SentenceTransformer | None = None
        logger.info("Loading local embedding model: %s", model_name)

    @property
    def model(self) -> SentenceTransformer:
        """Get or create the model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
            logger.info("Model loaded: %s", self.model_name)
        return self._model

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Truncates to TARGET_EMBEDDING_DIMENSIONS (384) for compatibility.
        """
        embedding = self.model.encode(text, convert_to_numpy=True).tolist()
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

    def close(self) -> None:
        """Close the model and release resources."""
        if self._model is not None:
            logger.info("Closing embedding model: %s", self.model_name)
            # SentenceTransformer doesn't have a close() method, but we can delete the reference
            # to allow garbage collection
            self._model = None
            logger.info("Embedding model closed successfully")
