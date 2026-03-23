"""Pytest fixtures for secondbrain tests."""

from __future__ import annotations

import atexit
import contextlib
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any, TypeVar
from unittest.mock import MagicMock

import pytest

from secondbrain.config import Config
from secondbrain.embedding import LocalEmbeddingGenerator
from secondbrain.storage import VectorStorage

T = TypeVar("T")


# Function-scoped fixture to clear config cache before each test
@pytest.fixture(autouse=True, scope="function")
def _clear_config_cache_per_test() -> Generator[None, None, None]:
    """Clear config cache before each test to prevent test pollution.

    The get_config() function uses @lru_cache which persists across tests.
    This fixture ensures each test starts with a clean cache.
    """
    from secondbrain.config import get_config

    get_config.cache_clear()
    yield
    get_config.cache_clear()


@pytest.fixture
def storage_config_mock() -> MagicMock:
    """Provide storage configuration mock for tests."""
    config = MagicMock()
    config.mongo_uri = "mongodb://localhost:27017"
    config.mongo_db = "secondbrain"
    config.mongo_collection = "embeddings"
    config.embedding_dimensions = 384
    return config


@pytest.fixture
def storage_with_mocks(storage_config_mock: MagicMock) -> Generator[Any, None, None]:
    """Provide storage instance with mocks to avoid real DB access."""
    # Create a VectorStorage using mocked config to avoid real DB access
    from unittest.mock import patch

    from secondbrain.storage import VectorStorage

    with patch("secondbrain.storage.get_config", return_value=storage_config_mock):
        storage = VectorStorage()
        yield storage
        storage.close()


@pytest.fixture
def mock_mongo_client() -> MagicMock:
    """Mock MongoDB client with ping/compat methods.

    This can be used to patch pymongo.MongoClient in tests that exercise
    Mongo interactions without requiring a real database.
    """
    mock = MagicMock()
    mock.ping.return_value = True  # some code paths use a ping check
    mock.admin.command.return_value = {"ok": 1}
    mock.drop_database.return_value = None
    # Support dict-like access (db[collection]) if the code uses it
    mock.__getitem__.return_value = MagicMock()
    return mock


@pytest.fixture
def mock_collection() -> MagicMock:
    """Provide generic mock for a MongoDB collection."""
    return MagicMock()


@pytest.fixture(scope="session")
def session_config() -> Config:
    """Session-scoped Config instance to avoid repeated initialization overhead.

    Creating a Config instance takes ~180ms due to Pydantic BaseSettings initialization
    (env file parsing, validation, etc.). This fixture creates it once per test session
    instead of per test, saving ~3.5s across 19 config tests.
    """
    return Config()


@pytest.fixture(scope="module")
def mock_embedding_generator() -> MagicMock:
    """Provide mock embedding generator for tests."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock.generate.return_value = [0.1] * 384
    mock.generate_batch.return_value = [[0.1] * 384 for _ in range(5)]

    return mock


@pytest.fixture(scope="module")
def mock_vector_storage() -> MagicMock:
    """Provide mock vector storage for tests."""
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

    return mock


@pytest.fixture
def clean_vector_storage() -> Generator[VectorStorage, None, None]:
    """Fixture to ensure VectorStorage client is properly closed."""
    from secondbrain.storage import VectorStorage

    storage = VectorStorage()
    try:
        yield storage
    finally:
        storage.close()


@pytest.fixture
def clean_embedding_generator() -> Generator[LocalEmbeddingGenerator, None, None]:
    """Fixture to ensure LocalEmbeddingGenerator client is properly closed."""
    from secondbrain.embedding import LocalEmbeddingGenerator

    generator = LocalEmbeddingGenerator()
    try:
        yield generator
    finally:
        generator.close()


@pytest.fixture
def cleanup_resources(request: Any) -> Generator[None, None, None]:
    """Opt-in cleanup for VectorStorage and LocalEmbeddingGenerator after tests.

    This fixture is NO LONGER autouse - tests must explicitly request it via
    `cleanup_resources` parameter to get automatic client cleanup.

    For tests that don't need cleanup (e.g., pure unit tests with mocks),
    this avoids the ~0.2s overhead from patching/unpatching classes.

    Usage:
        def test_something(cleanup_resources):
            # cleanup will happen automatically after this test
            ...
    """
    # Track which clients were actually used during the test
    clients_to_cleanup: list[tuple[str, Any]] = []

    # Patch the classes to track instantiation
    original_init: dict[str, Any] = {}

    def track_storage_init(self: Any, *args: Any, **kwargs: Any) -> None:
        clients_to_cleanup.append(("storage", self))
        original_init.get("storage", lambda *_: None)(self)

    def track_generator_init(self: Any, *args: Any, **kwargs: Any) -> None:
        clients_to_cleanup.append(("generator", self))
        original_init.get("generator", lambda *_: None)(self)

    def track_searcher_init(self: Any, *args: Any, **kwargs: Any) -> None:
        clients_to_cleanup.append(("searcher", self))
        original_init.get("searcher", lambda *_: None)(self)

    from secondbrain.embedding import LocalEmbeddingGenerator
    from secondbrain.search import Searcher
    from secondbrain.storage import VectorStorage

    original_init["storage"] = VectorStorage.__init__
    original_init["generator"] = LocalEmbeddingGenerator.__init__
    original_init["searcher"] = Searcher.__init__

    VectorStorage.__init__ = track_storage_init  # type: ignore[method-assign]
    LocalEmbeddingGenerator.__init__ = track_generator_init  # type: ignore[method-assign]
    Searcher.__init__ = track_searcher_init  # type: ignore[method-assign]

    try:
        yield
    finally:
        # Restore original init methods
        VectorStorage.__init__ = original_init.get("storage", VectorStorage.__init__)  # type: ignore[method-assign]
        LocalEmbeddingGenerator.__init__ = original_init.get(  # type: ignore[method-assign]
            "generator", LocalEmbeddingGenerator.__init__
        )
        Searcher.__init__ = original_init.get("searcher", Searcher.__init__)  # type: ignore[method-assign]

        # Only cleanup clients that were actually instantiated
        with contextlib.suppress(Exception):
            for _, client in clients_to_cleanup:
                client.close()


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
        "SECONDBRAIN_LOCALHOST": "http://localhost:11434",
        "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
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
        "SECONDBRAIN_LOCALHOST": "http://localhost:11434",
        "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "SECONDBRAIN_CHUNK_SIZE": 256,  # Smaller chunks for faster processing
        "SECONDBRAIN_CHUNK_OVERLAP": 25,
        "SECONDBRAIN_DEFAULT_TOP_K": 3,
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": 384,
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": 100,  # Higher limit for faster tests
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": 0.1,  # 10x faster for testing
        "SECONDBRAIN_CONNECTION_CACHE_TTL": 10.0,  # Shorter cache TTL
        "SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT": 0.1,  # 300x faster for testing
        "SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD": 3,  # Lower threshold for testing
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))
    return test_config


@pytest.fixture
def fast_cli_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture for fast CLI unit tests that don't need client cleanup.

    This fixture:
    - Sets up minimal config defaults
    - Does NOT patch VectorStorage/LocalEmbeddingGenerator (avoids 0.2s overhead)
    - Does NOT enable automatic cleanup

    Use this for pure CLI validation tests that mock all dependencies.

    Usage:
        def test_cli_validation(fast_cli_test):
            # No cleanup overhead, fast execution
            ...
    """
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_LOCALHOST": "http://localhost:11434",
        "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
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


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "This is a sample document. It contains multiple sentences. " * 10


