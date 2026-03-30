"""Configuration validation framework.

This module provides comprehensive validation for SecondBrain configuration
to catch errors early and provide clear error messages.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecondBrainSettings(BaseSettings):
    """SecondBrain application settings with comprehensive validation.

    All configuration values are validated at startup to provide
    clear error messages for misconfigurations.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECONDBRAIN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",  # Prevent typos in config
    )

    # MongoDB Configuration
    mongo_uri: str = Field(
        ...,
        description="MongoDB connection URI",
        examples=[
            "mongodb://localhost:27017",
            "mongodb+srv://user:pass@cluster.mongodb.net",
        ],
    )
    mongo_db: str = Field(
        default="secondbrain",
        description="MongoDB database name",
        min_length=1,
    )
    mongo_collection: str = Field(
        default="embeddings",
        description="MongoDB collection name for vector storage",
        min_length=1,
    )

    # Embedding Configuration
    local_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Sentence transformers model for local embeddings",
    )
    embedding_dimensions: int = Field(
        default=384,
        ge=64,  # Minimum reasonable dimension
        le=2048,  # Maximum reasonable dimension
        description="Dimension of embedding vectors",
    )

    # Document Processing Configuration
    chunk_size: int = Field(
        default=512,
        ge=64,  # Minimum chunk size
        le=4096,  # Maximum chunk size
        description="Maximum characters per chunk",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,  # Maximum overlap
        description="Overlap between consecutive chunks",
    )

    # Ollama Configuration
    localhost: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL",
    )
    rag_model: str = Field(
        default="llama2",
        description="Ollama model for RAG pipeline",
    )

    # Performance Configuration
    default_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Default number of search results to return",
    )
    rate_limit_max_requests: int = Field(
        default=10,
        ge=1,
        description="Maximum requests per window for rate limiting",
    )
    rate_limit_window_seconds: float = Field(
        default=1.0,
        ge=0.1,
        description="Rate limiting window in seconds",
    )

    # Connection Configuration
    connection_cache_ttl: float = Field(
        default=60.0,
        ge=1.0,
        description="Connection cache TTL in seconds",
    )
    circuit_breaker_failure_threshold: int = Field(
        default=3,
        ge=1,
        description="Failures before circuit breaker opens",
    )
    circuit_breaker_recovery_timeout: float = Field(
        default=60.0,
        ge=0.1,
        description="Recovery timeout in seconds",
    )

    # Logging Configuration
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level",
    )
    log_format: str = Field(
        default="text",
        pattern="^(text|json)$",
        description="Log format (text or JSON)",
    )

    # OpenTelemetry Configuration
    otlp_enabled: bool = Field(
        default=False,
        description="Enable OTLP exporter",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP collector endpoint",
    )
    otlp_timeout: int = Field(
        default=10,
        ge=1,
        le=60,
        description="OTLP export timeout in seconds",
    )

    @field_validator("mongo_uri")
    @classmethod
    def validate_mongo_uri(cls, v: str) -> str:
        """Validate MongoDB URI format.

        Args:
            v: MongoDB connection URI

        Returns:
            Validated URI

        Raises:
            ValueError: If URI format is invalid
        """
        if not v:
            raise ValueError("MongoDB URI cannot be empty")

        if not v.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError(
                f"Invalid MongoDB URI format: {v}. "
                "Must start with 'mongodb://' or 'mongodb+srv://'"
            )

        # Basic sanitization - check for obvious injection attempts
        if ".." in v or ";" in v:
            raise ValueError("MongoDB URI contains invalid characters")

        return v

    @field_validator("mongo_db", "mongo_collection")
    @classmethod
    def validate_database_name(cls, v: str) -> str:
        """Validate database/collection names.

        Args:
            v: Database or collection name

        Returns:
            Validated name

        Raises:
            ValueError: If name is invalid
        """
        if not v:
            raise ValueError("Database/collection name cannot be empty")

        if v.startswith(".") or v.startswith("$"):
            raise ValueError(f"Invalid name '{v}': Cannot start with '.' or '$'")

        if ".." in v:
            raise ValueError(f"Invalid name '{v}': Contains '..'")

        if len(v) > 120:
            raise ValueError(f"Name '{v}' too long: Maximum 120 characters")

        return v

    @field_validator("local_embedding_model")
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """Validate embedding model name.

        Args:
            v: Model name or path

        Returns:
            Validated model name

        Raises:
            ValueError: If model name is invalid
        """
        if not v:
            raise ValueError("Embedding model cannot be empty")

        # Allow HuggingFace format or local paths
        allowed_patterns = [
            r"^sentence-transformers/[\w-]+/[\w-]+$",  # HF format
            r"^[\w-]+$",  # Simple model name
            r"^/[\w/.-]+$",  # Local path
        ]

        if not any(re.match(p, v) for p in allowed_patterns):
            raise ValueError(
                f"Invalid embedding model format: {v}. "
                "Use HuggingFace format (sentence-transformers/model-name) "
                "or local path"
            )

        return v

    @field_validator("localhost")
    @classmethod
    def validate_ollama_url(cls, v: str) -> str:
        """Validate Ollama server URL.

        Args:
            v: Ollama server URL

        Returns:
            Validated URL

        Raises:
            ValueError: If URL is invalid
        """
        if not v:
            raise ValueError("Ollama URL cannot be empty")

        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid Ollama URL: {v}. Must start with 'http://' or 'https://'"
            )

        return v

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int, info: Any) -> int:
        """Validate chunk overlap is less than chunk size.

        Args:
            v: Chunk overlap value
            info: Field validation info

        Returns:
            Validated overlap

        Raises:
            ValueError: If overlap >= chunk_size
        """
        chunk_size = info.data.get("chunk_size", 512)
        if v >= chunk_size:
            raise ValueError(
                f"Chunk overlap ({v}) must be less than chunk size ({chunk_size})"
            )
        return v

    @model_validator(mode="after")
    def validate_configuration(self) -> SecondBrainSettings:
        """Perform cross-field validation.

        Returns:
            Validated settings

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate rate limiting makes sense
        if self.rate_limit_window_seconds < 0.1:
            raise ValueError("Rate limit window must be at least 0.1 seconds")

        # Validate circuit breaker settings
        if self.circuit_breaker_recovery_timeout < 1.0:
            raise ValueError(
                "Circuit breaker recovery timeout must be at least 1 second"
            )

        return self

    def get_mongo_connection_string(self) -> str:
        """Get full MongoDB connection string.

        Returns:
            Complete connection string with database
        """
        return f"{self.mongo_uri}/{self.mongo_db}"

    def get_mongo_collection_path(self) -> str:
        """Get full MongoDB collection path.

        Returns:
            Full path to collection
        """
        return f"{self.mongo_db}.{self.mongo_collection}"


def validate_settings() -> SecondBrainSettings:
    """Validate and return SecondBrain settings.

    Returns:
        Validated settings instance

    Raises:
        ValidationError: If configuration is invalid
    """
    return SecondBrainSettings()


def get_settings() -> SecondBrainSettings:
    """Get cached settings instance.

    Returns:
        Settings instance (cached)
    """
    from functools import lru_cache

    @lru_cache
    def _get_settings() -> SecondBrainSettings:
        return validate_settings()

    return _get_settings()
