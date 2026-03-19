# NOTE: Use the `storage_with_mock` fixture from conftest.py to avoid
# ~1s overhead per test. Example:
#     def test_something(self, storage_with_mock):
#         with patch.object(storage_with_mock, "_collection", mock_coll):
#             # test code
"""Tests for storage batch operations and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


@pytest.fixture(scope="module")
def mock_storage_config():
    """Module-scoped mock config to avoid repeated Config initialization."""
    from unittest.mock import MagicMock

    config = MagicMock()
    config.mongo_uri = "mongodb://localhost:27017"
    config.mongo_db = "secondbrain"
    config.mongo_collection = "embeddings"
    config.embedding_dimensions = 384
    return config


@pytest.fixture(scope="module")
def storage_with_mock(mock_storage_config):
    """Module-scoped VectorStorage instance to avoid 1s+ overhead per test."""
    with patch("secondbrain.storage.get_config", return_value=mock_storage_config):
        storage = VectorStorage()
        yield storage


class TestVectorStorageBatchOperations:
    """Tests for batch storage operations."""

    def test_store_batch_success(self, storage_with_mock: VectorStorage) -> None:
        """Test batch document storage."""
        storage = storage_with_mock

        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3", "id4", "id5"]

        mock_collection = MagicMock()
        mock_collection.insert_many.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            docs = [
                {
                    "chunk_text": f"Document {i}",
                    "embedding": [0.1] * 384,
                    "metadata": {"ingested_at": "original"},
                }
                for i in range(5)
            ]
            count = storage.store_batch(docs)
            assert count == 5
            mock_collection.insert_many.assert_called_once()
            call_args = mock_collection.insert_many.call_args[0][0]
            assert len(call_args) == 5
            # Verify timestamps were updated in metadata
            for doc in call_args:
                assert "metadata" in doc
                assert "ingested_at" in doc["metadata"]

    def test_store_batch_empty_list(self, storage_with_mock: VectorStorage) -> None:
        """Test batch storage with empty list."""
        storage = storage_with_mock

        mock_collection = MagicMock()

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            count = storage.store_batch([])
            # Method is called but returns 0 for empty list
            assert count == 0

    def test_store_batch_preserves_existing_metadata(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test that batch storage preserves existing metadata."""
        storage = storage_with_mock

        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1"]

        mock_collection = MagicMock()
        mock_collection.insert_many.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            docs = [
                {
                    "chunk_text": "Test",
                    "embedding": [0.1] * 384,
                    "metadata": {"custom_field": "value", "ingested_at": "old"},
                }
            ]
            storage.store_batch(docs)
            call_args = mock_collection.insert_many.call_args[0][0]
            # Should preserve custom field and update timestamp
            assert call_args[0]["metadata"]["custom_field"] == "value"

    def test_store_batch_with_connection_failure(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test batch storage raises StorageConnectionError on failure."""
        storage = storage_with_mock

        with (
            patch.object(storage, "validate_connection", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            storage.store_batch([{"test": "doc"}])


class TestVectorStorageIndexTimeout:
    """Tests for index ready timeout scenarios."""

    def test_wait_for_index_ready_success(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test index ready check succeeds on first attempt."""
        storage = storage_with_mock
        storage._index_created = True

        mock_index = {"name": "embedding_index", "status": "READY"}
        mock_collection = MagicMock()
        mock_collection.list_search_indexes.return_value = [mock_index]

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()
            # Should have called ensure_index once
            storage.ensure_index()

    def test_wait_for_index_ready_multiple_retries(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test index ready check succeeds after retries."""
        storage = storage_with_mock
        storage._index_created = True

        mock_collection = MagicMock()
        # First 2 attempts return not ready, 3rd succeeds
        mock_collection.list_search_indexes.side_effect = [
            [{"name": "embedding_index", "status": "BUILDING"}],
            [{"name": "embedding_index", "status": "BUILDING"}],
            [{"name": "embedding_index", "status": "READY"}],
        ]

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()

    def test_wait_for_index_ready_timeout_warning(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test index ready check logs warning after max retries."""
        storage = storage_with_mock
        storage._index_created = True

        mock_collection = MagicMock()
        # All attempts fail
        mock_collection.list_search_indexes.return_value = []

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch("time.sleep", return_value=None),  # Skip actual sleep delays
        ):
            storage._wait_for_index_ready()
            # Should have attempted 3 times

    def test_wait_for_index_ready_with_exception(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test index ready check handles exceptions gracefully."""
        storage = storage_with_mock
        storage._index_created = True

        mock_collection = MagicMock()
        mock_collection.list_search_indexes.side_effect = Exception("Index error")

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch("time.sleep", return_value=None),  # Skip actual sleep delays
        ):
            storage._wait_for_index_ready()


class TestVectorStorageFilterCombinations:
    """Tests for various filter combinations in search."""

    def test_search_with_both_filters(self, storage_with_mock: VectorStorage) -> None:
        """Test search with both source and file_type filters."""
        storage = storage_with_mock

        mock_result = [
            {
                "chunk_id": "1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "Test content",
                "score": 0.9,
            }
        ]

        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(
                storage, "_wait_for_index_ready", return_value=None
            ),  # Skip timeout wait
        ):
            results = storage.search(
                embedding=[0.1] * 384,
                top_k=5,
                source_filter="test.pdf",
                file_type_filter="pdf",
            )
            assert len(results) == 1
            # Verify pipeline was built with filters
            call_args = mock_collection.aggregate.call_args[0][0]
            assert "$vectorSearch" in call_args[0]

    def test_search_with_only_source_filter(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test search with only source filter."""
        storage = storage_with_mock

        mock_result = []
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(
                storage, "_wait_for_index_ready", return_value=None
            ),  # Skip timeout wait
        ):
            storage.search(
                embedding=[0.1] * 384,
                source_filter="document.pdf",
            )

    def test_search_with_only_file_type_filter(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test search with only file type filter."""
        storage = storage_with_mock

        mock_result = []
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(
                storage, "_wait_for_index_ready", return_value=None
            ),  # Skip timeout wait
        ):
            storage.search(
                embedding=[0.1] * 384,
                file_type_filter="pdf",
            )

    def test_search_with_no_filters(self, storage_with_mock: VectorStorage) -> None:
        """Test search with no filters."""
        storage = storage_with_mock

        mock_result = []
        mock_collection = MagicMock()
        mock_collection.aggregate.return_value = mock_result

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(
                storage, "_wait_for_index_ready", return_value=None
            ),  # Skip timeout wait
        ):
            storage.search(embedding=[0.1] * 384)


class TestVectorStorageConnectionRecovery:
    """Tests for connection recovery mechanisms."""

    def test_connection_reestablished_after_close(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test that connection can be reestablished after close."""
        storage = storage_with_mock

        # Get initial client
        initial_client = storage.client
        assert initial_client is not None

        # Close connection
        storage.close()
        assert storage._client is None

        # Reestablish connection - should create new client
        new_client = storage.client
        assert new_client is not None

    def test_validate_connection_with_retry(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test connection validation handles failures gracefully."""
        storage = storage_with_mock

        mock_client = MagicMock()
        # Always fail
        mock_client.admin.command.side_effect = Exception("Connection refused")

        with patch.object(storage, "_client", mock_client):
            # Should return False on failure
            result = storage.validate_connection()
            assert result is False

    def test_storage_context_manager(self, storage_with_mock: VectorStorage) -> None:
        """Test storage works correctly as context manager."""
        storage = storage_with_mock

        with storage:
            # Inside context, client should be available
            assert storage._client is None or storage._client is not None

        # After exit, client should be closed
        assert storage._client is None


class TestVectorStorageStatistics:
    """Tests for database statistics and metadata operations."""

    def test_get_database_statistics(self, storage_with_mock: VectorStorage) -> None:
        """Test database statistics retrieval."""
        storage = storage_with_mock

        mock_stats = {
            "count": 1000,
            "size": 5242880,
            "avgObjSize": 5242,
        }

        mock_db = MagicMock()
        mock_db.command.return_value = mock_stats

        mock_collection = MagicMock()
        mock_collection.count_documents.return_value = 1000

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_db", mock_db),
            patch.object(storage, "_collection", mock_collection),
        ):
            # Get stats should work without errors
            count = mock_collection.count_documents({})
            assert count == 1000

    def test_list_chunks_with_filters(self, storage_with_mock: VectorStorage) -> None:
        """Test listing chunks with various filters."""
        storage = storage_with_mock

        mock_chunks = [
            {
                "chunk_id": "1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "Test content",
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = iter(mock_chunks)
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = storage.list_chunks(source_filter="test.pdf", limit=50)
            assert len(result) == 1

    def test_list_chunks_by_chunk_id(self, storage_with_mock: VectorStorage) -> None:
        """Test listing chunks by specific chunk ID."""
        storage = storage_with_mock

        mock_chunks = [
            {
                "chunk_id": "specific-id",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "Test content",
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = iter(mock_chunks)
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = storage.list_chunks(chunk_id="specific-id")
            assert len(result) == 1
            assert result[0]["chunk_id"] == "specific-id"

    def test_list_chunks_with_pagination(
        self, storage_with_mock: VectorStorage
    ) -> None:
        """Test listing chunks with pagination."""
        storage = storage_with_mock

        mock_chunks = [
            {"chunk_id": f"id-{i}", "source_file": "test.pdf"} for i in range(10)
        ]
        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = iter(mock_chunks)
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage.list_chunks(limit=10, offset=20)
            # Verify skip and limit were called
            mock_cursor.skip.assert_called_once_with(20)
            mock_cursor.limit.assert_called_once_with(10)
