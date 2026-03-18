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

import contextlib
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secondbrain.document import DocumentIngestor, get_file_type
from secondbrain.embedding import LocalEmbeddingGenerator
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
        pass

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
    def test_embedding_generation(self) -> None:
        """Test that embedding generation works."""
        # Skip if SentenceTransformers is not available
        embedding_gen = LocalEmbeddingGenerator()

        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping embedding test")

        # Generate embedding
        test_text = "This is a test document for embedding generation."
        embedding = embedding_gen.generate(test_text)

        # Verify embedding is a list of floats
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.slow
    def test_full_ingestion_pipeline(self, sample_pdf_path: Path) -> None:
        """Test the full ingestion pipeline from PDF to storage.

        This is the main end-to-end test that verifies:
        1. PDF extraction
        2. Text chunking
        3. Embedding generation
        4. Vector storage in MongoDB
        """
        # Skip if services are not available
        embedding_gen = LocalEmbeddingGenerator()
        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping e2e test")

        storage = VectorStorage()
        if not storage.validate_connection():
            pytest.skip("MongoDB not available - skipping e2e test")

        # Perform ingestion
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        result = ingestor.ingest(str(sample_pdf_path))

        # Verify successful ingestion
        assert result["success"] == 1
        assert result["failed"] == 0

        # Verify documents were stored in MongoDB
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))

        # Verify we have stored chunks
        assert len(chunks) > 0

        # Verify chunk structure
        for chunk in chunks:
            assert "chunk_id" in chunk
            assert "source_file" in chunk
            assert "chunk_text" in chunk
            assert len(chunk["chunk_text"]) > 0

    @pytest.mark.slow
    def test_multi_page_pdf_ingestion(
        self, sample_pdf_with_multiple_pages: Path
    ) -> None:
        """Test ingestion of a multi-page PDF document."""
        # Skip if services are not available
        embedding_gen = LocalEmbeddingGenerator()
        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping e2e test")

        storage = VectorStorage()
        if not storage.validate_connection():
            pytest.skip("MongoDB not available - skipping e2e test")

        # Perform ingestion
        ingestor = DocumentIngestor()
        result = ingestor.ingest(str(sample_pdf_with_multiple_pages))

        # Verify successful ingestion
        assert result["success"] == 1
        assert result["failed"] == 0

        # Verify we have multiple pages worth of content
        chunks = storage.list_chunks(source_filter=str(sample_pdf_with_multiple_pages))

        # Should have multiple chunks from 3 pages
        assert len(chunks) >= 3

        # Verify page numbers are captured
        page_numbers = {chunk.get("page_number", 0) for chunk in chunks}
        assert len(page_numbers) >= 2  # At least 2 different pages

    @pytest.mark.slow
    def test_ingestion_with_custom_chunking(self, sample_pdf_path: Path) -> None:
        """Test ingestion with custom chunk size and overlap."""
        # Skip if services are not available
        embedding_gen = LocalEmbeddingGenerator()
        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping e2e test")

        storage = VectorStorage()
        if not storage.validate_connection():
            pytest.skip("MongoDB not available - skipping e2e test")

        # Test with custom chunk settings
        custom_chunk_size = 100
        custom_overlap = 25

        ingestor = DocumentIngestor(
            chunk_size=custom_chunk_size, chunk_overlap=custom_overlap
        )

        # Ingest the PDF
        result = ingestor.ingest(str(sample_pdf_path))

        assert result["success"] == 1

        # Verify chunks respect the custom size
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))
        for chunk in chunks:
            assert len(chunk["chunk_text"]) <= custom_chunk_size


