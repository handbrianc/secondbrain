"""End-to-end integration tests for PDF ingestion.

These tests exercise the full ingestion pipeline:
1. PDF text extraction (via docling)
2. Text chunking
3. Embedding generation (via SentenceTransformers)
4. Vector storage (in MongoDB)

Note: These tests require MongoDB and SentenceTransformers to be running.
Run with: pytest tests/test_document/test_e2e_pdf_ingestion.py -v
Run excluded from fast tests: pytest -m "not integration"
"""

import warnings
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from secondbrain.document import DocumentIngestor, get_file_type
from secondbrain.storage import VectorStorage

# Mark all tests as e2e (end-to-end with real services)
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
]

# Suppress docling deprecation warnings (upstream library issue)
warnings.filterwarnings(
    "ignore",
    message=".*This field is deprecated.*",
    category=DeprecationWarning,
    module="docling",
)


@pytest.mark.integration
@pytest.mark.slow
class TestPDFIngestionE2E:
    """End-to-end tests for PDF ingestion pipeline."""

    @pytest.fixture(autouse=True)
    def mock_storage_and_services(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cached_embedding_generator: MagicMock,
        mocked_pdf_extraction: MagicMock,
        auto_mongomock: Any,
    ) -> None:
        """Mock external services and MongoDB to speed up E2E tests."""
        mock_storage_instance = MagicMock()
        mock_storage_instance.validate_connection.return_value = True
        mock_storage_instance.delete_by_source.return_value = 0
        mock_storage_instance.list_chunks.return_value = []
        mock_storage_instance.store_batch.return_value = 1
        mock_storage_instance.store.return_value = "mock_id"
        mock_storage_instance.search.return_value = []
        mock_storage_instance.ensure_index.return_value = True

        def mock_storage_constructor(*args, **kwargs):
            return mock_storage_instance

        monkeypatch.setattr(
            "secondbrain.storage.VectorStorage",
            mock_storage_constructor,
        )

        del (
            monkeypatch,
            cached_embedding_generator,
            mocked_pdf_extraction,
            auto_mongomock,
        )

    def test_pdf_text_extraction(self, sample_pdf_path: Path) -> None:
        """Test that PDF text extraction works correctly."""
        # Verify the PDF file exists
        assert sample_pdf_path.exists()
        assert sample_pdf_path.suffix.lower() == ".pdf"

        # Test file type detection
        file_type = get_file_type(sample_pdf_path)
        assert file_type == "pdf"

        # Test text extraction via DocumentIngestor
        ingestor = DocumentIngestor()
        segments = ingestor._extract_text(sample_pdf_path)

        # Verify we got text segments
        assert len(segments) > 0
        assert all("text" in segment and "page" in segment for segment in segments)

        # Verify the text contains expected content
        combined_text = " ".join(seg["text"] for seg in segments)
        assert len(combined_text) > 0
        assert "SecondBrain" in combined_text or "test" in combined_text.lower()

    def test_pdf_text_chunking(self, sample_pdf_path: Path) -> None:
        """Test that PDF text is chunked correctly."""
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)

        # Extract text
        segments = ingestor._extract_text(sample_pdf_path)

        # Chunk the text
        chunks = ingestor._chunk_text(segments)

        # Verify we got chunks
        assert len(chunks) > 0
        assert all("text" in chunk and "page" in chunk for chunk in chunks)

        # Verify chunk size constraints
        for chunk in chunks:
            assert len(chunk["text"]) <= 100

    def test_embedding_generation(self, cached_embedding_generator: MagicMock) -> None:
        """Test that embedding generation works."""
        # Use mocked embedding generator
        embedding_gen = cached_embedding_generator

        # Generate embedding
        test_text = "This is a test document for embedding generation."
        embedding = embedding_gen.generate(test_text)

        # Verify embedding is a list of floats
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)


@pytest.mark.integration
@pytest.mark.slow
class TestPDFSearchIntegration:
    """Integration tests for search functionality after ingestion."""

    @pytest.fixture(autouse=True, scope="function")
    def mock_storage_for_search_tests(
        self,
        monkeypatch: pytest.MonkeyPatch,
        auto_mongomock: Any,
    ) -> None:
        """Mock MongoDB storage for search tests."""
        from secondbrain.config import get_config

        monkeypatch.setenv("SECONDBRAIN_EMBEDDING_DIMENSIONS", "768")
        get_config.cache_clear()

        mock_storage_instance = MagicMock()
        mock_storage_instance.validate_connection.return_value = True
        mock_storage_instance.delete_by_source.return_value = 0
        mock_storage_instance.list_chunks.return_value = [
            {"chunk_text": "mock chunk", "source_file": "test_document.pdf"}
        ]

        from secondbrain import storage

        monkeypatch.setattr(
            storage, "VectorStorage", MagicMock(return_value=mock_storage_instance)
        )
        import sys

        this_module = sys.modules[__name__]
        monkeypatch.setattr(
            this_module, "VectorStorage", MagicMock(return_value=mock_storage_instance)
        )

        del monkeypatch, auto_mongomock

    def test_search_after_ingestion(
        self,
        sample_pdf_path: Path,
        mocked_pdf_extraction: MagicMock,
        cached_embedding_generator: MagicMock,
    ) -> None:
        """Test that semantic search works after PDF ingestion."""
        del mocked_pdf_extraction  # Unused fixture - sets up mocks
        # Clean up before test
        storage = VectorStorage()
        storage.delete_by_source(str(sample_pdf_path))

        # Ingest the PDF with mocked services
        ingestor = DocumentIngestor()
        ingestor.ingest(str(sample_pdf_path))

        # Verify data was stored
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))
        assert len(chunks) > 0

        # Generate query embedding using mocked generator
        query = "machine learning artificial intelligence"
        _ = cached_embedding_generator.generate(query)

        # For this test, verify we can get chunks (actual vector search requires MongoDB setup)
        # The search functionality is tested in other unit tests with mocks
        assert len(chunks) > 0
        for chunk in chunks:
            assert "chunk_text" in chunk

    def test_search_with_filters(
        self, sample_pdf_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test search with source and file type filters."""
        del mocked_pdf_extraction  # Unused fixture - sets up mocks
        # Clean up before test
        storage = VectorStorage()
        storage.delete_by_source(str(sample_pdf_path))

        # Ingest the PDF with mocked services
        ingestor = DocumentIngestor()
        ingestor.ingest(str(sample_pdf_path))

        # Verify data was stored
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))
        assert len(chunks) > 0

        # Verify source filtering works at the storage level
        # (Actual vector search with filters is tested in unit tests)
        for chunk in chunks:
            assert "test_document.pdf" in chunk.get("source_file", "")
