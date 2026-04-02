"""Pytest fixtures for integration tests with real services."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from pymongo import MongoClient

from secondbrain.embedding import LocalEmbeddingGenerator
from secondbrain.storage import VectorStorage
from secondbrain.utils.observability import MetricsCollector

if TYPE_CHECKING:
    pass

# Test service URLs (use running services)
# Check if running in Docker environment
import os

if os.getenv("RUNNING_IN_CI", "false").lower() == "true":
    # Docker-compose test environment
    TEST_MONGO_URI = "mongodb://mongodb:27017/secondbrain_test"
    TEST_EMBEDDING_URL = "http://sentence-transformers:8000"
else:
    # Local development environment
    TEST_MONGO_URI = "mongodb://127.0.0.1:27018/secondbrain_test"
    TEST_EMBEDDING_URL = "http://localhost:11435"

# Test database/collection names
TEST_DB_NAME = "secondbrain_test"
TEST_COLLECTION_NAME = "test_embeddings"

# Health check timeout
SERVICE_HEALTH_TIMEOUT = 60  # seconds


def _get_worker_id() -> str:
    """Get pytest-xdist worker ID for test isolation.

    Returns worker ID suffix (e.g., 'gw0', 'gw1') or 'master' for non-parallel runs.
    """
    # Get worker ID from environment variable set by pytest-xdist
    return os.environ.get("PYTEST_XDIST_WORKER", "master")


def _check_mongodb_healthy() -> bool:
    """Check if MongoDB test service is healthy."""
    try:
        client = MongoClient(
            TEST_MONGO_URI, serverSelectionTimeoutMS=5000, directConnection=True
        )
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def _check_embedding_service_healthy() -> bool:
    """Check if sentence-transformers service is healthy."""
    try:
        response = httpx.get(f"{TEST_EMBEDDING_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def worker_id_suffix() -> str:
    """Get worker-specific suffix for test isolation.

    Returns worker ID (e.g., 'gw0', 'gw1') or 'master' for non-parallel runs.
    Each pytest-xdist worker gets its own collection namespace to prevent race conditions.
    """
    return _get_worker_id()


@pytest.fixture(scope="session")
def mongo_test_uri() -> str:
    """MongoDB test URI fixture.

    Returns the test MongoDB URI configured for docker-compose test services.
    """
    return TEST_MONGO_URI


@pytest.fixture(scope="session")
def embedding_service_url() -> str:
    """Sentence-transformers service URL fixture.

    Returns the test embedding service URL configured for docker-compose.
    """
    return TEST_EMBEDDING_URL


@pytest.fixture(scope="session")
def wait_for_services() -> Generator[None, None, None]:
    """Wait for test services to be healthy before running tests.

    This session-scoped fixture ensures MongoDB is healthy before tests run.
    It waits up to SERVICE_HEALTH_TIMEOUT seconds for MongoDB to become available.

    The sentence-transformers embedding service is optional - tests that require
    real embeddings will be skipped if the service is not available.

    If MongoDB is not available, pytest.skip() is called to skip all integration
    tests gracefully instead of failing.
    """
    print("\nWaiting for test services to be healthy...")

    # Wait for MongoDB
    start_time = time.time()
    while time.time() - start_time < SERVICE_HEALTH_TIMEOUT:
        if _check_mongodb_healthy():
            print("MongoDB is healthy")
            break
        print(".", end="", flush=True)
        time.sleep(2)
    else:
        pytest.skip(
            f"MongoDB not available - integration tests require MongoDB running at {TEST_MONGO_URI}"
        )

    if _check_embedding_service_healthy():
        print("Sentence-transformers is healthy")
    else:
        print(
            f"Warning: Sentence-transformers service not available at {TEST_EMBEDDING_URL}. "
            "Tests requiring embeddings will be skipped individually."
        )

    print("MongoDB is ready, proceeding with tests\n")
    yield


@pytest.fixture(scope="session")
def real_storage(
    wait_for_services: None, worker_id_suffix: str
) -> Generator[VectorStorage, None, None]:
    """VectorStorage with real MongoDB connection (worker-isolated).

    Each pytest-xdist worker gets its own collection to prevent race conditions.
    Collection name format: test_embeddings_{worker_id} (e.g., test_embeddings_gw0)

    Yields:
        VectorStorage: Connected storage instance for this worker.
    """
    # Dynamic collection name per worker
    collection_name = f"{TEST_COLLECTION_NAME}_{worker_id_suffix}"

    storage = VectorStorage(
        mongo_uri=TEST_MONGO_URI,
        db_name=TEST_DB_NAME,
        collection_name=collection_name,
    )

    try:
        # Ensure index exists
        storage.ensure_index()
        storage._wait_for_index_ready()
        print(
            f"[{worker_id_suffix}] VectorStorage initialized: {TEST_DB_NAME}/{collection_name}"
        )
        yield storage
    finally:
        # Cleanup: delete only this worker's test data at session end
        try:
            storage.delete_all()
            print(f"[{worker_id_suffix}] Cleaned up test data from {collection_name}")
        except Exception as e:
            print(f"[{worker_id_suffix}] Warning: Failed to cleanup: {e}")
        storage.close()


@pytest.fixture(scope="session")
def real_embedding_generator(
    worker_id_suffix: str,
) -> Generator[LocalEmbeddingGenerator, None, None]:
    """Real embedding generator using sentence-transformers service (worker-isolated).

    Each pytest-xdist worker gets its own embedding generator instance to prevent
    race conditions when generating embeddings concurrently.

    Yields:
        LocalEmbeddingGenerator: Connected embedding generator for this worker.
    """
    generator = LocalEmbeddingGenerator(model_name="all-MiniLM-L6-v2")

    try:
        # Validate connection
        if not generator.validate_connection(force=True):
            raise RuntimeError("Failed to validate embedding generator connection")

        print(f"[{worker_id_suffix}] EmbeddingGenerator initialized")
        yield generator
    finally:
        generator.close()


@pytest.fixture
def isolated_storage(
    worker_id_suffix: str,
) -> Generator[VectorStorage, None, None]:
    """Function-scoped isolated storage for tests needing clean state.

    Creates a unique collection per test: test_embeddings_{worker_id}_{test_name}
    Automatically cleans up after the test completes.

    Use this fixture when tests need guaranteed isolation from other parallel tests.

    Yields:
        VectorStorage: Fresh storage instance with empty collection.
    """
    # Get test name for unique collection
    import inspect

    frame = inspect.currentframe()
    if frame and frame.f_back:
        test_name = frame.f_back.f_code.co_name.replace(" ", "_")[:30]
    else:
        test_name = "unknown"

    collection_name = f"{TEST_COLLECTION_NAME}_{worker_id_suffix}_{test_name}"

    storage = VectorStorage(
        mongo_uri=TEST_MONGO_URI,
        db_name=TEST_DB_NAME,
        collection_name=collection_name,
    )

    try:
        storage.ensure_index()
        yield storage
    finally:
        with contextlib.suppress(Exception):
            storage.delete_all()
            storage.close()


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
def worker_isolated_metrics(
    worker_id_suffix: str,
) -> Generator[MetricsCollector, None, None]:
    """MetricsCollector instance isolated per pytest-xdist worker.

    Each worker gets its own MetricsCollector to prevent race conditions
    when tests run in parallel with pytest-xdist (-n 12).

    Args:
        worker_id_suffix: Worker ID from worker_id_suffix fixture.

    Yields:
        MetricsCollector: Fresh metrics instance for this worker.
    """
    metrics = MetricsCollector()
    print(f"[{worker_id_suffix}] Initialized worker-isolated metrics collector")
    yield metrics
    # No cleanup needed for in-memory metrics


@pytest.fixture
def health_check_utils() -> dict[str, Any]:
    """Provide utility functions for checking service health.

    Returns:
        dict: Dictionary with health check functions.
    """
    return {
        "mongodb_healthy": _check_mongodb_healthy,
        "embedding_healthy": _check_embedding_service_healthy,
    }
