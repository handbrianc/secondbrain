"""Local embedding generator using sentence-transformers."""

import logging

from sentence_transformers import SentenceTransformer

from secondbrain.exceptions import EmbeddingGenerationError

logger = logging.getLogger(__name__)


class LocalEmbeddingGenerator:
    """Local embedding generator using sentence-transformers.

    Runs entirely in Python with no HTTP calls.
    Uses all-MiniLM-L6-v2 model by default (~80MB, fast, good quality).
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
        """Generate embedding for single text."""
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []
        embeddings = self.model.encode(
            [t for t in texts if t.strip()],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
