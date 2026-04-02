"""Shared fixtures for storage tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


from secondbrain.storage import VectorStorage


@pytest.fixture(scope="session")
def mongo_client_storage() -> Generator[Any, None, None]:
    """Session-scoped MongoDB client for storage tests.

    Creates a single MongoDB client per test session to reduce
    connection overhead. Used by session-scoped storage fixtures.
    """
    from pymongo import MongoClient

    client = MongoClient(
        "mongodb://localhost:27017",
        serverSelectionTimeoutMS=5000,
        socketTimeoutMS=2000,
        connectTimeoutMS=2000,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def test_storage_db(mongo_client_storage: Any) -> Generator[Any, None, None]:
    """Session-scoped test database for storage tests.

    Creates a single test database per session for storage tests,
    reducing database creation overhead across all storage test modules.
    """
    db = mongo_client_storage["test_storage_secondbrain"]
    yield db
    mongo_client_storage.drop_database("test_storage_secondbrain")


@pytest.fixture(scope="module")
def mock_storage_config() -> MagicMock:
    """Module-scoped mock config to avoid repeated Config initialization."""
    config = MagicMock()
    config.mongo_uri = "mongodb://localhost:27017"
    config.mongo_db = "secondbrain"
    config.mongo_collection = "embeddings"
    config.embedding_dimensions = 384
    return config


@pytest.fixture(scope="module")
def storage_with_mock(mock_storage_config: MagicMock) -> Generator[Any, None, None]:
    """Module-scoped VectorStorage instance to avoid 1s+ overhead per test.

    This fixture creates a single VectorStorage instance with mocked config
    that can be reused across all tests in a module. Tests should use this
    fixture instead of creating their own VectorStorage instances.

    Example:
        def test_something(self, storage_with_mock):
            with patch.object(storage_with_mock, "_collection", mock_collection):
                # test code
    """
    with patch("secondbrain.storage.sync.get_config", return_value=mock_storage_config):
        storage = VectorStorage()
        yield storage
