"""Storage models and type definitions."""

from dataclasses import dataclass
from typing import TypedDict

from secondbrain.domain.entities import DocumentMetadata
from secondbrain.domain.value_objects import ChunkId, EmbeddingVector


class DatabaseStats(TypedDict):
    """Typed dictionary for database statistics.

    Attributes
    ----------
        total_chunks: Total number of chunks stored.
        unique_sources: Number of unique source files.
        database: Database name.
        collection: Collection name.
    """

    total_chunks: int
    unique_sources: int
    database: str
    collection: str


@dataclass(frozen=True)
class StorableDocument:
    """Frozen document representation for storage operations.

    Attributes
    ----------
        chunk_id: Unique identifier for this chunk.
        text: The chunk text content (stored as 'chunk_text' in MongoDB).
        embedding: Vector embedding for semantic search.
        metadata: Reference to parent document metadata.
        page_number: Page number in source document (if applicable).

    Note
    ----
        This is a frozen dataclass to ensure immutability of documents
        being stored. The 'magnitude' field is computed during preparation
        for storage and is not part of this type.
    """

    chunk_id: ChunkId
    text: str
    embedding: EmbeddingVector
    metadata: DocumentMetadata
    page_number: int | None = None
