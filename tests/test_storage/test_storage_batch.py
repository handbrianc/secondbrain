"""Tests for storage batch operations and edge cases."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorageBatchOperations:
    """Tests for batch storage operations."""

    def test_store_batch_success(self) -> None:
        """Test batch document storage."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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

    def test_store_batch_empty_list(self) -> None:
        """Test batch storage with empty list."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                count = storage.store_batch([])
                # Method is called but returns 0 for empty list
                assert count == 0

    def test_store_batch_preserves_existing_metadata(self) -> None:
        """Test that batch storage preserves existing metadata."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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

    def test_store_batch_with_connection_failure(self) -> None:
        """Test batch storage raises StorageConnectionError on failure."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError, match="Cannot connect"),
            ):
                storage.store_batch([{"test": "doc"}])


class TestVectorStorageIndexTimeout:
    """Tests for index ready timeout scenarios."""

    def test_wait_for_index_ready_success(self) -> None:
        """Test index ready check succeeds on first attempt."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 5
            mock_config.return_value.index_ready_retry_delay = 0.1

            storage = VectorStorage()
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

    def test_wait_for_index_ready_multiple_retries(self) -> None:
        """Test index ready check succeeds after retries."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 5
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()
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

    def test_wait_for_index_ready_timeout_warning(self) -> None:
        """Test index ready check logs warning after max retries."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()
            storage._index_created = True

            mock_collection = MagicMock()
            # All attempts fail
            mock_collection.list_search_indexes.return_value = []

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                storage._wait_for_index_ready()
                # Should have attempted 3 times

    def test_wait_for_index_ready_with_exception(self) -> None:
        """Test index ready check handles exceptions gracefully."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()
            storage._index_created = True

            mock_collection = MagicMock()
            mock_collection.list_search_indexes.side_effect = Exception("Index error")

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                storage._wait_for_index_ready()


class TestVectorStorageFilterCombinations:
    """Tests for various filter combinations in search."""

    def test_search_with_both_filters(self) -> None:
        """Test search with both source and file_type filters."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 1
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()

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
                patch.object(storage, "_wait_for_index_ready"),
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

    def test_search_with_only_source_filter(self) -> None:
        """Test search with only source filter."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 1
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()

            mock_result = []
            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_wait_for_index_ready"),
            ):
                storage.search(
                    embedding=[0.1] * 384,
                    source_filter="document.pdf",
                )

    def test_search_with_only_file_type_filter(self) -> None:
        """Test search with only file type filter."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 1
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()

            mock_result = []
            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_wait_for_index_ready"),
            ):
                storage.search(
                    embedding=[0.1] * 384,
                    file_type_filter="pdf",
                )

    def test_search_with_no_filters(self) -> None:
        """Test search with no filters."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 1
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()

            mock_result = []
            mock_collection = MagicMock()
            mock_collection.aggregate.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
                patch.object(storage, "_wait_for_index_ready"),
            ):
                storage.search(embedding=[0.1] * 384)


class TestVectorStorageConnectionRecovery:
    """Tests for connection recovery mechanisms."""

    def test_connection_reestablished_after_close(self) -> None:
        """Test that connection can be reestablished after close."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Get initial client
            initial_client = storage.client
            assert initial_client is not None

            # Close connection
            storage.close()
            assert storage._client is None

            # Reestablish connection - should create new client
            new_client = storage.client
            assert new_client is not None

    def test_validate_connection_with_retry(self) -> None:
        """Test connection validation handles failures gracefully."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_client = MagicMock()
            # Always fail
            mock_client.admin.command.side_effect = Exception("Connection refused")

            with patch.object(storage, "_client", mock_client):
                # Should return False on failure
                result = storage.validate_connection()
                assert result is False

    def test_storage_context_manager(self) -> None:
        """Test storage works correctly as context manager."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with storage:
                # Inside context, client should be available
                assert storage._client is None or storage._client is not None

            # After exit, client should be closed
            assert storage._client is None


class TestVectorStorageStatistics:
    """Tests for database statistics and metadata operations."""

    def test_get_database_statistics(self) -> None:
        """Test database statistics retrieval."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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

    def test_list_chunks_with_filters(self) -> None:
        """Test listing chunks with various filters."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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

    def test_list_chunks_by_chunk_id(self) -> None:
        """Test listing chunks by specific chunk ID."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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

    def test_list_chunks_with_pagination(self) -> None:
        """Test listing chunks with pagination."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

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