@pytest.mark.integration
@pytest.mark.slow
class TestPDFSearchIntegration:
    """Integration tests for search functionality after ingestion."""

    @pytest.fixture(autouse=True)
    def setup_search_index(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Clean up and recreate search index before each test."""
        from secondbrain.config import get_config

        # Override the autouse mock_config_defaults which sets 384 dimensions
        # The E2E tests need 768 dimensions to match the actual SentenceTransformers model
        monkeypatch.setenv("SECONDBRAIN_EMBEDDING_DIMENSIONS", "768")

        # Clear config cache to pick up the new value
        get_config.cache_clear()

        try:
            from secondbrain.storage import VectorStorage

            storage = VectorStorage()
            if not storage.validate_connection():
                pytest.skip("MongoDB not available")

            # Drop existing index to ensure correct dimensions
            with contextlib.suppress(Exception):
                storage.collection.drop_search_index("embedding_index")

            # Create fresh index with correct dimensions (768)
            storage.ensure_index()
        except (OSError, RuntimeError):
            pass  # Ignore errors

    @pytest.mark.slow
    def test_search_after_ingestion(self, sample_pdf_path: Path) -> None:
        """Test that semantic search works after PDF ingestion."""
        # Skip if services are not available
        embedding_gen = LocalEmbeddingGenerator()
        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping e2e test")

        storage = VectorStorage()
        if not storage.validate_connection():
            pytest.skip("MongoDB not available - skipping e2e test")

        # Clean up before test
        storage.delete_by_source(str(sample_pdf_path))

        # Ingest the PDF
        ingestor = DocumentIngestor()
        ingestor.ingest(str(sample_pdf_path))

        # Verify data was stored
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))
        assert len(chunks) > 0

        # Try search - should work with MongoDB Atlas Local
        try:
            query = "machine learning artificial intelligence"
            query_embedding = embedding_gen.generate(query)
            results = storage.search(query_embedding, top_k=5)

            # Verify we got search results
            assert len(results) > 0

            # Verify result structure
            for result in results:
                assert "chunk_text" in result
                assert "score" in result
        except Exception as e:
            # Skip only if vector search is genuinely not available (code 31082 = SearchNotEnabled)
            # Also skip if index is not initialized
            error_msg = str(e)
            if (
                getattr(e, "code", None) == 31082
                or "SearchNotEnabled" in error_msg
                or "not initialized" in error_msg
                or "needs to be indexed" in error_msg
            ):
                pytest.skip(
                    f"Vector search not available in MongoDB - skipping search test: {e}"
                )
            raise

    @pytest.mark.slow
    def test_search_with_filters(self, sample_pdf_path: Path) -> None:
        """Test search with source and file type filters."""
        # Skip if services are not available
        embedding_gen = LocalEmbeddingGenerator()
        if not embedding_gen.validate_connection():
            pytest.skip("SentenceTransformers not available - skipping e2e test")

        storage = VectorStorage()
        if not storage.validate_connection():
            pytest.skip("MongoDB not available - skipping e2e test")

        # Clean up before test
        storage.delete_by_source(str(sample_pdf_path))

        # Ingest the PDF
        ingestor = DocumentIngestor()
        ingestor.ingest(str(sample_pdf_path))

        # Verify data was stored
        chunks = storage.list_chunks(source_filter=str(sample_pdf_path))
        assert len(chunks) > 0

        # Try search with source filter - should work with MongoDB Atlas Local
        try:
            query_embedding = embedding_gen.generate("test document")
            results = storage.search(
                query_embedding, top_k=5, source_filter="test_document.pdf"
            )

            # Verify results are filtered
            assert all("test_document.pdf" in r.get("source_file", "") for r in results)
        except Exception as e:
            # Skip only if vector search is genuinely not available (code 31082 = SearchNotEnabled)
            # Also skip if index is not initialized
            error_msg = str(e)
            if (
                getattr(e, "code", None) == 31082
                or "SearchNotEnabled" in error_msg
                or "not initialized" in error_msg
                or "needs to be indexed" in error_msg
            ):
                pytest.skip(
                    f"Vector search not available in MongoDB - skipping search test: {e}"
                )
            raise
