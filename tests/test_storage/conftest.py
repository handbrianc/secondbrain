"""Shared fixtures for storage tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import os
import pytest

from secondbrain.storage import VectorStorage


@pytest.fixture(scope="module")
def mock_storage_config() -> MagicMock:
    """Module-scoped mock config to avoid repeated Config initialization."""
    config = MagicMock()
    config.mongo_uri = os.environ.get(
        "SECONDBRAIN_MONGO_URI",
        "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin",
    )
    config.mongo_db = os.environ.get("SECONDBRAIN_MONGO_DB", "secondbrain_test")
    config.mongo_collection = os.environ.get("SECONDBRAIN_MONGO_COLLECTION", "embeddings_test")
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
    with patch("secondbrain.storage.get_config", return_value=mock_storage_config):
        storage = VectorStorage()
        yield storage
        storage._client = None
        storage._db = None
        storage._collection = None
        storage._async_client = None
        storage._index_created = False
        storage.invalidate_connection_cache()
