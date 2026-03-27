"""Shared fixtures for storage tests."""

from collections.abc import Generator
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import VectorStorage


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
