"""Qdrant vector storage settings fragment for :class:`secondbrain.config.Config`.

Replaces the MongoDB-backed vector store with Qdrant. The vector backend is a
pure cosine-similarity database; all chunk metadata (including ``chunk_text``)
travels in the Qdrant payload so ``search`` returns everything the Searcher
needs in a single round trip.
"""

from pydantic import Field, field_validator


class QdrantMixin:
    """Qdrant vector storage configuration."""

    storage_backend: str = Field(
        default="qdrant",
        description=(
            "Vector storage backend (override via SECONDBRAIN_STORAGE_BACKEND "
            "env var). 'qdrant' (default) or 'mock' (fast in-memory, tests)."
        ),
    )

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, v: str) -> str:
        """Validate the storage backend selector."""
        allowed = {"qdrant", "mock"}
        if v.lower() not in allowed:
            raise ValueError(
                f"storage_backend must be one of {sorted(allowed)}, got: {v}"
            )
        return v.lower()

    qdrant_url: str = Field(
        default="http://localhost:6333",
        description="Qdrant server URL (override via SECONDBRAIN_QDRANT_URL env var)",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key (optional, for authenticated servers)",
    )
    qdrant_collection: str = Field(
        default="embeddings",
        description="Qdrant collection name for embeddings",
    )
