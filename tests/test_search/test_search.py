"""Tests for storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


@pytest.mark.unit
class TestVectorStorage:
    """Tests for VectorStorage class."""

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_init_default(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test initialization with defaults from config (may include auth)."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        storage = VectorStorage()

        assert storage.mongo_uri == mock_config.mongo_uri
        assert storage.db_name == mock_config.mongo_db
        assert storage.collection_name == mock_config.mongo_collection

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

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_validate_connection_success(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test connection validation when successful."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        assert storage.validate_connection() is True

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_validate_connection_failure(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test connection validation when failing."""
        import pymongo.errors

        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = pymongo.errors.ConnectionFailure()
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        assert storage.validate_connection() is False

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_store_success(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test successful document storage."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.insert_one.return_value = MagicMock(inserted_id="test_id")

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        storage.validate_connection = MagicMock(return_value=True)
        result = storage.store(
            {
                "chunk_id": "test",
                "chunk_text": "test text",
                "embedding": [0.1, 0.2],
                "metadata": {"file_type": "test"},
            }
        )
        assert result == "test_id"

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_store_connection_error(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test store raises when connection fails."""
        import pymongo.errors

        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = pymongo.errors.ConnectionFailure()
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        with pytest.raises(StorageConnectionError):
            storage.store({"chunk_id": "test", "embedding": [0.1]})

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_store_batch(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test batch document storage."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_search_basic(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test basic search functionality."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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
        storage.validate_connection = MagicMock(return_value=True)
        storage._wait_for_index_ready = MagicMock()
        results = storage.search(embedding=[0.1] * 384, top_k=5)
        assert len(results) == 2

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_search_with_source_filter(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test search with source filter."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = []

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        storage.validate_connection = MagicMock(return_value=True)
        storage._wait_for_index_ready = MagicMock()
        results = storage.search(embedding=[0.1] * 384, source_filter="test.pdf")
        assert len(results) == 0
        mock_collection.aggregate.assert_called_once()

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_ensure_index_mongodb8_syntax(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test vector search index creation uses MongoDB 8.0+ syntax."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {}

        mock_collection = MagicMock()
        mock_collection.create_search_index = MagicMock()

        mock_db = MagicMock()
        mock_db.__getitem__ = lambda self, key: mock_collection

        mock_client.__getitem__ = lambda self, key: mock_db
        mock_client_class.return_value = mock_client

        storage = VectorStorage()
        storage.ensure_index()

        mock_collection.create_search_index.assert_called_once()

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_delete_by_source(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test deleting by source file."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_delete_chunk_id(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test deleting by chunk ID."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_delete_all(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test deleting all documents."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_get_stats(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test getting database statistics."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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
        assert stats["database"] == "test_secondbrain"
        assert stats["collection"] == "test_embeddings"

    @patch("secondbrain.storage.get_config")
    @patch("secondbrain.storage.MongoClient")
    def test_list_chunks_basic(
        self, mock_client_class: MagicMock, mock_get_config: MagicMock
    ) -> None:
        """Test listing chunks."""
        from secondbrain.config import Config

        mock_config = Config()
        mock_get_config.return_value = mock_config

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
        assert isinstance(results, list)