@pytest.fixture
def sample_embedding() -> list[float]:
    """Sample embedding vector."""
    import random

    random.seed(42)
    return [random.random() for _ in range(384)]


@pytest.fixture
def cached_embedding_generator(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock embedding generator with pre-cached embeddings for fast tests.

    This fixture mocks the LocalEmbeddingGenerator to return pre-computed
    embeddings instead of calling SentenceTransformers, reducing test time by ~2-3s per test.
    """
    import random
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock._model_pulled = True

    # Pre-compute deterministic embeddings based on text hash
    def mock_generate(text: str) -> list[float]:
        random.seed(hash(text.lower()) % (2**32))
        return [random.random() for _ in range(384)]

    mock.generate.side_effect = mock_generate
    mock.generate_batch.side_effect = lambda texts: [mock_generate(t) for t in texts]

    monkeypatch.setattr(
        "secondbrain.embedding.LocalEmbeddingGenerator",
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
        {"text": "This is mock SecondBrain test text from page 1. " * 10, "page": 1},
        {"text": "This is mock SecondBrain test text from page 2. " * 10, "page": 2},
        {"text": "This is mock SecondBrain test text from page 3. " * 10, "page": 3},
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
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

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
    except (OSError, RuntimeError):
        pass


def _cleanup_embedding() -> None:
    """Cleanup function to be registered with atexit."""
    try:
        from secondbrain.embedding import LocalEmbeddingGenerator

        generator = LocalEmbeddingGenerator()
        generator.close()
    except (OSError, RuntimeError):
        pass


@pytest.fixture(scope="session", autouse=True)
def mock_config_defaults() -> None:
    """Mock configuration defaults for test environment.

    Note: Does NOT set SECONDBRAIN_MONGO_DB to allow tests to use their own
    database names. Unit tests expect "secondbrain", integration tests use
    "test_secondbrain" via their own fixtures.
    """
    import os

    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        # NOTE: Not setting SECONDBRAIN_MONGO_DB - tests control their own db name
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_LOCALHOST": "http://localhost:11434",
        "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "SECONDBRAIN_CHUNK_SIZE": 512,
        "SECONDBRAIN_CHUNK_OVERLAP": 50,
        "SECONDBRAIN_DEFAULT_TOP_K": 5,
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": 384,
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": 10,
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": 1.0,
        "SECONDBRAIN_CONNECTION_CACHE_TTL": 60.0,
        "SECONDBRAIN_CIRCUIT_BREAKER_RECOVERY_TIMEOUT": 0.5,
        "SECONDBRAIN_CIRCUIT_BREAKER_FAILURE_THRESHOLD": 3,
    }
    for key, value in test_config.items():
        os.environ[key] = str(value)


def _cleanup_coverage_files() -> None:
    project_root = Path(__file__).parent.parent.parent
    coverage_patterns = [
        project_root / ".coverage",
        project_root / ".coverage.*",
    ]

    for pattern in coverage_patterns:
        for coverage_file in pattern.parent.glob(pattern.name):
            with contextlib.suppress(OSError):
                coverage_file.unlink()

    htmlcov_dir = project_root / "htmlcov"
    if htmlcov_dir.exists():
        shutil.rmtree(htmlcov_dir, ignore_errors=True)


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
    except (OSError, RuntimeError, Exception):
        # Silently ignore cleanup errors when MongoDB is unavailable
        pass


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Cleanup after test session finishes."""
    del session, exitstatus  # Unused but required for interface
    _cleanup_mongodb()
    _cleanup_storage()
    _cleanup_embedding()


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: Any
) -> None:
    """Provide terminal summary after test run."""
    del terminalreporter, exitstatus, config  # Unused but required for interface


# Register cleanup handlers for atexit to catch any remaining resources
atexit.register(_cleanup_storage)
atexit.register(_cleanup_embedding)
atexit.register(_cleanup_mongodb)
