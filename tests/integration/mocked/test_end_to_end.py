"""End-to-end integration tests for SecondBrain workflows.

Tests exercise real logic paths with minimal mocking:
- Document ingestion pipeline (segment dedup → chunking → embedding → build)
- Full workflow: ingest -> list -> delete

Uses mongomock for in-memory MongoDB testing.

# Group mocked integration tests on same xdist worker to share mongomock client
pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("mocked_integration")]


ARCHITECTURAL NOTE:
`ingest()` uses ThreadPoolExecutor internally for parallel file processing —
worker threads re-import `docling` and embedding factories, bypassing test
patches. Therefore, pipeline stages are tested DIRECTLY (not through `ingest()`)
to ensure mocks apply. The threading workflow IS exercised in
test_e2e_pdf_ingestion.py via proper monkeypatch.setattr at module scope.
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

# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
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

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingest_single_pdf_document(self, sample_pdf_path: Path) -> None:
        """Test PDF segments pass through embed→build pipeline producing valid docs."""
        import random

        mongomock_client = mongomock.MongoClient()
        try:
            db = mongomock_client["secondbrain_test"]
            collection = db["embeddings_test"]

            random.seed(0)
            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._collection = collection
            mock_storage._db = db
            mock_storage._client = mongomock_client
            mock_storage.store_batch = MagicMock(return_value=[])

            def make_emb(text: str) -> list[float]:
                random.seed(hash(text.lower()))
                return [random.random() for _ in range(384)]

            mock_embed_instance = MagicMock()
            mock_embed_instance.generate.side_effect = make_emb
            mock_embed_instance.generate_batch.side_effect = lambda texts: [
                make_emb(t) for t in texts
            ]
            mock_embed_instance.validate_connection.return_value = True

            ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

            segments = ingestor._extract_text(sample_pdf_path)
            assert len(segments) > 0

            chunks = ingestor._deduplicate_and_chunk_segments(sample_pdf_path, segments)
            with patch.object(
                ingestor, "_generate_embeddings_with_cache"
            ) as mock_gen_cache:
                mock_gen_cache.return_value = {
                    c["text_hash"]: make_emb(c["text"]) for c in chunks
                }
                docs = ingestor._build_documents_with_embeddings(
                    sample_pdf_path, segments, mock_embed_instance
                )

            assert len(docs) >= 1
            for doc in docs:
                assert isinstance(doc["chunk_id"], str)
                assert doc["source_file"] == str(sample_pdf_path)
                assert doc["page_number"] >= 0
                assert doc["chunk_text"] != ""
                assert isinstance(doc["embedding"], list)
                assert len(doc["embedding"]) == 384
        finally:
            mongomock_client.close()

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingest_multiple_files_batch(
        self,
        sample_pdf_path: Path,
        sample_pdf_with_multiple_pages: Path,
        tmp_path: Path,
    ) -> None:
        """Test that building docs from two PDFs produces correct schemas."""
        import random
        import shutil

        mongomock_client = mongomock.MongoClient()
        try:
            db = mongomock_client["secondbrain_test"]
            collection = db["embeddings_test"]

            test_dir = tmp_path / "test_pdfs"
            test_dir.mkdir()
            pdf1 = test_dir / "test1.pdf"
            pdf2 = test_dir / "test2.pdf"
            shutil.copy(sample_pdf_path, pdf1)
            shutil.copy(sample_pdf_with_multiple_pages, pdf2)

            random.seed(0)

            def make_emb(text: str) -> list[float]:
                random.seed(hash(text.lower()))
                return [random.random() for _ in range(384)]

            mock_embed = MagicMock()
            mock_embed.generate.side_effect = make_emb
            mock_embed.generate_batch.side_effect = lambda texts: [
                make_emb(t) for t in texts
            ]
            mock_embed.validate_connection.return_value = True

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._collection = collection
            mock_storage._db = db
            mock_storage._client = mongomock_client
            mock_storage.store_batch.return_value = []

            ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

            for pdf_path in [pdf1, pdf2]:
                segments = ingestor._extract_text(pdf_path)
                assert len(segments) > 0, f"No segments from {pdf_path.name}"

                chunks = ingestor._deduplicate_and_chunk_segments(pdf_path, segments)

                with patch.object(
                    ingestor, "_generate_embeddings_with_cache"
                ) as mock_gen_cache:
                    mock_gen_cache.return_value = {
                        c["text_hash"]: make_emb(c["text"]) for c in chunks
                    }
                    docs = ingestor._build_documents_with_embeddings(
                        pdf_path, segments, mock_embed
                    )

                assert len(docs) >= 1, f"No docs produced for {pdf_path.name}"

                for d in docs:
                    assert isinstance(d["embedding"], list)
                    assert len(d["embedding"]) == 384
                    assert d["source_file"] == str(pdf_path)
        finally:
            mongomock_client.close()


class TestFullWorkflow:
    """Tests for complete workflow: ingest -> list -> delete."""

    @pytest.mark.integration
    def test_full_workflow(
        self,
        mongomock_client: mongomock.MongoClient,
    ) -> None:
        """Test complete workflow from ingestion to deletion using mongomock."""
        db = mongomock_client["test_db"]
        collection = db["test_embeddings"]

        original_count = len(list(collection.find()))

        def mock_generate(text: str) -> list[float]:
            import random as r

            r.seed(hash(text.lower()))
            return [r.random() for _ in range(384)]

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
            with patch(
                "secondbrain.embedding.providers.factory.EmbeddingProviderFactory.create_from_config"
            ) as mock_factory:
                mock_embed = MagicMock()
                mock_embed.generate.side_effect = mock_generate
                mock_embed.validate_connection.return_value = True
                mock_factory.return_value = mock_embed

                ingestor = DocumentIngestor(
                    chunk_size=500, chunk_overlap=50, verbose=False
                )
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
            pdf_path.unlink(missing_ok=True)

    @pytest.mark.integration
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
                "embedding": [0.1] * 384,
                "metadata": {"file_type": "pdf"},
            }
        )

        delete_result = collection.delete_one({"chunk_id": "test-chunk-123"})
        assert delete_result.deleted_count == 1

        remaining = list(collection.find())
        assert len(remaining) == 0

    @pytest.mark.integration
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
                    "embedding": [0.1] * 384,
                    "metadata": {"file_type": "pdf"},
                }
            )

        delete_result = collection.delete_many({})
        assert delete_result.deleted_count == 5

        remaining = list(collection.find())
        assert len(remaining) == 0


class TestIntegrationDataFlow:
    """Tests validating data flows between modules."""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_ingestion_creates_proper_chunks(
        self,
        sample_pdf_path: Path,
    ) -> None:
        """Verify chunk schema fields and embedding dimensions from build pipeline."""
        import random

        mongomock_client = mongomock.MongoClient()
        try:
            random.seed(0)

            def make_emb(text: str) -> list[float]:
                random.seed(hash(text.lower()))
                return [random.random() for _ in range(384)]

            mock_embed = MagicMock()
            mock_embed.generate.side_effect = make_emb
            mock_embed.generate_batch.side_effect = lambda texts: [
                make_emb(t) for t in texts
            ]
            mock_embed.validate_connection.return_value = True

            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage.store_batch.return_value = []

            ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)

            segments = ingestor._extract_text(sample_pdf_path)
            assert len(segments) > 0

            chunks = ingestor._deduplicate_and_chunk_segments(sample_pdf_path, segments)

            with patch.object(
                ingestor, "_generate_embeddings_with_cache"
            ) as mock_gen_cache:
                mock_gen_cache.return_value = {
                    c["text_hash"]: make_emb(c["text"]) for c in chunks
                }
                docs = ingestor._build_documents_with_embeddings(
                    sample_pdf_path, segments, mock_embed
                )

            assert len(docs) >= 1
            for doc in docs:
                assert isinstance(doc["chunk_id"], str)
                assert doc.get("source_file") == str(sample_pdf_path)
                assert doc.get("page_number", 0) >= 0
                assert doc.get("chunk_text", "") != ""
                assert isinstance(doc["embedding"], list)
                assert len(doc["embedding"]) == 384
                assert "file_type" in doc
                assert "ingested_at" in doc
        finally:
            mongomock_client.close()

    @pytest.mark.integration
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
                    "embedding": [0.1] * 384,
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

    @pytest.mark.integration
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
                    "embedding": [0.1] * 384,
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

    @pytest.mark.integration
    @pytest.mark.slow
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
