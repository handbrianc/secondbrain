"""Tests for storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorage:
    """Tests for VectorStorage class."""

    def test_init_default(self) -> None:
        """Test initialization with defaults."""
        storage = VectorStorage()
        assert storage.mongo_uri == "mongodb://localhost:27017"
        assert storage.db_name == "secondbrain"
        assert storage.collection_name == "embeddings"

    def test_init_custom(self) -> None:
        """Test initialization with custom values."""
        storage = VectorStorage(
            mongo_uri="mongodb://custom:27017",
            db_name="custom_db",
            collection_name="custom_collection",
        )
        assert storage.mongo_uri == "mongodb://custom:27017"
        assert storage.db_name == "custom_db"
        assert storage.collection_name == "custom_collection"

    @patch("secondbrain.storage.MongoClient")
    def test_validate_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test connection validation when successful."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        assert storage.validate_connection() is True

    @patch("secondbrain.storage.MongoClient")
    def test_validate_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test connection validation when failing."""
        import pymongo.errors

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = pymongo.errors.ConnectionFailure()
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        assert storage.validate_connection() is False

    @patch("secondbrain.storage.MongoClient")
    def test_store_success(self, mock_client_class: MagicMock) -> None:
        """Test successful document storage."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="test_id")

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: (
            mock_collection if key == "embeddings" else None
        )

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        result = storage.store(
            {
                "chunk_id": "test",
                "chunk_text": "test text",
                "embedding": [0.1, 0.2],
                "metadata": {"file_type": "test"},
            }
        )
        assert result == "test_id"

    @patch("secondbrain.storage.MongoClient")
    def test_store_connection_error(self, mock_client_class: MagicMock) -> None:
        """Test store raises when connection fails."""
        import pymongo.errors

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = pymongo.errors.ConnectionFailure()
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        with pytest.raises(StorageConnectionError):
            storage.store({"chunk_id": "test", "embedding": [0.1]})

    @patch("secondbrain.storage.MongoClient")
    def test_store_batch(self, mock_client_class: MagicMock) -> None:
        """Test batch document storage."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.insert_many.return_value = MagicMock(
            inserted_ids=["id1", "id2"]
        )

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        docs = [
            {"chunk_id": "1", "embedding": [0.1]},
            {"chunk_id": "2", "embedding": [0.2]},
        ]
        result = storage.store_batch(docs)
        assert result == 2

    @patch("secondbrain.storage.MongoClient")
    def test_search_basic(self, mock_client_class: MagicMock) -> None:
        """Test basic search functionality."""
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
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        results = storage.search(embedding=[0.1] * 384, top_k=5)
        assert len(results) == 2

    @patch("secondbrain.storage.MongoClient")
    def test_search_with_source_filter(self, mock_client_class: MagicMock) -> None:
        """Test search with source filter."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        results = storage.search(embedding=[0.1] * 384, source_filter="test.pdf")
        assert len(results) == 0
        # Verify aggregate was called
        mock_collection.aggregate.assert_called_once()

    @patch("secondbrain.storage.MongoClient")
    def test_delete_by_source(self, mock_client_class: MagicMock) -> None:
        """Test deleting by source file."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.delete_many.return_value = MagicMock(deleted_count=5)

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        result = storage.delete_by_source("test.pdf")
        assert result == 5

    @patch("secondbrain.storage.MongoClient")
    def test_delete_by_chunk_id(self, mock_client_class: MagicMock) -> None:
        """Test deleting by chunk ID."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.delete_one.return_value = MagicMock(deleted_count=1)

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        result = storage.delete_by_chunk_id("chunk-123")
        assert result == 1

    @patch("secondbrain.storage.MongoClient")
    def test_delete_all(self, mock_client_class: MagicMock) -> None:
        """Test deleting all documents."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.delete_many.return_value = MagicMock(deleted_count=100)

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        result = storage.delete_all()
        assert result == 100

    @patch("secondbrain.storage.MongoClient")
    def test_get_stats(self, mock_client_class: MagicMock) -> None:
        """Test getting database statistics."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 50
        mock_collection.distinct.return_value = ["file1.pdf", "file2.pdf"]

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        stats = storage.get_stats()
        assert stats["total_chunks"] == 50
        assert stats["unique_sources"] == 2
        assert stats["database"] == "secondbrain"
        assert stats["collection"] == "embeddings"

    @patch("secondbrain.storage.MongoClient")
    def test_list_chunks_basic(self, mock_client_class: MagicMock) -> None:
        """Test listing chunks."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.find.return_value.skip.return_value.limit.return_value = iter(
            [
                {
                    "chunk_id": "1",
                    "source_file": "test.pdf",
                    "chunk_text": "test",
                    "page_number": 1,
                },
                {
                    "chunk_id": "2",
                    "source_file": "test.pdf",
                    "chunk_text": "test2",
                    "page_number": 2,
                },
            ]
        )

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        results = storage.list_chunks()
        # Note: mock returns iterator
        assert isinstance(results, list)
