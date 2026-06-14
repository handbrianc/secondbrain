"""Tests for domain interfaces to improve coverage."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from secondbrain.domain.interfaces import (
    DocumentConverter,
    EmbeddingGenerator,
    VectorStore,
)
from secondbrain.domain.entities import DocumentChunk, ChunkId, DocumentMetadata, SourcePath


class TestDocumentConverterProtocol:
    """Test DocumentConverter protocol."""

    def test_protocol_has_convert_method(self):
        """Test protocol defines convert method."""
        assert hasattr(DocumentConverter, 'convert')

    def test_protocol_has_supports_format_method(self):
        """Test protocol defines supports_format method."""
        assert hasattr(DocumentConverter, 'supports_format')

    def test_convert_returns_dict(self):
        """Test that a mock converter returns dict."""
        class MockConverter:
            def convert(self, file_path: Path) -> dict[str, str]:
                return {"1": "test content"}
            
            def supports_format(self, file_path: Path) -> bool:
                return True
        
        converter = MockConverter()
        result = converter.convert(Path("test.pdf"))
        
        assert isinstance(result, dict)
        assert "1" in result

    def test_supports_format_returns_bool(self):
        """Test that supports_format returns bool."""
        class MockConverter:
            def convert(self, file_path: Path) -> dict[str, str]:
                return {}
            
            def supports_format(self, file_path: Path) -> bool:
                return True
        
        converter = MockConverter()
        result = converter.supports_format(Path("test.pdf"))
        
        assert isinstance(result, bool)


class TestEmbeddingGeneratorProtocol:
    """Test EmbeddingGenerator protocol."""

    def test_protocol_has_generate_method(self):
        """Test protocol defines generate method."""
        assert hasattr(EmbeddingGenerator, 'generate')

    def test_protocol_has_generate_batch_method(self):
        """Test protocol defines generate_batch method."""
        assert hasattr(EmbeddingGenerator, 'generate_batch')

    def test_protocol_has_dimensions_property(self):
        """Test protocol defines dimensions property."""
        assert hasattr(EmbeddingGenerator, 'dimensions')

    def test_generate_returns_list(self):
        """Test generate returns list of floats."""
        class MockEmbedder:
            def generate(self, text: str) -> list[float]:
                return [0.1, 0.2, 0.3]
            
            def generate_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.1, 0.2, 0.3]]
            
            @property
            def dimensions(self) -> int:
                return 3
        
        embedder = MockEmbedder()
        result = embedder.generate("test")
        
        assert isinstance(result, list)
        assert len(result) == 3

    def test_generate_batch_returns_list_of_lists(self):
        """Test generate_batch returns list of lists."""
        class MockEmbedder:
            def generate(self, text: str) -> list[float]:
                return [0.1, 0.2, 0.3]
            
            def generate_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            
            @property
            def dimensions(self) -> int:
                return 3
        
        embedder = MockEmbedder()
        result = embedder.generate_batch(["test1", "test2"])
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], list)

    def test_dimensions_property_returns_int(self):
        """Test dimensions property returns int."""
        class MockEmbedder:
            def generate(self, text: str) -> list[float]:
                return [0.1, 0.2, 0.3]
            
            def generate_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.1, 0.2, 0.3]]
            
            @property
            def dimensions(self) -> int:
                return 3
        
        embedder = MockEmbedder()
        result = embedder.dimensions
        
        assert isinstance(result, int)
        assert result == 3


class TestVectorStoreProtocol:
    """Test VectorStore protocol."""

    def test_protocol_has_store_method(self):
        """Test protocol defines store method."""
        assert hasattr(VectorStore, 'store')

    def test_protocol_has_store_batch_method(self):
        """Test protocol defines store_batch method."""
        assert hasattr(VectorStore, 'store_batch')

    def test_protocol_has_search_method(self):
        """Test protocol defines search method."""
        assert hasattr(VectorStore, 'search')

    def test_protocol_has_delete_by_source_method(self):
        """Test protocol defines delete_by_source method."""
        assert hasattr(VectorStore, 'delete_by_source')

    def test_protocol_has_delete_all_method(self):
        """Test protocol defines delete_all method."""
        assert hasattr(VectorStore, 'delete_all')

    def test_store_returns_string_id(self):
        """Test that store method returns a string ID."""
        class MockStore:
            def store(self, chunk: DocumentChunk) -> str:
                return "chunk-id-123"
            
            def store_batch(self, chunks: list[DocumentChunk]) -> int:
                return 1
            
            def search(
                self,
                embedding: list[float],
                top_k: int = 5,
                _source_filter: str | None = None  # noqa: F841,
            ) -> Sequence[DocumentChunk]:
                return []
            
            def delete_by_source(self, source: str) -> int:
                return 0
            
            def delete_all(self) -> int:
                return 0
        
        store = MockStore()
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="Test content",
            metadata=DocumentMetadata(
                source_file=SourcePath(Path("test.pdf")),
                file_type="pdf",
                ingested_at=datetime.now(),
            ),
            page_number=1,
        )
        
        result = store.store(chunk)
        assert isinstance(result, str)
        assert result == "chunk-id-123"

    def test_search_returns_sequence_of_chunks(self):
        """Test that search method returns a sequence of chunks."""
        from collections.abc import Sequence
        
        class MockStore:
            def store(self, chunk: DocumentChunk) -> str:
                return "id1"
            
            def store_batch(self, chunks: list[DocumentChunk]) -> int:
                return 1
            
            def search(
                self,
                embedding: list[float],
                top_k: int = 5,
                source_filter: str | None = None,
            ) -> Sequence[DocumentChunk]:
                chunk1 = DocumentChunk(
                    chunk_id=ChunkId("chunk-1"),
                    text="Similar content 1",
                    metadata=DocumentMetadata(
                        source_file=SourcePath(Path("test.pdf")),
                        file_type="pdf",
                        ingested_at=datetime.now(),
                    ),
                    page_number=1,
                )
                chunk2 = DocumentChunk(
                    chunk_id=ChunkId("chunk-2"),
                    text="Similar content 2",
                    metadata=DocumentMetadata(
                        source_file=SourcePath(Path("test.pdf")),
                        file_type="pdf",
                        ingested_at=datetime.now(),
                    ),
                    page_number=2,
                )
                return [chunk1, chunk2]
            
            def delete_by_source(self, source: str) -> int:
                return 0
            
            def delete_all(self) -> int:
                return 0
        
        store = MockStore()
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = store.search(query_embedding, top_k=2, source_filter="test.pdf")
        
        assert isinstance(result, Sequence)
        assert len(result) == 2
        assert result[0].chunk_id == "chunk-1"
        assert result[1].chunk_id == "chunk-2"
        assert result[0].text == "Similar content 1"


class TestDocumentChunkCreation:
    """Test DocumentChunk entity creation."""

    def test_create_chunk_with_minimal_fields(self):
        """Test creating chunk with minimal fields."""
        metadata = DocumentMetadata(
            source_file=SourcePath(Path("test.pdf")),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="Test content",
            metadata=metadata,
            page_number=1,
        )
        
        # ChunkId is a NewType(str), so it's just a string
        assert chunk.chunk_id == "test-id"
        assert chunk.text == "Test content"
        assert chunk.page_number == 1

    def test_create_chunk_with_all_fields(self):
        """Test creating chunk with all fields."""
        metadata = DocumentMetadata(
            source_file=SourcePath(Path("test.pdf")),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        chunk = DocumentChunk(
            chunk_id=ChunkId("test-id"),
            text="Test content",
            metadata=metadata,
            page_number=1,
            embedding=[0.1, 0.2, 0.3],
        )
        
        assert chunk.chunk_id == "test-id"
        assert chunk.page_number == 1
        assert chunk.embedding == [0.1, 0.2, 0.3]

    def test_chunk_text_cannot_be_empty(self):
        """Test that empty text raises ValueError."""
        metadata = DocumentMetadata(
            source_file=SourcePath(Path("test.pdf")),
            file_type="pdf",
            ingested_at=datetime.now(),
        )
        with pytest.raises(ValueError, match="cannot be empty"):
            DocumentChunk(
                chunk_id=ChunkId("test-id"),
                text="",
                metadata=metadata,
            )
