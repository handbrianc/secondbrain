"""Pytest fixtures for integration tests with real services and mock fallbacks."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

import pytest
from qdrant_client import QdrantClient

from secondbrain.config import Config
from secondbrain.embedding.mock import MockEmbeddingGenerator
from secondbrain.storage import MockVectorStorage, QdrantVectorStorage

if TYPE_CHECKING:
    pass

# Get test service URLs from Config (automatically uses test defaults when PYTEST_CURRENT_TEST is set)
_config = Config()
TEST_QDRANT_URL = "http://localhost:6333"
TEST_EMBEDDING_URL = "http://localhost:11434"  # Default LLM endpoint for tests

# Test database/collection names
TEST_QDRANT_COLLECTION = "test_embeddings"

# Health check timeout
SERVICE_HEALTH_TIMEOUT = 10  # seconds - reduced for faster test feedback


def _check_qdrant_healthy() -> bool:
    """Check if the Qdrant test service is healthy."""
    try:
        client = QdrantClient(url=TEST_QDRANT_URL)
        client.get_collections()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def qdrant_test_url() -> str:
    """Qdrant test URL fixture.

    Returns the Qdrant URL configured for the test services.
    """
    return TEST_QDRANT_URL


@pytest.fixture(scope="session")
def embedding_service_url() -> str:
    """OpenAI-compatible embedding API URL fixture.

    Returns the test embedding service URL configured for docker-compose.
    """
    return TEST_EMBEDDING_URL


@pytest.fixture(scope="session")
def wait_for_services() -> Generator[None]:
    """Wait for test services to be healthy before running tests.

    This session-scoped fixture ensures Qdrant is healthy before tests run.
    It waits up to SERVICE_HEALTH_TIMEOUT seconds for services to become available.

    Raises
    ------
        pytest.skip: If services don't become healthy within timeout.
    """
    print("\nWaiting for test services to be healthy...")

    # Wait for Qdrant
    start_time = time.time()
    while time.time() - start_time < SERVICE_HEALTH_TIMEOUT:
        if _check_qdrant_healthy():
            print("Qdrant is healthy")
            break
        print(".", end="", flush=True)
        time.sleep(0.5)  # Reduced from 1s for faster feedback
    else:
        pytest.skip(
            f"Qdrant not available after {SERVICE_HEALTH_TIMEOUT}s - integration tests skipped. "
            f"Start services with appropriate docker-compose setup."
        )

    print("Services are healthy\n")
    yield


@pytest.fixture(scope="session")
def real_storage(wait_for_services: None) -> Generator[QdrantVectorStorage]:
    """VectorStorage with a real Qdrant connection.

    Creates a QdrantVectorStorage instance connected to the test Qdrant server.
    Qdrant provisions the collection lazily on first write, so we force
    provisioning up front via ``delete_all()`` (which triggers ``_ensure_collection``).

    Yields
    ------
        QdrantVectorStorage: Connected storage instance.
    """
    storage = QdrantVectorStorage(
        url=TEST_QDRANT_URL,
        collection_name=TEST_QDRANT_COLLECTION,
    )

    try:
        # Force collection provisioning so operations work immediately.
        storage.delete_all()
        print(f"QdrantVectorStorage initialized: {TEST_QDRANT_COLLECTION}")
        yield storage
    finally:
        # Cleanup: delete all test data
        try:
            storage.delete_all()
            print("Cleaned up test data")
        except Exception as e:
            print(f"Warning: Failed to cleanup test data: {e}")
        storage.close()


@pytest.fixture(scope="session")
def mock_storage() -> Generator[MockVectorStorage]:
    """Mock VectorStorage for integration tests without a real service.

    Provides an in-memory storage implementation for testing integration
    logic without requiring an actual Qdrant connection.

    Yields
    ------
        MockVectorStorage: In-memory storage instance.
    """
    storage = MockVectorStorage()
    storage.initialize()
    yield storage
    storage.close()


@pytest.fixture(scope="session")
def real_embedding_generator(
    wait_for_services: None,
) -> Generator[Any]:
    """Real embedding generator using OpenAI-compatible API (e.g. Ollama, LM Studio).

    Creates an OpenAIEmbeddingProvider instance connected to the test
    embedding service URL configured in the environment.

    Yields
    ------
        OpenAIEmbeddingProvider: Connected embedding generator.
    """
    from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider

    cfg = Config()
    generator = OpenAIEmbeddingProvider(
        model=cfg.embedding_model,
        api_key=cfg.embedding_api_key or "test",
        api_base=cfg.embedding_api_base or TEST_EMBEDDING_URL,
        dimensions=cfg.embedding_dimensions,
    )

    try:
        # Validate connection
        if not generator.validate_connection(force=True):
            raise RuntimeError("Failed to validate embedding generator connection")

        print("EmbeddingGenerator initialized")
        yield generator
    finally:
        generator.close()


@pytest.fixture(scope="session")
def mock_embedding_generator() -> Generator[MockEmbeddingGenerator]:
    """Mock embedding generator for integration tests.

    Provides deterministic, fast embeddings for testing without
    requiring an external embedding service.

    Yields
    ------
        MockEmbeddingGenerator: Mock embedding generator instance.
    """
    generator = MockEmbeddingGenerator(model_name="mock-384", dimension=384)
    yield generator
    generator.close()


@pytest.fixture
async def clean_test_database(
    real_storage: QdrantVectorStorage,
) -> AsyncGenerator[None]:
    """Clean test database before and after each test.

    Ensures a clean slate for each test by deleting all documents
    before the test runs and after the test completes.

    Yields
    ------
        None: Control point for test execution.
    """
    # Cleanup before test
    import contextlib

    with contextlib.suppress(Exception):
        real_storage.delete_all()

    yield

    # Cleanup after test
    with contextlib.suppress(Exception) as e:
        if e:
            print(f"Warning: Failed to cleanup after test: {e}")


@pytest.fixture
def sample_test_document() -> dict[str, Any]:
    """Sample document for testing ingestion and search.

    Returns
    -------
        dict: Sample document with text and metadata.
    """
    return {
        "chunk_id": "test-chunk-001",
        "source_file": "test_document.pdf",
        "page_number": 1,
        "chunk_text": "This is a sample document chunk for integration testing.",
        "metadata": {
            "file_type": "pdf",
            "test": True,
        },
    }


@pytest.fixture
def health_check_utils() -> dict[str, Any]:
    """Provide utility functions for health checking services.

    Returns
    -------
        dict: Dictionary with health check functions.
    """
    return {
        "qdrant_healthy": _check_qdrant_healthy,
    }
