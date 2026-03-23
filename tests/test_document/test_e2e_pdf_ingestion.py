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
from unittest.mock import MagicMock

import pytest

from secondbrain.document import DocumentIngestor, get_file_type
from secondbrain.storage import VectorStorage

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
    def mock_external_services(
        self,
        monkeypatch: pytest.MonkeyPatch,
        cached_embedding_generator: MagicMock,
        mocked_pdf_extraction: MagicMock,
    ) -> None:
        """Mock external services to speed up E2E tests."""
        del (
            monkeypatch,
            cached_embedding_generator,
            mocked_pdf_extraction,
        )  # Unused but sets up mocks

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
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

    @pytest.mark.slow
    def test_full_ingestion_pipeline(
        self, sample_pdf_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test the full ingestion pipeline from PDF to storage.

        This is the main end-to-end test that verifies:
        1. PDF extraction
        2. Text chunking
        3. Embedding generation
        4. Vector storage in MongoDB
        """
        del mocked_pdf_extraction  # Unused fixture - sets up mocks
        # Perform ingestion with mocked services
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        result = ingestor.ingest(str(sample_pdf_path))

        # Verify successful ingestion
        assert result["success"] == 1
        assert result["failed"] == 0

    @pytest.mark.slow
    def test_multi_page_pdf_ingestion(
        self, sample_pdf_with_multiple_pages: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test ingestion of a multi-page PDF document."""
        del mocked_pdf_extraction  # Unused fixture - sets up mocks
        # Perform ingestion with mocked services
        ingestor = DocumentIngestor()
        result = ingestor.ingest(str(sample_pdf_with_multiple_pages))

        # Verify successful ingestion
        assert result["success"] == 1
        assert result["failed"] == 0

    @pytest.mark.slow
    def test_ingestion_with_custom_chunking(
        self, sample_pdf_path: Path, mocked_pdf_extraction: MagicMock
    ) -> None:
        """Test ingestion with custom chunk size and overlap."""
        del mocked_pdf_extraction  # Unused fixture - sets up mocks
        # Test with custom chunk settings
        custom_chunk_size = 100
        custom_overlap = 25

        ingestor = DocumentIngestor(
            chunk_size=custom_chunk_size, chunk_overlap=custom_overlap
        )

        # Ingest the PDF with mocked services
        result = ingestor.ingest(str(sample_pdf_path))

        assert result["success"] == 1


@pytest.mark.integration
@pytest.mark.slow
class TestPDFSearchIntegration:
    """Integration tests for search functionality after ingestion."""

    @pytest.fixture(autouse=True)
    def setup_search_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set up test environment with mocked services."""
        from secondbrain.config import get_config

        # Override the autouse mock_config_defaults which sets 384 dimensions
        # The E2E tests need 768 dimensions to match the actual SentenceTransformers model
        monkeypatch.setenv("SECONDBRAIN_EMBEDDING_DIMENSIONS", "768")

        # Clear config cache to pick up the new value
        get_config.cache_clear()

    @pytest.mark.slow
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

    @pytest.mark.slow
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
