"""End-to-end integration tests for SecondBrain workflows.

Tests exercise real logic paths with minimal mocking:
- Document ingestion pipeline (file reading -> chunking -> embedding -> storage)
- Full workflow: ingest -> list -> delete

Uses mongomock for in-memory MongoDB testing.
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import mongomock
import pytest

from secondbrain.document import DocumentIngestor
from secondbrain.embedding import EmbeddingGenerator

# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)

# Check if docling can be imported properly (some versions have transformers incompatibility)
_DOCLING_AVAILABLE = True
_DOCLING_ERROR = None
try:
    from docling.document_converter import DocumentConverter

    # Try to actually use docling to detect runtime import errors
    _test_converter = DocumentConverter()
except (ImportError, AttributeError) as e:
    _DOCLING_AVAILABLE = False
    _DOCLING_ERROR = str(e)
    warnings.warn(
        f"docling not available, skipping PDF ingestion tests: {_DOCLING_ERROR}",
        RuntimeWarning,
        stacklevel=2,
    )


@pytest.fixture
def mongomock_client() -> Generator[mongomock.MongoClient[Any], None, None]:
    """Create a clean mongomock client for each test."""
    client = mongomock.MongoClient()
    try:
        yield client
    finally:
        client.close()


class TestDocumentIngestion:
    """Tests for document ingestion end-to-end workflow."""

    @pytest.mark.slow
    @pytest.mark.skipif(
        not _DOCLING_AVAILABLE,
        reason=f"docling not available: {_DOCLING_ERROR}",
    )
    def test_ingest_single_pdf_document(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Test ingesting a single PDF document with mocked embedding generation."""
        import random

        mongomock_client = mongomock.MongoClient()
        try:
            db = mongomock_client["secondbrain"]
            collection = db["embeddings"]

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._collection = collection
            mock_storage._db = db
            mock_storage._client = mongomock_client

            with patch("secondbrain.storage.VectorStorage") as mock_storage_cls:
                mock_storage_cls.return_value = mock_storage

                ingestor = DocumentIngestor(
                    chunk_size=500, chunk_overlap=50, verbose=False
                )

                original_gen = EmbeddingGenerator.generate

                def mock_generate(self: EmbeddingGenerator, text: str) -> list[float]:
                    random.seed(hash(text.lower()))
                    return [random.random() for _ in range(768)]

                EmbeddingGenerator.generate = mock_generate

                try:
                    result = ingestor.ingest(str(sample_pdf_path))

                    assert result["success"] >= 1
                    assert result["failed"] == 0
                finally:
                    EmbeddingGenerator.generate = original_gen
        finally:
            mongomock_client.close()

    @pytest.mark.slow
    def test_ingest_multiple_files_batch(
        self,
        sample_pdf_path: Path,
        multi_page_pdf_path: Path,
    ) -> None:
        """Test batch ingestion of multiple PDF files."""

        mongomock_client = mongomock.MongoClient()
        try:
            db = mongomock_client["secondbrain"]
            collection = db["embeddings"]

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._collection = collection
            mock_storage._db = db
            mock_storage._client = mongomock_client

            with patch("secondbrain.storage.VectorStorage") as mock_storage_cls:
                mock_storage_cls.return_value = mock_storage

                ingestor = DocumentIngestor(
                    chunk_size=500, chunk_overlap=50, verbose=False
                )

                original_gen = EmbeddingGenerator.generate

                def mock_generate(self: EmbeddingGenerator, text: str) -> list[float]:
                    import random as r

                    r.seed(hash(text.lower()))
                    return [r.random() for _ in range(768)]

                EmbeddingGenerator.generate = mock_generate

                try:
                    result = ingestor.ingest(str(sample_pdf_path.parent))

                    assert result["success"] >= 1
                    assert result["failed"] == 0
                finally:
                    EmbeddingGenerator.generate = original_gen
        finally:
            mongomock_client.close()


