"""Shared fixtures for storage tests.

All storage tests use a local-mode (in-memory) Qdrant backend via
``QdrantClient(":memory:")`` so they run with no external server while still
exercising the real Qdrant client API.
"""

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage

EMBEDDING_DIMENSIONS = 384


@pytest.fixture(scope="module")
def mock_storage_config() -> MagicMock:
    """Module-scoped mock config to avoid repeated Config initialization."""
    config = MagicMock()
    config.storage_backend = "qdrant"
    config.qdrant_url = "http://localhost:6333"
    config.qdrant_api_key = None
    config.qdrant_collection = "test_embeddings"
    config.embedding_dimensions = EMBEDDING_DIMENSIONS
    return config


@pytest.fixture(scope="module")
def storage() -> Generator[QdrantVectorStorage]:
    """Module-scoped local-mode Qdrant storage for public-API storage tests.

    Creates a single QdrantVectorStorage backed by an in-memory Qdrant client
    that can be reused across all tests in a module.
    """
    instance = QdrantVectorStorage(collection_name="test_embeddings")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = EMBEDDING_DIMENSIONS
    yield instance
    instance.close()
