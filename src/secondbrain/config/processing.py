"""Ingestion, storage, rate limiting, and multicore settings fragment."""

from pydantic import Field, field_validator


class ProcessingStorageMixin:
    """Ingestion, storage, rate limiting, and multicore settings."""

    max_file_size_bytes: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file size in bytes (default: 100MB)",
    )
    index_ready_retry_count: int = Field(
        default=15,
        description="Max retries for index ready check (exponential backoff)",
    )
    index_ready_retry_delay: float = Field(
        default=1.0,
        description="Initial delay for index ready retries",
    )
    rate_limit_max_requests: int = Field(
        default=10,
        description="Maximum requests per rate limit window",
    )
    rate_limit_window_seconds: float = Field(
        default=1.0,
        description="Rate limit window in seconds",
    )
    connection_cache_ttl: float = Field(
        default=60.0,
        description="TTL for connection validation cache in seconds",
    )
    max_workers: int | None = Field(
        default=None,
        description="Maximum number of worker processes for parallel processing (default: auto-detect CPU count)",
    )
    ingest_pool: str = Field(
        default="process",
        description="Pool type for CPU-bound extraction: 'process' (multicore, default) or 'thread'",
    )

    @field_validator("ingest_pool")
    @classmethod
    def validate_ingest_pool(cls, v: str) -> str:
        """Validate ingest pool is one of 'process' or 'thread'."""
        if v not in {"process", "thread"}:
            raise ValueError("ingest_pool must be one of {'process', 'thread'}")
        return v

    skip_existing_on_reingest: bool = Field(
        default=True,
        description=(
            "Skip re-embedding and re-storing chunks whose text_hash already "
            "exists in storage when ingesting already-ingested content"
        ),
    )
    streaming_enabled: bool = Field(
        default=True,
        description="Enable streaming processing for memory efficiency (default: true)",
    )
    streaming_chunk_batch_size: int = Field(
        default=100,
        description="Number of chunks to process per streaming batch (1-200, default: 100)",
    )

    @field_validator("streaming_chunk_batch_size")
    @classmethod
    def validate_streaming_chunk_batch_size(cls, v: int) -> int:
        """Validate streaming chunk batch size is between 1 and 200."""
        if v <= 0 or v > 200:
            raise ValueError("streaming_chunk_batch_size must be between 1 and 200")
        return v

    storage_compression_enabled: bool = Field(
        default=True,
        description="Enable MongoDB collection-level compression (zstd)",
    )
    embedding_dtype: str = Field(
        default="float32",
        description="Embedding data type: 'float32' (50% smaller) or 'float64'",
    )
    embedding_storage_format: str = Field(
        default="array",
        description=(
            "Embedding storage format: 'array' (required for vector search) or 'binary' "
            "(DEPRECATED and INCOMPATIBLE with vector search)"
        ),
    )
    text_compression_enabled: bool = Field(
        default=False,
        description="Enable text compression for chunk_text (gzip/brotli)",
    )
    pdf_ocr_enabled: bool = Field(
        default=False,
        description=(
            "Run OCR on PDFs. False = OCR only when the PDF has no embedded "
            "text layer (scanned). Set True to always OCR all PDFs."
        ),
    )
    pdf_table_structure_enabled: bool = Field(
        default=True,
        description="Detect table structure in PDFs.",
    )
    text_compression_algorithm: str = Field(
        default="gzip",
        description="Text compression algorithm: 'gzip', 'brotli', or 'zstd'",
    )
