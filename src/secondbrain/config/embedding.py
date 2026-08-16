"""Search and embedding settings fragment."""

from pydantic import Field, field_validator


class SearchEmbeddingMixin:
    """Search and embedding settings."""

    default_top_k: int = Field(
        default=50,
        description="Default number of search results (higher = more context for better answers)",
    )
    embedding_provider: str = Field(
        default="openai",
        description="Embedding provider type (openai, or any OpenAI-compatible API)",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model name for the configured provider",
    )
    embedding_api_key: str | None = Field(
        default=None,
        description="API key for embedding provider (openai). Defaults to SECONDBRAIN_EMBEDDING_API_KEY env var.",
    )
    embedding_api_base: str | None = Field(
        default=None,
        description="Base URL for embedding API (openai). Defaults to OpenAI endpoint.",
    )
    embedding_dimensions: int = Field(
        default=1536,
        description="Dimensionality of embedding vectors (must match model)",
    )
    embedding_cache_size: int = Field(
        default=1000,
        description="Maximum number of embeddings to cache (0 disables cache)",
    )

    @field_validator("embedding_cache_size")
    @classmethod
    def validate_embedding_cache_size(cls, v: int) -> int:
        """Validate embedding cache size is non-negative."""
        if v < 0:
            raise ValueError("embedding_cache_size must be non-negative")
        return v

    embedding_batch_size: int = Field(
        default=20,
        description="Batch size for embedding generation (1-100)",
    )

    @field_validator("embedding_batch_size")
    @classmethod
    def validate_embedding_batch_size(cls, v: int) -> int:
        """Validate embedding batch size is between 1 and 100."""
        if v <= 0 or v > 100:
            raise ValueError("embedding_batch_size must be between 1 and 100")
        return v

    embedding_timeout: int = Field(
        default=300,
        description="Request timeout for embedding API calls in seconds",
    )
