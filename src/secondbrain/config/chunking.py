"""Chunking and summarization settings fragment."""

from typing import Literal

from pydantic import Field, field_validator


class ChunkingSummarizerMixin:
    """Chunking, summarization, and ingestion settings."""

    chunk_size: int = Field(
        default=4096,
        description="Chunk size for document splitting",
    )

    @field_validator("chunk_size")
    @classmethod
    def validate_chunk_size(cls, v: int) -> int:
        """Validate chunk size is positive."""
        if v <= 0:
            raise ValueError("chunk_size must be positive")
        return v

    chunk_overlap: int = Field(
        default=50,
        description="Chunk overlap for splitting",
    )

    @field_validator("chunk_overlap")
    @classmethod
    def validate_chunk_overlap(cls, v: int) -> int:
        """Validate chunk overlap is non-negative."""
        if v < 0:
            raise ValueError("chunk_overlap must be non-negative")
        return v

    summarizer_mode: Literal["concise", "detailed", "chapter_only"] = Field(
        default="concise",
        description=(
            "Summarization approach: 'concise' (brief), 'detailed' (comprehensive), "
            "or 'chapter_only' (structure only)"
        ),
    )
    summary_depth: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Max heading depth to traverse for chapter summaries",
    )
    adaptive_chunking: bool = Field(
        default=False,
        description="Enable adaptive chunk sizing based on content density",
    )
    supported_extensions: str = Field(
        default="pdf,docx,pptx,xlsx,html,htm,md,txt,asciidoc,adoc,tex,csv,"
        "png,jpg,jpeg,tiff,tif,bmp,webp,wav,mp3,vtt,xml,json",
        description="Comma-separated list of supported file extensions (without dots)",
    )
