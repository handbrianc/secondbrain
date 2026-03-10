"""Pytest fixtures for secondbrain tests."""

from __future__ import annotations

import atexit
from pathlib import Path
from typing import Any, TypeVar
from unittest.mock import MagicMock

import pytest

T = TypeVar("T")


@pytest.fixture
def mock_embedding_generator(monkeypatch: pytest.MonkeyPatch) -> Any:
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock.generate.return_value = [0.1] * 768
    mock.generate_batch.return_value = [[0.1] * 768 for _ in range(5)]

    monkeypatch.setattr(
        "secondbrain.document.EmbeddingGenerator",
        lambda *args, **kwargs: mock,
    )
    return mock


@pytest.fixture
def mock_vector_storage(monkeypatch: pytest.MonkeyPatch) -> Any:
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock.search.return_value = []
    mock.list_chunks.return_value = []
    mock.store.return_value = "test_id"
    mock.store_batch.return_value = 1
    mock.delete_by_source.return_value = 0
    mock.delete_by_chunk_id.return_value = 0
    mock.delete_all.return_value = 0
    mock.get_stats.return_value = {
        "total_chunks": 0,
        "unique_sources": 0,
        "database": "test",
        "collection": "test",
    }

    monkeypatch.setattr(
        "secondbrain.document.VectorStorage",
        lambda *args, **kwargs: mock,
    )
    return mock


@pytest.fixture
def clean_vector_storage() -> Any:
    """Fixture to ensure VectorStorage client is properly closed."""
    from secondbrain.storage import VectorStorage

    storage = VectorStorage()
    try:
        yield storage
    finally:
        storage.close()


@pytest.fixture
def clean_embedding_generator() -> Any:
    """Fixture to ensure EmbeddingGenerator client is properly closed."""
    from secondbrain.embedding import EmbeddingGenerator

    generator = EmbeddingGenerator()
    try:
        yield generator
    finally:
        generator.close()


@pytest.fixture(autouse=True)
def cleanup_resources(request: Any) -> Any:
    """Automatically cleanup VectorStorage and EmbeddingGenerator after each test."""
    try:
        yield
    finally:
        from secondbrain.embedding import EmbeddingGenerator
        from secondbrain.search import Searcher
        from secondbrain.storage import VectorStorage

        try:
            storage = VectorStorage()
            storage.close()
        except Exception:
            pass

        try:
            generator = EmbeddingGenerator()
            generator.close()
        except Exception:
            pass

        try:
            searcher = Searcher()
            searcher.close()
        except Exception:
            pass


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test data."""
    return tmp_path / "test_data"


@pytest.fixture
def mock_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock configuration for testing."""
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
        "SECONDBRAIN_MODEL": "embeddinggemma:latest",
        "SECONDBRAIN_CHUNK_SIZE": 512,
        "SECONDBRAIN_CHUNK_OVERLAP": 50,
        "SECONDBRAIN_DEFAULT_TOP_K": 5,
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": 384,
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": 10,
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": 1.0,
        "SECONDBRAIN_CONNECTION_CACHE_TTL": 60.0,
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))
    return test_config


@pytest.fixture
def fast_test_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock configuration optimized for fast test execution.

    Reduces rate limiter windows and uses smaller test data sizes
    to speed up test execution while maintaining test validity.
    """
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain_fast",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings_fast",
        "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
        "SECONDBRAIN_MODEL": "embeddinggemma:latest",
        "SECONDBRAIN_CHUNK_SIZE": 256,  # Smaller chunks for faster processing
        "SECONDBRAIN_CHUNK_OVERLAP": 25,
        "SECONDBRAIN_DEFAULT_TOP_K": 3,
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": 384,
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": 100,  # Higher limit for faster tests
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": 0.1,  # 10x faster for testing
        "SECONDBRAIN_CONNECTION_CACHE_TTL": 10.0,  # Shorter cache TTL
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))
    return test_config


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "This is a sample document. It contains multiple sentences. " * 10


@pytest.fixture
def sample_embedding() -> list[float]:
    """Sample embedding vector."""
    import random

    random.seed(42)
    return [random.random() for _ in range(768)]


@pytest.fixture
def cached_embedding_generator(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock embedding generator with pre-cached embeddings for fast tests.

    This fixture mocks the EmbeddingGenerator to return pre-computed
    embeddings instead of calling Ollama, reducing test time by ~2-3s per test.
    """
    import random
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock._model_pulled = True

    # Pre-compute deterministic embeddings based on text hash
    def mock_generate(text: str) -> list[float]:
        random.seed(hash(text.lower()) % (2**32))
        return [random.random() for _ in range(768)]

    mock.generate.side_effect = mock_generate
    mock.generate_batch.side_effect = lambda texts: [mock_generate(t) for t in texts]

    monkeypatch.setattr(
        "secondbrain.document.EmbeddingGenerator",
        lambda *args, **kwargs: mock,
    )
    monkeypatch.setattr(
        "secondbrain.embedding.EmbeddingGenerator",
        lambda *args, **kwargs: mock,
    )
    monkeypatch.setattr(
        "secondbrain.search.EmbeddingGenerator",
        lambda *args, **kwargs: mock,
    )

    return mock