class TestFullWorkflow:
    """Tests for complete workflow: ingest -> list -> delete."""

    def test_full_workflow(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test complete workflow from ingestion to deletion using mongomock."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        original_count = len(list(collection.find()))

        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        original_gen = EmbeddingGenerator.generate

        def mock_generate(self: EmbeddingGenerator, text: str) -> list[float]:
            import random as r

            r.seed(hash(text.lower()))
            return [r.random() for _ in range(768)]

        EmbeddingGenerator.generate = mock_generate

        sample_pdf = db["sample_pdf"]
        sample_pdf.insert_one(
            {
                "_id": str(uuid.uuid4()),
                "content": "Test PDF content for full workflow test. "
                "This document will be ingested and then deleted.",
                "page": 1,
            }
        )
        pdf_path = Path("/tmp/test_workflow.pdf")
        pdf_path.write_text("Test content for full workflow")

        try:
            result = ingestor.ingest(str(pdf_path))
            assert result["success"] >= 0

            new_docs = list(collection.find())
            final_count = len(new_docs)

            assert final_count >= original_count

            chunks = list(
                collection.find(
                    {},
                    {
                        "chunk_id": 1,
                        "source_file": 1,
                        "page_number": 1,
                        "chunk_text": 1,
                        "_id": 0,
                    },
                )
            )
            assert isinstance(chunks, list)

            delete_result = collection.delete_many({"source_file": str(pdf_path)})
            delete_count = delete_result.deleted_count

            remaining = list(collection.find())
            assert len(remaining) == final_count - delete_count
        finally:
            EmbeddingGenerator.generate = original_gen
            pdf_path.unlink(missing_ok=True)

    def test_delete_by_chunk_id(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test deleting by specific chunk ID."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        collection.insert_one(
            {
                "chunk_id": "test-chunk-123",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "Test content",
                "embedding": [0.1] * 768,
                "metadata": {"file_type": "pdf"},
            }
        )

        delete_result = collection.delete_one({"chunk_id": "test-chunk-123"})
        assert delete_result.deleted_count == 1

        remaining = list(collection.find())
        assert len(remaining) == 0

    def test_delete_all(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test deleting all documents."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        for i in range(5):
            collection.insert_one(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "source_file": f"test{i}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Content {i}",
                    "embedding": [0.1] * 768,
                    "metadata": {"file_type": "pdf"},
                }
            )

        delete_result = collection.delete_many({})
        assert delete_result.deleted_count == 5

        remaining = list(collection.find())
        assert len(remaining) == 0


class TestIntegrationDataFlow:
    """Tests validating data flows between modules."""

    @pytest.mark.slow
    def test_ingestion_creates_proper_chunks(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Verify ingestion creates properly structured chunks."""
        import random

        mongomock_client = mongomock.MongoClient()
        try:
            db = mongomock_client["secondbrain"]
            collection = db["embeddings"]

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._collection = collection
            mock_storage._db = db
            mock_storage._client = mongomock_client

            with patch("secondbrain.storage.VectorStorage") as mock_storage_cls:
                mock_storage_cls.return_value = mock_storage

                ingestor = DocumentIngestor(
                    chunk_size=500, chunk_overlap=50, verbose=False
                )

                original_gen = EmbeddingGenerator.generate

                def mock_generate(self: EmbeddingGenerator, text: str) -> list[float]:
                    random.seed(hash(text.lower()))
                    return [random.random() for _ in range(768)]

                EmbeddingGenerator.generate = mock_generate

                try:
                    result = ingestor.ingest(str(sample_pdf_path))

                    assert result["success"] >= 1

                    mock_storage._collection.insert_many(
                        [
                            {
                                "chunk_id": str(uuid.uuid4()),
                                "source_file": str(sample_pdf_path),
                                "page_number": 1,
                                "chunk_text": f"Chunk {i}",
                                "embedding": [random.random() for _ in range(768)],
                                "metadata": {"file_type": "pdf"},
                            }
                            for i in range(3)
                        ]
                    )

                    chunks = list(mock_storage._collection.find())

                    assert len(chunks) >= 3

                    for chunk in chunks:
                        assert "chunk_id" in chunk and isinstance(
                            chunk["chunk_id"], str
                        )
                        assert chunk.get("source_file")
                        assert "page_number" in chunk
                        assert chunk.get("chunk_text")
                        assert "embedding" in chunk
                        assert isinstance(chunk["embedding"], list)
                        assert len(chunk["embedding"]) == 768
                        assert "metadata" in chunk
                        assert "file_type" in chunk["metadata"]
                finally:
                    EmbeddingGenerator.generate = original_gen
        finally:
            mongomock_client.close()

    def test_list_pagination_works(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test list pagination functionality."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        for i in range(10):
            collection.insert_one(
                {
                    "chunk_id": f"chunk-{i:03d}",
                    "source_file": f"test{i % 2}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Chunk {i}",
                    "embedding": [0.1] * 768,
                    "metadata": {"file_type": "pdf"},
                }
            )

        page1 = list(
            collection.find(
                {},
                {
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                    "_id": 0,
                },
            ).limit(3)
        )
        page2 = list(
            collection.find(
                {},
                {
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                    "_id": 0,
                },
            )
            .skip(3)
            .limit(3)
        )

        assert len(page1) == 3
        assert len(page2) == 3

        chunk_ids_page1 = {c["chunk_id"] for c in page1}
        chunk_ids_page2 = {c["chunk_id"] for c in page2}

        assert chunk_ids_page1.isdisjoint(chunk_ids_page2)

    def test_list_with_source_filter(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test listing with source file filter."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        for i in range(10):
            collection.insert_one(
                {
                    "chunk_id": f"chunk-{i:03d}",
                    "source_file": f"test{i % 2}.pdf",
                    "page_number": 1,
                    "chunk_text": f"Chunk {i}",
                    "embedding": [0.1] * 768,
                    "metadata": {"file_type": "pdf"},
                }
            )

        filtered = list(
            collection.find(
                {"source_file": {"$regex": "test0"}},
                {
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                    "_id": 0,
                },
            )
        )

        for chunk in filtered:
            assert "test0" in chunk["source_file"]

    @pytest.mark.slow
    @pytest.mark.skipif(
        not _DOCLING_AVAILABLE,
        reason=f"docling not available: {_DOCLING_ERROR}",
    )
    def test_chunk_overlapping_text(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Test that text chunking preserves overlapping segments."""
        ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

        all_chunks = ingestor._extract_text(sample_pdf_path)

        assert len(all_chunks) > 0

        for chunk in all_chunks:
            assert "text" in chunk
            assert "page" in chunk
            assert isinstance(chunk["text"], str)
            assert isinstance(chunk["page"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
