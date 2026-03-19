"""Configuration management for secondbrain CLI using Pydantic Settings.

This module provides a Config class that loads configuration from environment
variables following 12-factor app principles, with validation for MongoDB
connection strings.
"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Config", "config", "get_config"]


def _validate_mongo_uri(value: str) -> str:
    """Validate MongoDB URI format.

    Args:
        value: MongoDB URI to validate.

    Returns
    -------
        Validated URI string.

    Raises
    ------
        ValueError: If URI doesn't start with mongodb:// or mongodb+srv://
    """
    if not value.startswith("mongodb://") and not value.startswith("mongodb+srv://"):
        raise ValueError(
            f"mongo_uri must start with 'mongodb://' or 'mongodb+srv://', got: {value}"
        )
    return value


class Config(BaseSettings):
    """Configuration for secondbrain CLI.

    Uses environment variables following 12-factor app principles.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECONDBRAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # MongoDB settings
    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI",
    )

    @field_validator("mongo_uri")
    @classmethod
    def validate_mongo_uri(cls, v: str) -> str:
        """Validate MongoDB URI.

        Args:
            v: MongoDB URI to validate.

        Returns
        -------
            Validated URI string.
        """
        return _validate_mongo_uri(v)

    mongo_db: str = Field(
        default="secondbrain",
        description="Database name",
    )
    mongo_collection: str = Field(
        default="embeddings",
        description="Collection name for embeddings",
    )

    local_embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description="Sentence-transformers model for local embedding (e.g., all-MiniLM-L6-v2, all-mpnet-base-v2)",
    )

    # Chunking settings
    chunk_size: int = Field(
        default=4096,
        description="Chunk size for document splitting",
    )
    chunk_overlap: int = Field(
        default=50,
        description="Chunk overlap for splitting",
    )

    # File extension settings
    supported_extensions: str = Field(
        default="pdf,docx,pptx,xlsx,html,htm,md,txt,asciidoc,adoc,tex,csv,"
        "png,jpg,jpeg,tiff,tif,bmp,webp,wav,mp3,vtt,xml,json",
        description="Comma-separated list of supported file extensions (without dots)",
    )

    # Search settings
    default_top_k: int = Field(
        default=5,
        description="Default number of search results",
    )

    # Embedding settings
    embedding_dimensions: int = Field(
        default=384,
        description=(
            "Dimensionality of embedding vectors (must match model). "
            "384 = sentence-transformers/all-MiniLM-L6-v2 default. "
            "Other models: 768 (all-mpnet-base-v2), 1024 (large models)"
        ),
    )
    embedding_cache_size: int = Field(
        default=1000,
        description=(
            "Maximum number of embeddings to cache (0 disables cache). "
            "Caches reduce API calls for duplicate text. "
            "1000 embeddings x 384 floats x 4 bytes ~1.5MB RAM"
        ),
    )
    embedding_batch_size: int = Field(
        default=20,
        description=(
            "Batch size for embedding generation (1-100). "
            "Higher = better throughput, lower = less memory. "
            "sentence-transformers API typically handles 20-50 well. "
            "Max 100 to prevent timeout on slow networks"
        ),
    )

    # Document ingestion settings
    max_file_size_bytes: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file size in bytes (default: 100MB)",
    )

    # Storage settings
    index_ready_retry_count: int = Field(
        default=15,
        description=(
            "Max retries for index ready check (exponential backoff). "
            "With 100ms base, 2s max: 15 retries ≈ 15 seconds total wait time. "
            "MongoDB Atlas index creation typically completes in 5-10 seconds"
        ),
    )
    index_ready_retry_delay: float = Field(
        default=1.0,
        description=(
            "Initial delay for index ready retries (not used directly; "
            "exponential backoff starts at 100ms, this is for future extensibility)"
        ),
    )

    # Rate limiting settings
    rate_limit_max_requests: int = Field(
        default=10,
        description=(
            "Maximum requests per rate limit window. "
            "Protects sentence-transformers API from overload. "
            "10 req/s = 600 req/min, sufficient for batch processing"
        ),
    )
    rate_limit_window_seconds: float = Field(
        default=1.0,
        description=(
            "Rate limit window in seconds. "
            "1-second window = sliding window rate limiting. "
            "Combine with rate_limit_max_requests for token-bucket style limiting"
        ),
    )

    # Connection validation settings
    connection_cache_ttl: float = Field(
        default=60.0,
        description="TTL for connection validation cache in seconds",
    )

    # Multicore processing settings
    max_workers: int | None = Field(
        default=None,
        description="Maximum number of worker processes for parallel processing (default: auto-detect CPU count)",
    )

    streaming_enabled: bool = Field(
        default=True,
        description="Enable streaming processing for memory efficiency (default: true)",
    )
    streaming_chunk_batch_size: int = Field(
        default=100,
        description="Number of chunks to process per streaming batch (1-200, default: 100). Larger batches improve embedding throughput by utilizing batch API calls.",
    )

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk size is positive.

        Args:
            v: Chunk size value to validate.

        Returns
        -------
            Validated chunk size value.

        Raises
        ------
            ValueError: If chunk size is not positive.
        """
        if v <= 0:
            raise ValueError("chunk_size must be positive")
        return v

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int) -> int:
        """Validate chunk overlap is non-negative.

        Args:
            v: Chunk overlap value to validate.

        Returns
        -------
            Validated chunk overlap value.

        Raises
        ------
            ValueError: If chunk overlap is negative.
        """
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
        return v

    @field_validator("embedding_cache_size")
    @classmethod
    def validate_embedding_cache_size(cls, v: int) -> int:
        """Validate embedding cache size is non-negative.

        Args:
            v: Cache size value to validate.

        Returns
        -------
            Validated cache size value.

        Raises
        ------
            ValueError: If cache size is negative.
        """
        if v < 0:
            raise ValueError("embedding_cache_size must be non-negative")
        return v

    @field_validator("embedding_batch_size")
    @classmethod
    def validate_embedding_batch_size(cls, v: int) -> int:
        """Validate embedding batch size is between 1 and 100.

        Args:
            v: Batch size value to validate.

        Returns
        -------
            Validated batch size value.

        Raises
        ------
            ValueError: If batch size is not in range [1, 100].
        """
        if v <= 0 or v > 100:
            raise ValueError("embedding_batch_size must be between 1 and 100")
        return v

    @field_validator("streaming_chunk_batch_size")
    @classmethod
    def validate_streaming_chunk_batch_size(cls, v: int) -> int:
        """Validate streaming chunk batch size is between 1 and 200.

        Args:
            v: Batch size value to validate.

        Returns
        -------
            Validated batch size value.

        Raises
        ------
            ValueError: If batch size is not in range [1, 200].
        """
        if v <= 0 or v > 200:
            raise ValueError("streaming_chunk_batch_size must be between 1 and 200")
        return v

    @model_validator(mode="after")
    def validate_config_values(self) -> "Config":
        """Validate configuration values.

        Returns
        -------
            Config instance after validation.

        Raises
        ------
            ValueError: If validation fails.
        """
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be positive")
        if self.max_workers is not None and self.max_workers <= 0:
            raise ValueError("max_workers must be positive when set")
        if self.embedding_cache_size < 0:
            raise ValueError("embedding_cache_size must be non-negative")
        if self.embedding_batch_size <= 0 or self.embedding_batch_size > 100:
            raise ValueError("embedding_batch_size must be between 1 and 100")
        if (
            self.streaming_chunk_batch_size <= 0
            or self.streaming_chunk_batch_size > 200
        ):
            raise ValueError("streaming_chunk_batch_size must be between 1 and 200")
        return self

    @property
    def extensions_set(self) -> set[str]:
        """Get supported extensions as a set with dots.

        Returns
        -------
            Set of file extensions with leading dots (e.g., {".pdf", ".docx"}).
        """
        extensions = self.supported_extensions.split(",")
        # Ensure we don't end up with double dots if an input already has a leading dot
        return {f".{ext.strip().lstrip('.')}" for ext in extensions if ext.strip()}


@lru_cache
def get_config() -> Config:
    """Get cached configuration instance.

    Configuration supports multicore processing via `max_workers` setting
    (or `--cores` CLI flag for ingestion command).

    Returns
    -------
        Config: Configuration instance.
    """
    return Config()


# Convenience function for direct access
config = get_config()
