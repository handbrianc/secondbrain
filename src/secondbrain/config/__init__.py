"""Configuration module for secondbrain CLI."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_mongo_uri(value: str) -> str:
    """Validate MongoDB URI format.

    Args:
        value: MongoDB URI to validate

    Returns:
        Validated URI string

    Raises:
        ValueError: If URI doesn't match expected format
    """
    if not value.startswith("mongodb://") and not value.startswith("mongodb+srv://"):
        raise ValueError(
            f"mongo_uri must start with 'mongodb://' or 'mongodb+srv://', got: {value}"
        )
    return value


def _validate_ollama_url(value: str) -> str:
    """Validate Ollama URL format.

    Args:
        value: Ollama URL to validate

    Returns:
        Validated URL string

    Raises:
        ValueError: If URL doesn't match expected format
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

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("chunk_size must be positive")
        return v

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int) -> int:
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
        return v

    @model_validator(mode="after")
    def validate_config_values(self) -> "Config":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")
        if self.default_top_k <= 0:
            raise ValueError("default_top_k must be positive")
        return self


@lru_cache
def get_config() -> Config:
    """Get cached configuration instance.

    Returns:
        Config: Configuration instance
    """
    return Config()


# Convenience function for direct access
config = get_config()
