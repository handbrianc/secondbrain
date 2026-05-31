"""Factory for creating test Chunk objects."""

from factory import Faker, Sequence, Factory, SubFactory, LazyAttribute
from secondbrain.domain.entities import DocumentChunk, DocumentMetadata
from secondbrain.domain.value_objects import ChunkId, EmbeddingVector, SourcePath

from .document_factory import DocumentMetadataFactory


class ChunkFactory(Factory):
    """Factory for creating test Chunk (DocumentChunk) objects.

    Provides flexible chunk creation for tests with realistic fake data.
    Default embedding is [0.1] * 384 as specified.

    Attributes
    ----------
    id : ChunkId
        Unique chunk identifier (auto-generated)
    document_id : str
        Associated document identifier
    page_number : int
        Page number in source document
    content : str
        Chunk text content
    embedding : EmbeddingVector
        Vector embedding for semantic search (default: [0.1] * 384)
    metadata : DocumentMetadata
        Parent document metadata
    """

    class Meta:
        model = DocumentChunk

    chunk_id = Sequence(lambda n: ChunkId(f"chunk_{n:04d}"))
    text = Faker("paragraph")
    page_number = Faker("random_int", min=1, max=10)
    metadata = SubFactory(DocumentMetadataFactory)
    embedding = LazyAttribute(lambda _: EmbeddingVector([0.1] * 384))

    document_id = Faker("uuid4")

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Create a chunk with document_id in metadata if provided."""
        document_id = kwargs.pop("document_id", None)
        
        # Ensure metadata has document reference
        if document_id and "metadata" not in kwargs:
            kwargs["metadata"] = DocumentMetadata(
                source_file=SourcePath(f"/test/docs/{document_id}.pdf"),
                file_type="pdf",
                ingested_at=Faker("date_time_this_year").generate({}),
            )
        
        return model_class(*args, **kwargs)
