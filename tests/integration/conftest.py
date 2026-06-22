"""Pytest fixtures for integration tests with real services and mock fallbacks."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from pymongo import MongoClient

from secondbrain.config import Config
from secondbrain.embedding.mock import MockEmbeddingGenerator
from secondbrain.storage import MockVectorStorage, VectorStorage

if TYPE_CHECKING:
    pass

# Get test service URLs from Config (automatically uses test defaults when PYTEST_CURRENT_TEST is set)
_config = Config()
TEST_MONGO_URI = _config.mongo_uri
TEST_EMBEDDING_URL = "http://localhost:11434"  # Default LLM endpoint for tests

# Test database/collection names
TEST_DB_NAME = _config.mongo_db
TEST_COLLECTION_NAME = "test_embeddings"

# Health check timeout
SERVICE_HEALTH_TIMEOUT = 10  # seconds - reduced for faster test feedback


def _check_mongodb_healthy() -> bool:
    """Check if MongoDB test service is healthy."""
    try:
        client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=10000, maxPoolSize=50)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False





@pytest.fixture(scope="session")
def mongo_test_uri() -> str:
    """MongoDB test URI fixture.

    Returns the test MongoDB URI configured for docker-compose test services.
    """
    return TEST_MONGO_URI


@pytest.fixture(scope="session")
def embedding_service_url() -> str:
    """OpenAI-compatible embedding API URL fixture.

    Returns the test embedding service URL configured for docker-compose.
    """
    return TEST_EMBEDDING_URL


@pytest.fixture(scope="session")
def wait_for_services() -> Generator[None, None, None]:
    """Wait for test services to be healthy before running tests.

    This session-scoped fixture ensures MongoDB is healthy before tests run.
    It waits up to SERVICE_HEALTH_TIMEOUT seconds for services to become available.

    Raises:
        pytest.skip: If services don't become healthy within timeout.
    """
    print("\nWaiting for test services to be healthy...")

    # Wait for MongoDB
    start_time = time.time()
    while time.time() - start_time < SERVICE_HEALTH_TIMEOUT:
        if _check_mongodb_healthy():
            print("MongoDB is healthy")
            break
        print(".", end="", flush=True)
        time.sleep(0.5)  # Reduced from 1s for faster feedback
    else:
        pytest.skip(
            f"MongoDB not available after {SERVICE_HEALTH_TIMEOUT}s - integration tests skipped. "
            f"Start services with appropriate docker-compose setup."
        )

    print("Services are healthy\n")
    yield


@pytest.fixture(scope="session")
def real_storage(wait_for_services: None) -> Generator[VectorStorage, None, None]:
    """VectorStorage with real MongoDB connection.

    Creates a VectorStorage instance connected to the test MongoDB database.
    Ensures the vector search index is created and waits for it to be ready.

    Yields:
        VectorStorage: Connected storage instance.
    """
    storage = VectorStorage(
        mongo_uri=TEST_MONGO_URI,
        db_name=TEST_DB_NAME,
        collection_name=TEST_COLLECTION_NAME,
    )

    try:
        # Ensure index exists
        storage.ensure_index()
        storage._wait_for_index_ready()
        print(f"VectorStorage initialized: {TEST_DB_NAME}/{TEST_COLLECTION_NAME}")
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
def mock_storage() -> Generator[MockVectorStorage, None, None]:
    """Mock VectorStorage for integration tests without MongoDB.

    Provides an in-memory storage implementation for testing integration
    logic without requiring actual MongoDB connections.

    Yields:
        MockVectorStorage: In-memory storage instance.
    """
    storage = MockVectorStorage()
    storage.initialize()
    yield storage
    storage.close()


@pytest.fixture(scope="session")
def real_embedding_generator(
    wait_for_services: None,
) -> Generator[Any, None, None]:
    """Real embedding generator using OpenAI-compatible API (e.g. Ollama, LM Studio).

    Creates an OpenAIEmbeddingProvider instance connected to the test
    embedding service URL configured in the environment.

    Yields:
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
def mock_embedding_generator() -> Generator[MockEmbeddingGenerator, None, None]:
    """Mock embedding generator for integration tests.

    Provides deterministic, fast embeddings for testing without
    requiring an external embedding service.

    Yields:
        MockEmbeddingGenerator: Mock embedding generator instance.
    """
    generator = MockEmbeddingGenerator(model_name="mock-384", dimension=384)
    yield generator
    generator.close()


@pytest.fixture
async def clean_test_database(
    real_storage: VectorStorage,
) -> AsyncGenerator[None, None]:
    """Clean test database before and after each test.

    Ensures a clean slate for each test by deleting all documents
    before the test runs and after the test completes.

    Yields:
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

    Returns:
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

    Returns:
        dict: Dictionary with health check functions.
    """
    return {
        "mongodb_healthy": _check_mongodb_healthy,
    }
