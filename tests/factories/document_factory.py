"""Factory for creating test DocumentMetadata and DocumentChunk objects."""

from factory import Factory, Faker, LazyAttribute, Sequence, SubFactory

from secondbrain.domain.entities import DocumentChunk, DocumentMetadata
from secondbrain.domain.value_objects import ChunkId


def _get_default_embedding() -> list[float]:
    """Get default embedding vector sized to match config's embedding_dimensions."""
    from secondbrain.config import config

    return [0.1] * config().embedding_dimensions


class DocumentMetadataFactory(Factory):
    """Factory for creating test DocumentMetadata objects.

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

    class Meta:
        model = DocumentMetadata

    source_file = Faker("file_path")
    file_type = Faker("file_extension")
    ingested_at = Faker("date_time_this_year")
    chunk_count = Faker("random_int", min=1, max=10)
    total_chars = Faker("random_int", min=100, max=10000)


class DocumentChunkFactory(Factory):
    """Factory for creating test DocumentChunk objects.

    Provides flexible document chunk creation for tests with realistic fake data.

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

    class Meta:
        model = DocumentChunk

    chunk_id = Sequence(lambda n: ChunkId(f"chunk_{n:04d}"))
    text = Faker("paragraph")
    page_number = None
    metadata = SubFactory(DocumentMetadataFactory)
    embedding = LazyAttribute(lambda _: _get_default_embedding())
