"""Pytest fixtures for integration tests with real services and mock fallbacks."""

from __future__ import annotations

import os
import time
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

import pytest
from pymongo import MongoClient

from secondbrain.embedding.mock import MockEmbeddingGenerator
from secondbrain.storage import MockVectorStorage, VectorStorage

if TYPE_CHECKING:
    pass


TEST_MONGO_URI_EMPTY = ""
TEST_DB_NAME_EMPTY = ""
TEST_EMBEDDING_URL = os.getenv("SECONDBRAIN_EMBEDDING_URL", "http://localhost:11435")
TEST_COLLECTION_NAME = "test_embeddings"
SERVICE_HEALTH_TIMEOUT = 10


def _read_env_test(key: str, default: str) -> str:
    """Read a value from .env.test (if present), else return default."""
    from pathlib import Path
    env_path = Path(__file__).parent.parent.parent / ".env.test"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, val = line.partition("=")
                if k.strip() == key:
                    return val.strip().strip('"').strip("'")
    return default


def get_test_mongo_uri() -> str:
    uri = os.environ.get(
        "SECONDBRAIN_MONGO_URI",
        "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin",
    )
    if uri:
        return uri
    return _read_env_test(
        "SECONDBRAIN_MONGO_URI",
        "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin",
    )


def get_test_db_name() -> str:
    db = os.environ.get("SECONDBRAIN_MONGO_DB", "")
    if db:
        return db
    return _read_env_test("SECONDBRAIN_MONGO_DB", "secondbrain_test")


def _check_mongodb_healthy() -> bool:
    try:
        client = MongoClient(get_test_mongo_uri(), serverSelectionTimeoutMS=5000, maxPoolSize=50)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def _check_embedding_service_healthy() -> bool:
    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        return True
    except Exception:
        return False


def _check_llm_service_healthy() -> bool:
    """Check if LLM service is healthy (always returns True - LLM is mocked in tests)."""
    return True


@pytest.fixture(scope="session")
def mongo_test_uri() -> str:
    """MongoDB test URI fixture.

    Returns the test MongoDB URI configured for docker-compose test services.
    """
    return get_test_mongo_uri()


@pytest.fixture(scope="session")
def embedding_service_url() -> str:
    """Sentence-transformers service URL fixture.

    Returns the test embedding service URL configured for docker-compose.
    """
    return TEST_EMBEDDING_URL


@pytest.fixture(scope="session")
def wait_for_services() -> Generator[None, None, None]:
    """Wait for test services to be healthy before running tests.

    This session-scoped fixture ensures both MongoDB and sentence-transformers
    services are healthy before tests run. It waits up to SERVICE_HEALTH_TIMEOUT
    seconds for services to become available.

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
        time.sleep(0.1)  # Poll interval scaled down from 0.5 for faster test execution
    else:
        pytest.skip(
            f"MongoDB not available after {SERVICE_HEALTH_TIMEOUT}s - integration tests skipped. "
            f"Start services with appropriate docker-compose setup."
        )

    print("MongoDB is healthy\n")
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
        mongo_uri=get_test_mongo_uri(),
        db_name=get_test_db_name(),
        collection_name=TEST_COLLECTION_NAME,
    )

    try:
        # Ensure index exists
        storage.ensure_index()
        storage._wait_for_index_ready()
        print(f"VectorStorage initialized: {get_test_db_name()}/{TEST_COLLECTION_NAME}")
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
def mock_embedding_generator() -> Generator[MockEmbeddingGenerator, None, None]:
    """Mock embedding generator for integration tests.

    Provides deterministic, fast embeddings for testing without
    requiring sentence-transformers service.

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
        "embedding_healthy": _check_embedding_service_healthy,
        "llm_healthy": _check_llm_service_healthy,
    }
