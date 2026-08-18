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
        default=False,
        description="Detect table structure in PDFs.",
    )
    pdf_table_fast_mode: bool = Field(
        default=True,
        description=(
            "When table structure is enabled, use TableFormer 'fast' mode "
            "instead of the slower, more accurate mode."
        ),
    )
    pdf_table_cell_matching: bool = Field(
        default=False,
        description=(
            "Enable docling table cell matching (post-processing). Disabled "
            "by default for speed and OCR compatibility."
        ),
    )
    pdf_accelerator_device: str = Field(
        default="auto",
        description="Docling accelerator device: 'auto' | 'cpu' | 'mps' | 'cuda'.",
    )
    pdf_num_threads: int = Field(
        default=4,
        description="Threads for docling inference.",
    )
    max_ingest_processes: int = Field(
        default=0,
        description=(
            "Cap on AUTO-detected process-pool workers (0 = unlimited/auto). "
            "Explicit --cores or configured max_workers always win."
        ),
    )
    pdf_threaded_pipeline: bool = Field(
        default=False,
        description=(
            "Use docling's threaded/batched PDF pipeline (ThreadedPdfPipelineOptions) "
            "instead of the default."
        ),
    )
    pdf_layout_batch_size: int = Field(
        default=4,
        description=(
            "Layout-model batch size for the threaded pipeline (used only when "
            "pdf_threaded_pipeline is true)."
        ),
    )
    pdf_generate_page_images: bool = Field(
        default=False,
        description=(
            "Render full-page images during parsing (unused for storage; disabled for speed)."
        ),
    )
    pdf_generate_picture_images: bool = Field(
        default=False,
        description=(
            "Render embedded picture images during parsing (unused for storage; "
            "disabled for speed)."
        ),
    )
    pdf_images_scale: float = Field(
        default=1.0,
        description="Rendering scale for generated images.",
    )

    @field_validator("pdf_accelerator_device")
    @classmethod
    def validate_pdf_accelerator_device(cls, v: str) -> str:
        """Validate the accelerator device is one of the supported values."""
        if v not in {"auto", "cpu", "mps", "cuda"}:
            raise ValueError(
                "pdf_accelerator_device must be one of {'auto', 'cpu', 'mps', 'cuda'}"
            )
        return v

    @field_validator("pdf_num_threads")
    @classmethod
    def validate_pdf_num_threads(cls, v: int) -> int:
        """Validate docling inference thread count is at least 1."""
        if v < 1:
            raise ValueError("pdf_num_threads must be >= 1")
        return v

    @field_validator("max_ingest_processes")
    @classmethod
    def validate_max_ingest_processes(cls, v: int) -> int:
        """Validate the auto-detect worker cap is non-negative."""
        if v < 0:
            raise ValueError("max_ingest_processes must be >= 0")
        return v

    @field_validator("pdf_layout_batch_size")
    @classmethod
    def validate_pdf_layout_batch_size(cls, v: int) -> int:
        """Validate the threaded-pipeline layout batch size is at least 1."""
        if v < 1:
            raise ValueError("pdf_layout_batch_size must be >= 1")
        return v

    @field_validator("pdf_images_scale")
    @classmethod
    def validate_pdf_images_scale(cls, v: float) -> float:
        """Validate the generated-image rendering scale is positive."""
        if v <= 0:
            raise ValueError("pdf_images_scale must be > 0")
        return v

    text_compression_algorithm: str = Field(
        default="gzip",
        description="Text compression algorithm: 'gzip', 'brotli', or 'zstd'",
    )
