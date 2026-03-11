"""Configuration management for secondbrain CLI using Pydantic Settings.

This module provides a Config class that loads configuration from environment
variables following 12-factor app principles, with validation for MongoDB
and Ollama connection strings.
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

    Returns:
        Validated URI string.

    Raises:
        ValueError: If URI doesn't start with mongodb:// or mongodb+srv://
    """
    if not value.startswith("mongodb://") and not value.startswith("mongodb+srv://"):
        raise ValueError(
            f"mongo_uri must start with 'mongodb://' or 'mongodb+srv://', got: {value}"
        )
    return value


def _validate_ollama_url(value: str) -> str:
    """Validate Ollama URL format.

    Args:
        value: Ollama URL to validate.

    Returns:
        Validated URL string.

    Raises:
        ValueError: If URL doesn't have valid scheme and host
    """
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            f"ollama_url must be a valid URL with scheme and host, got: {value}"
        )
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"ollama_url must use http or https scheme, got: {parsed.scheme}"
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

        Returns:
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

    # Ollama settings
    ollama_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API URL",
    )

    @field_validator("ollama_url")
    @classmethod
    def validate_ollama_url(cls, v: str) -> str:
        """Validate Ollama URL.

        Args:
            v: Ollama URL to validate.

        Returns:
            Validated URL string.
        """
        return _validate_ollama_url(v)

    model: str = Field(
        default="embeddinggemma:latest",
        description="Embedding model to use",
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
        default=768,
        description="Dimensionality of embedding vectors (must match model)",
    )

    # Document ingestion settings
    max_file_size_bytes: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file size in bytes (default: 100MB)",
    )

    # Storage settings
    index_ready_retry_count: int = Field(
        default=15,
        description="Max retries for index ready check",
    )
    index_ready_retry_delay: float = Field(
        default=1.0,
        description="Delay between index ready retries in seconds",
    )

    # Rate limiting settings
    rate_limit_max_requests: int = Field(
        default=10,
        description="Maximum requests per rate limit window",
    )
    rate_limit_window_seconds: float = Field(
        default=1.0,
        description="Rate limit window in seconds",
    )

    # Connection validation settings
    connection_cache_ttl: float = Field(
        default=60.0,
        description="TTL for connection validation cache in seconds",
    )

    # Circuit breaker settings
    circuit_breaker_recovery_timeout: float = Field(
        default=30.0,
        description="Circuit breaker recovery timeout in seconds",
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        description="Number of failures before circuit opens",
    )

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk size is positive.

        Args:
            v: Chunk size value to validate.

        Returns:
            Validated chunk size value.

        Raises:
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

        Returns:
            Validated chunk overlap value.

        Raises:
            ValueError: If chunk overlap is negative.
        """
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_config_values(self) -> "Config":
        """Validate configuration values.

        Returns:
            Config instance after validation.

        Raises:
            ValueError: If validation fails.
        """
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be positive")
        return self

    @property
    def extensions_set(self) -> set[str]:
        """Get supported extensions as a set with dots.

        Returns:
            Set of file extensions with leading dots (e.g., {".pdf", ".docx"}).
        """
        extensions = self.supported_extensions.split(",")
        return {f".{ext.strip()}" for ext in extensions if ext.strip()}


@lru_cache
def get_config() -> Config:
    """Get cached configuration instance.

    Returns:
        Config: Configuration instance.
    """
    return Config()


# Convenience function for direct access
config = get_config()
