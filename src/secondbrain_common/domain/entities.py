"""Domain entities for the SecondBrain system.

Entities are objects with identity that persist over time. They represent
core business concepts like documents and chunks.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from secondbrain.domain.value_objects import ChunkId, EmbeddingVector, SourcePath


@dataclass(frozen=True)
class DocumentMetadata:
    """Immutable metadata for a processed document.

    Attributes
    ----------
    source_file : SourcePath
        Original file path where document was ingested
    file_type : str
        File type category (e.g., 'pdf', 'docx', 'markdown')
    ingested_at : datetime
        Timestamp when document was ingested
    chunk_count : int
        Number of chunks this document was split into
    total_chars : int
        Total character count across all chunks
    """

    source_file: SourcePath
    file_type: str
    ingested_at: datetime
    chunk_count: int = 0
    total_chars: int = 0

    def __post_init__(self) -> None:
        """Validate required metadata fields."""
        if not self.source_file:
            raise ValueError("Source file cannot be empty")
        if not self.file_type:
            raise ValueError("File type cannot be empty")


@dataclass
class DocumentChunk:
    """A chunk of text from a processed document.

    This is the primary entity for semantic search. Each chunk has a unique
    ID and is associated with metadata about its source document.

    Attributes
    ----------
    chunk_id : ChunkId
        Unique identifier for this chunk
    text : str
        The chunk text content
    page_number : int | None
        Page number in source document (if applicable)
    metadata : DocumentMetadata
        Reference to parent document metadata
    embedding : EmbeddingVector | None
        Vector embedding for semantic search (lazy-loaded)
    """

    chunk_id: ChunkId
    text: str
    metadata: DocumentMetadata
    page_number: int | None = None
    embedding: EmbeddingVector | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate chunk text and ID are non-empty."""
        if not self.text.strip():
            raise ValueError("Chunk text cannot be empty")
        if not self.chunk_id:
            raise ValueError("Chunk ID cannot be empty")

    @property
    def char_count(self) -> int:
        """Character count of this chunk."""
        return len(self.text)

    @property
    def word_count(self) -> int:
        """Word count of this chunk."""
        return len(self.text.split())

    def has_embedding(self) -> bool:
        """Check if chunk has an embedding vector."""
        return self.embedding is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage.

        Returns
        -------
        dict[str, Any]
            Dictionary representation suitable for MongoDB storage
        """
        return {
            "chunk_id": self.chunk_id,
            "chunk_text": self.text,
            "page_number": self.page_number,
            "source_file": self.metadata.source_file,
            "file_type": self.metadata.file_type,
            "ingested_at": self.metadata.ingested_at.isoformat(),
            "embedding": self.embedding,
        }