@pytest.fixture
def mocked_pdf_extraction(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock PDF text extraction to avoid slow docling processing.

    This fixture mocks the DocumentIngestor._extract_text method to return
    pre-computed text segments instead of parsing PDFs with docling,
    reducing test time by ~3-5s per test.
    """
    from unittest.mock import MagicMock

    mock = MagicMock()

    # Pre-computed mock segments that mimic real PDF extraction
    mock_segments = [
        {"text": "This is mock text from page 1. " * 10, "page": 1},
        {"text": "This is mock text from page 2. " * 10, "page": 2},
        {"text": "This is mock text from page 3. " * 10, "page": 3},
    ]

    def mock_extract_text(self: Any, pdf_path: Path) -> list[dict[str, Any]]:
        return mock_segments

    monkeypatch.setattr(
        "secondbrain.document.DocumentIngestor._extract_text",
        mock_extract_text,
    )

    return mock


@pytest.fixture(scope="session")
def sample_pdf_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a sample PDF file for testing.

    Creates a simple PDF with some text content for testing
    the document ingestion pipeline.
    Cached at session scope to avoid repeated PDF generation.
    """
    from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
    from reportlab.lib.units import mm  # type: ignore[import-untyped]
    from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

    tmp_path = tmp_path_factory.mktemp("data")
    pdf_path = tmp_path / "test_document.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    c.setFont("Helvetica-Bold", 24)
    c.drawString(50 * mm, height - 30 * mm, "SecondBrain Test Document")

    c.setFont("Helvetica", 12)
    text_y = height - 50 * mm

    text = (
        "This is a sample PDF document created for testing the ingestion pipeline. "
        "It contains multiple sentences for testing text extraction and chunking. "
        "The document includes various content to test the full ingestion pipeline. "
        "Additional testing content includes keywords like machine learning, "
        "artificial intelligence, and natural language processing. "
        "This helps verify that the embedding generation works correctly. "
        "The storage and retrieval functions are also validated through this test."
    )

    c.drawString(50 * mm, text_y, text)

    c.showPage()
    c.setFont("Helvetica", 12)
    c.drawString(50 * mm, height - 30 * mm, "Page 2 - Additional Content")
    c.drawString(
        50 * mm,
        height - 50 * mm,
        "More text for testing multi-page extraction and chunking.",
    )

    c.save()

    return pdf_path


@pytest.fixture(scope="session")
def sample_pdf_with_multiple_pages(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a sample multi-page PDF for testing.

    Cached at session scope to avoid repeated PDF generation.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    tmp_path = tmp_path_factory.mktemp("data")
    pdf_path = tmp_path / "multi_page_document.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    for page_num in range(3):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50 * mm, height - 30 * mm, f"Page {page_num + 1} - Test Document")

        c.setFont("Helvetica", 12)
        text = (
            f"This is page {page_num + 1} of a multi-page test document. "
            "It contains enough text to test multi-page extraction and chunking functionality. "
            "The content includes various topics like data science, machine learning, "
            "deep learning, neural networks, and artificial intelligence. "
            "This helps verify that text extraction works correctly across multiple pages. "
            "The chunking logic also needs to handle page boundaries properly."
        )

        c.drawString(50 * mm, height - 50 * mm, text)
        c.showPage()

    c.save()

    return pdf_path


def _cleanup_storage() -> None:
    """Cleanup function to be registered with atexit."""
    try:
        from secondbrain.storage import VectorStorage

        storage = VectorStorage()
        storage.close()
    except Exception:
        pass


def _cleanup_embedding() -> None:
    """Cleanup function to be registered with atexit."""
    try:
        from secondbrain.embedding import EmbeddingGenerator

        generator = EmbeddingGenerator()
        generator.close()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def mock_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure all config defaults are available for tests that patch get_config."""
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
        "SECONDBRAIN_MODEL": "embeddinggemma:latest",
        "SECONDBRAIN_CHUNK_SIZE": 512,
        "SECONDBRAIN_CHUNK_OVERLAP": 50,
        "SECONDBRAIN_DEFAULT_TOP_K": 5,
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": 384,
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": 10,
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": 1.0,
        "SECONDBRAIN_CONNECTION_CACHE_TTL": 60.0,
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))


def _cleanup_mongodb() -> None:
    """Cleanup MongoDB test database."""
    try:
        from pymongo import MongoClient

        client: MongoClient[dict[str, Any]] = MongoClient(
            "mongodb://localhost:27017", serverSelectionTimeoutMS=1000
        )
        try:
            client.drop_database("test_secondbrain")
        finally:
            client.close()
    except Exception:
        pass


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    # Cleanup after all tests complete
    _cleanup_mongodb()
    _cleanup_storage()
    _cleanup_embedding()


# Register cleanup handlers for atexit to catch any remaining resources
atexit.register(_cleanup_storage)
atexit.register(_cleanup_embedding)
atexit.register(_cleanup_mongodb)
