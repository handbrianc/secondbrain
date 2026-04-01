"""Local embedding generator using sentence-transformers."""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any

import torch

from secondbrain.exceptions import EmbeddingGenerationError

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

    def __init__(
        self, model_name: str = "all-MiniLM-L6-v2", device: str | None = None
    ) -> None:
        """Initialize local embedding generator.

        Args:
            model_name: Name of sentence-transformers model to use.
            device: Device to use ('cuda', 'cpu', 'mps', or None for auto-detect).
        """
        self.model_name = model_name
        detected_device = device or self._detect_device()
        self.device = detected_device
        self._model: Any = None
        self._connection_valid: bool | None = None
        self._connection_checked_at: float = 0.0

        logger.info(
            "Initializing embedding model: %s on device: %s",
            self.model_name,
            self.device,
        )

        if self.device == "cuda":
            logger.info("GPU acceleration enabled: CUDA detected")
        elif self.device == "mps":
            logger.info("GPU acceleration enabled: Apple Silicon MPS detected")
        else:
            logger.info("CPU mode: No GPU available")

        # Suppress third-party logs
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    def _detect_device(self) -> str:
        """Auto-detect best available device for GPU acceleration.

        Returns:
            Device string: 'cuda' for NVIDIA, 'mps' for Apple Silicon, 'cpu' otherwise.
        """
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @property
    def model(self) -> Any:
        """Get or create the model with GPU support."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device=self.device)  # type: ignore[operator]
        return self._model

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text.

        Truncates to TARGET_EMBEDDING_DIMENSIONS (384) for compatibility.

        Raises:
            EmbeddingGenerationError: If embedding generation fails.
        """
        try:
            embedding: list[float] = self.model.encode(
                text, convert_to_numpy=True
            ).tolist()
            return embedding[:TARGET_EMBEDDING_DIMENSIONS]
        except Exception as e:
            raise EmbeddingGenerationError(
                f"Failed to generate embedding for text: {e}"
            ) from e

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
