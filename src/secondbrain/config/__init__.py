"""Configuration management for secondbrain CLI using Pydantic Settings.

This module provides a Config class that loads configuration from environment
variables following 12-factor app principles, with validation for MongoDB
connection strings, LLM/RAG settings, embedding, chunking, and storage options.
"""

import os
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from secondbrain.config.chunking import ChunkingSummarizerMixin
from secondbrain.config.embedding import SearchEmbeddingMixin
from secondbrain.config.llm import LLMMixin
from secondbrain.config.mongo import MongoMixin
from secondbrain.config.processing import ProcessingStorageMixin
from secondbrain.config.rag import RagMixin

__all__ = ["Config", "config", "get_config"]


class Config(
    LLMMixin,
    RagMixin,
    ChunkingSummarizerMixin,
    SearchEmbeddingMixin,
    ProcessingStorageMixin,
    MongoMixin,
    BaseSettings,
):
    """Configuration for secondbrain CLI.

    Uses environment variables following 12-factor app principles.
    Automatically detects test environment and loads from .env.test if available.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECONDBRAIN_",
        env_file=None,  # Don't auto-load - we handle it manually
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="before")
    @classmethod
    def _load_env_file(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Load from appropriate .env file based on environment.

        When PYTEST_CURRENT_TEST is set, loads from .env.test if it exists.
        Otherwise loads from .env.

        Environment variables take precedence over .env file values.
        """
        # Determine which .env file to load
        is_test_env = os.getenv("PYTEST_CURRENT_TEST") is not None

        if is_test_env and Path(".env.test").exists():
            env_file_path = Path(".env.test")
        elif Path(".env").exists():
            env_file_path = Path(".env")
        else:
            env_file_path = None

        # Load environment variables from file if it exists
        if env_file_path and env_file_path.exists():
            with env_file_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        env_key = key.replace("SECONDBRAIN_", "").lower()
                        if env_key not in values and key not in os.environ:
                            os.environ[key] = value
                            values[env_key] = value

        # Set test-specific defaults if running in test environment
        if is_test_env:
            if "mongo_db" not in values:
                values["mongo_db"] = "secondbrain_test"
            if "mongo_collection" not in values:
                values["mongo_collection"] = "test_embeddings"
            if "circuit_breaker_enabled" not in values:
                values["circuit_breaker_enabled"] = False
            if "rate_limit_enabled" not in values:
                values["rate_limit_enabled"] = False
            if "log_level" not in values:
                values["log_level"] = "debug"

        return values

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
        if self.embedding_dtype not in ("float32", "float64"):
            raise ValueError("embedding_dtype must be 'float32' or 'float64'")
        if self.embedding_storage_format not in ("binary", "array"):
            raise ValueError("embedding_storage_format must be 'binary' or 'array'")
        if self.text_compression_algorithm not in ("gzip", "brotli", "zstd"):
            raise ValueError(
                "text_compression_algorithm must be 'gzip', 'brotli', or 'zstd'"
            )
        if self.rag_chunk_preview_chars >= self.rag_max_context_chars:
            raise ValueError(
                "rag_chunk_preview_chars must be less than rag_max_context_chars"
            )

        # Warn if deprecated binary format is selected
        if self.embedding_storage_format == "binary":
            warnings.warn(
                "embedding_storage_format='binary' is deprecated and incompatible with "
                "vector search operations. Binary format produces incorrect cosine similarity "
                "scores. Please use 'array' format. See: "
                "https://github.com/your-repo/docs/embedding-storage",
                DeprecationWarning,
                stacklevel=1,
            )
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

    Returns:
        Config: Configuration instance loaded from environment variables.
    """
    return Config()


def config() -> Config:
    """Get configuration instance (convenience wrapper).

    Returns:
        Config: Configuration instance loaded from environment variables.
    """
    return get_config()
