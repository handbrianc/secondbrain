"""Tests for domain entities."""

import dataclasses
from dataclasses import is_dataclass
from datetime import datetime

import pytest

from secondbrain.domain.entities import DocumentChunk, DocumentMetadata
from secondbrain.domain.value_objects import ChunkId, SourcePath


class TestDocumentMetadataValidation:
    def test_source_file_required(self) -> None:
        with pytest.raises(ValueError, match="Source file cannot be empty"):
            DocumentMetadata(
                source_file=SourcePath(""),
                file_type="pdf",
                ingested_at=datetime.now(),
            )

    def test_file_type_required(self) -> None:
        with pytest.raises(ValueError, match="File type cannot be empty"):
            DocumentMetadata(
                source_file=SourcePath("/test/file.pdf"),
                file_type="",
                ingested_at=datetime.now(),
            )

    def test_dataclass_validation(self) -> None:
        # Valid metadata should work
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        assert metadata.source_file == SourcePath("/test/file.pdf")
        assert metadata.file_type == "pdf"


class TestDocumentMetadataDefaults:
    def test_optional_fields_default(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        assert metadata.chunk_count == 0
        assert metadata.total_chars == 0

    def test_metadata_dict_behavior(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
            chunk_count=5,
            total_chars=1000,
        )
        assert metadata.chunk_count == 5
        assert metadata.total_chars == 1000


class TestDocumentMetadataImmutability:
    def test_frozen_dataclass(self) -> None:
        assert is_dataclass(DocumentMetadata)

    def test_cannot_modify_after_creation(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        with pytest.raises(getattr(dataclasses, "FrozenInstanceError", TypeError)):
            metadata.chunk_count = 10  # type: ignore


class TestDocumentChunkValidation:
    def test_chunk_text_required(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        with pytest.raises(ValueError, match="Chunk text cannot be empty"):
            DocumentChunk(
                chunk_id=ChunkId("test-id"),
                text="",
                metadata=metadata,
            )

    def test_chunk_id_required(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        with pytest.raises(ValueError, match="Chunk ID cannot be empty"):
            DocumentChunk(
                chunk_id=ChunkId(""),
                text="test text",
                metadata=metadata,
            )

    def test_validation_errors(self) -> None:
        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        # Valid chunk should work
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=metadata,
        )
        assert chunk.text == "test text"


class TestDocumentChunkProperties:
    @pytest.fixture
    def sample_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )

    def test_char_count_calculation(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="Hello World",
            metadata=sample_metadata,
        )
        assert chunk.char_count == 11

    def test_word_count_calculation(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="Hello World This Is A Test",
            metadata=sample_metadata,
        )
        assert chunk.word_count == 6

    def test_accuracy(self, sample_metadata: DocumentMetadata) -> None:
        text = "The quick brown fox jumps over the lazy dog"
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text=text,
            metadata=sample_metadata,
        )
        assert chunk.char_count == len(text)
        assert chunk.word_count == len(text.split())


class TestDocumentChunkEmbeddingStatus:
    @pytest.fixture
    def sample_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )

    def test_has_embedding_with_none_vector(
        self, sample_metadata: DocumentMetadata
    ) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
            embedding=None,
        )
        assert chunk.has_embedding() is False

    def test_has_embedding_with_valid_vector(
        self, sample_metadata: DocumentMetadata
    ) -> None:
        from secondbrain.domain.value_objects import EmbeddingVector

        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
            embedding=EmbeddingVector([0.1, 0.2, 0.3]),
        )
        assert chunk.has_embedding() is True

    def test_boolean_logic(self, sample_metadata: DocumentMetadata) -> None:
        chunk_no_embedding = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
        )
        assert not chunk_no_embedding.has_embedding()

        from secondbrain.domain.value_objects import EmbeddingVector

        chunk_with_embedding = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
            embedding=EmbeddingVector([0.1] * 384),
        )
        assert chunk_with_embedding.has_embedding()


class TestDocumentChunkToDict:
    @pytest.fixture
    def sample_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )

    def test_serialization_to_storage_format(
        self, sample_metadata: DocumentMetadata
    ) -> None:
        from secondbrain.domain.value_objects import EmbeddingVector

        chunk = DocumentChunk(
            chunk_id=ChunkId("test-chunk-id"),
            text="test text content",
            metadata=sample_metadata,
            page_number=1,
            embedding=EmbeddingVector([0.1, 0.2, 0.3]),
        )
        result = chunk.to_dict()

        assert result["chunk_id"] == "test-chunk-id"
        assert result["chunk_text"] == "test text content"
        assert result["page_number"] == 1

    def test_all_fields_included(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test",
            metadata=sample_metadata,
        )
        result = chunk.to_dict()

        assert "chunk_id" in result
        assert "chunk_text" in result
        assert "page_number" in result
        assert "source_file" in result
        assert "file_type" in result
        assert "ingested_at" in result
        assert "embedding" in result

    def test_embedding_vector_serialization(
        self, sample_metadata: DocumentMetadata
    ) -> None:
        from secondbrain.domain.value_objects import EmbeddingVector

        embedding = EmbeddingVector([0.1, 0.2, 0.3, 0.4, 0.5])
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test",
            metadata=sample_metadata,
            embedding=embedding,
        )
        result = chunk.to_dict()

        assert result["embedding"] == embedding


class TestDocumentChunkPageNone:
    @pytest.fixture
    def sample_metadata(self) -> DocumentMetadata:
        return DocumentMetadata(
            source_file=SourcePath("/test/file.pdf"),
            file_type="pdf",
            ingested_at=datetime(2024, 1, 1, 12, 0, 0),
        )

    def test_chunk_without_page_number(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
            page_number=None,
        )
        assert chunk.page_number is None

    def test_page_num_none_handled(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
        )
        # Default is None
        assert chunk.page_number is None

    def test_serialization_with_none(self, sample_metadata: DocumentMetadata) -> None:
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="test text",
            metadata=sample_metadata,
            page_number=None,
        )
        result = chunk.to_dict()
        assert result["page_number"] is None
