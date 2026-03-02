"""Configuration module for secondbrain CLI."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @model_validator(mode="after")
    def validate_config(self) -> "Config":
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
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
