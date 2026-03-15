"""Tests for storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import VectorStorage


@pytest.mark.unit
class TestVectorStorage:
    """Tests for VectorStorage class."""

    def test_search_basic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test basic search functionality using mocked MongoClient."""
        # Use environment-config-based Config via get_config (no patch)
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = [
            {"chunk_id": "1", "score": 0.9},
            {"chunk_id": "2", "score": 0.8},
        ]

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        # Patch the MongoClient constructor to return our mock client
        patcher = patch("secondbrain.storage.MongoClient", return_value=mock_client)
        patcher.start()
        try:
            storage = VectorStorage()
            storage.validate_connection = MagicMock(return_value=True)
            storage._wait_for_index_ready = MagicMock()
            # Mock the collection property to return our mock collection
            storage._collection = mock_collection
            results = storage.search(embedding=[0.1] * 384, top_k=5)
            assert len(results) == 2
        finally:
            patcher.stop()

    def test_search_with_source_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test search with source filter using mocked MongoClient."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        patcher = patch("secondbrain.storage.MongoClient", return_value=mock_client)
        patcher.start()
        try:
            storage = VectorStorage()
            storage.validate_connection = MagicMock(return_value=True)
            storage._wait_for_index_ready = MagicMock()
            # Mock the collection property to return our mock collection
            storage._collection = mock_collection
            results = storage.search(embedding=[0.1] * 384, source_filter="test.pdf")
            assert len(results) == 0
        finally:
            patcher.stop()
