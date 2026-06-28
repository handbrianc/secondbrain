"""Configuration management for secondbrain CLI using Pydantic Settings.

This module provides a Config class that loads configuration from environment
variables following 12-factor app principles, with validation for MongoDB
connection strings.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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
            with open(env_file_path, encoding="utf-8") as f:
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

    # MongoDB settings
    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection URI (without credentials - set via environment variable for production)",
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

    llm_provider: str = Field(
        default="openai",
        description="LLM provider type (openai, anthropic)",
    )
    openai_base_url: str | None = Field(
        default=None,
        description="OpenAI-compatible API base URL (optional, defaults to OpenAI). Use for self-hosted endpoints like vLLM, LM Studio, Azure OpenAI, Groq, etc.",
    )
    openai_api_key: str | None = Field(
        default=None,
        description="OpenAI-compatible API key (optional for self-hosted endpoints without auth). Defaults to SECONDBRAIN_OPENAI_API_KEY env var.",
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        description="Default LLM model for RAG",
    )
    llm_temperature: float = Field(
        default=0.1,
        description="LLM generation temperature (0.0-2.0)",
    )
    llm_max_tokens: int = Field(
        default=2048,
        description="Maximum tokens for LLM responses",
    )
    llm_timeout: int = Field(
        default=120,
        description="Request timeout in seconds for LLM",
    )
    rag_context_window: int = Field(
        default=5,
        description="Number of recent messages to keep in context (default: 5 per spec)",
    )
    rag_max_retries: int = Field(
        default=3,
        ge=1,
        description="Maximum retry attempts for LLM generation in RAG chat (default: 3)",
    )

    # RAG formatting settings
    rag_max_context_chars: int = Field(
        default=8000,
        ge=1000,
        le=500000,
        description=(
            "Maximum total context length in characters for RAG prompt construction. "
            "Controls how much retrieved document text is included in the LLM prompt. "
            "Defaults to 8000 (appropriate for 8k-context models). Increase for "
            "longer-context models (e.g., 32000 for claude-3-5 Sonnet)."
        ),
    )
    rag_chunk_preview_chars: int = Field(
        default=500,
        ge=100,
        le=10000,
        description=(
            "Maximum character length of each individual chunk's text in the RAG context. "
            "Chunks longer than this are truncated to prevent any single chunk from "
            "dominating the context window. Defaults to 500."
        ),
    )

    # RAG prompt settings
    rag_system_prompt: str = Field(
        default=(
            "You are a helpful assistant. You MUST answer based ONLY on the provided context below.\n"
            "\n"
            "IMPORTANT RULES:\n"
            "1. The context contains information from documents. Read it carefully.\n"
            "2. Extract and synthesize the answer from the context - do NOT say you 'cannot find' information that IS in the context.\n"
            "3. If you see the answer in the context, state it clearly and confidently.\n"
            "4. Only say 'I cannot find the answer' if you have thoroughly searched the entire context and the information is genuinely absent.\n"
            "5. Do not hallucinate or make up information - stick to what's in the context.\n"
            "6. When the question asks for a list (formats, features, components, options, etc.), extract ALL items from the context - don't miss any.\n"
            "7. Read ALL chunks in the context - important information might be in any of them.\n"
            "8. For questions about system architecture or components, list the SPECIFIC component names mentioned in the context (e.g., 'CLI Interface', 'Ingestor', 'Embedding Engine', not just 'Components').\n"
            "9. When the question asks for a SPECIFIC VALUE (like a model name, version number, configuration value, etc.), you MUST include the exact value from the context in your answer.\n"
            "10. NEVER generalize or omit specific values - if the context says 'all-MiniLM-L6-v2', your answer must include 'all-MiniLM-L6-v2'.\n"
            "11. Format your answer concisely and directly, matching the style of the question.\n"
            "\n"
            "When the answer is in the context:\n"
            "- State the answer directly in 1-2 sentences\n"
            "- For lists: include ALL items mentioned in the context with their full names\n"
            "- For specific values: include the EXACT value from the context\n"
            "- Be concise - avoid unnecessary elaboration\n"
            "- Cite the source if helpful (e.g., 'According to the document...')\n"
            "\n"
            "The context from documents follows:\n"
        ),
        description="System prompt for RAG chat (supports environment variable SECONDBRAIN_RAG_SYSTEM_PROMPT)",
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
        default=20,
        description="Default number of search results (higher = more context for better answers)",
    )

    # Embedding settings
    embedding_provider: str = Field(
        default="openai",
        description="Embedding provider type (openai, or any OpenAI-compatible API)",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description=(
            "Embedding model name. For OpenAI: 'text-embedding-3-small', 'text-embedding-3-large', "
            "'text-embedding-ada-002'. For OpenAI-compatible providers (Ollama, LM Studio, vLLM): "
            "use the model name configured in the server (e.g., 'mxbai-embed-large', 'all-MiniLM-L6-v2')."
        ),
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
        description=(
            "Dimensionality of embedding vectors (must match model). "
            "1536 = OpenAI text-embedding-3-small default. "
            "Other common sizes: 384, 768, 1024, 3072 depending on provider/model."
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
            "Adjust based on your embedding provider's rate limits. "
            "10 req/s = 600 req/min, sufficient for typical batch processing."
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

    # Storage optimization settings
    storage_compression_enabled: bool = Field(
        default=True,
        description="Enable MongoDB collection-level compression (zstd). Reduces storage by 40-60%.",
    )

    embedding_dtype: str = Field(
        default="float32",
        description="Embedding data type: 'float32' (50% smaller) or 'float64' (default MongoDB). float32 recommended for most use cases.",
    )

    embedding_storage_format: str = Field(
        default="array",
        description=(
            "Embedding storage format: 'array' (JSON array, required for vector search) or "
            "'binary' (BSON Binary, DEPRECATED and INCOMPATIBLE with vector search - "
            "cosine similarity computations will produce incorrect results. "
            "Supported for backward compatibility only. Default: 'array'."
        ),
    )

    text_compression_enabled: bool = Field(
        default=False,
        description="Enable text compression for chunk_text (gzip/brotli). Opt-in initially, reduces text storage by 60-80%.",
    )

    text_compression_algorithm: str = Field(
        default="gzip",
        description="Text compression algorithm: 'gzip', 'brotli', or 'zstd'. gzip is fastest, brotli has best ratio.",
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

    @field_validator("llm_temperature")
    @classmethod
    def validate_llm_temperature(cls, v: float) -> float:
        """Validate LLM temperature is between 0.0 and 2.0.

        Args:
            v: Temperature value to validate.

        Returns
        -------
            Validated temperature value.

        Raises
        ------
            ValueError: If temperature is not in range [0.0, 2.0].
        """
        if v < 0.0 or v > 2.0:
            raise ValueError("llm_temperature must be between 0.0 and 2.0")
        return v

    @field_validator("llm_max_tokens")
    @classmethod
    def validate_llm_max_tokens(cls, v: int) -> int:
        """Validate LLM max tokens is positive.

        Args:
            v: Max tokens value to validate.

        Returns
        -------
            Validated max tokens value.

        Raises
        ------
            ValueError: If max tokens is not positive.
        """
        if v <= 0:
            raise ValueError("llm_max_tokens must be positive")
        return v

    @field_validator("llm_timeout")
    @classmethod
    def validate_llm_timeout(cls, v: int) -> int:
        """Validate LLM timeout is positive.

        Args:
            v: Timeout value to validate.

        Returns
        -------
            Validated timeout value.

        Raises
        ------
            ValueError: If timeout is not positive.
        """
        if v <= 0:
            raise ValueError("llm_timeout must be positive")
        return v

    @field_validator("rag_context_window")
    @classmethod
    def validate_rag_context_window(cls, v: int) -> int:
        """Validate RAG context window is positive.

        Args:
            v: Context window value to validate.

        Returns
        -------
            Validated context window value.

        Raises
        ------
            ValueError: If context window is not positive.
        """
        if v <= 0:
            raise ValueError("rag_context_window must be positive")
        return v

    @field_validator("rag_max_context_chars")
    @classmethod
    def validate_rag_max_context_chars(cls, v: int) -> int:
        if v < 1000 or v > 500000:
            raise ValueError("rag_max_context_chars must be between 1000 and 500000")
        return v

    @field_validator("rag_chunk_preview_chars")
    @classmethod
    def validate_rag_chunk_preview_chars(cls, v: int) -> int:
        if v < 100 or v > 10000:
            raise ValueError("rag_chunk_preview_chars must be between 100 and 10000")
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
            import warnings

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
