# NOTE: Use the `storage_with_mock` fixture from conftest.py to avoid
# ~1s overhead per test. Example:
#     def test_something(self, storage_with_mock):
#         with patch.object(storage_with_mock, "_collection", mock_coll):
#             # test code
"""Tests for storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorage:
    """Tests for VectorStorage class."""

    def test_init_default(self) -> None:
        """Test initialization with defaults."""
        from secondbrain.config import get_config

        get_config.cache_clear()
        with patch("secondbrain.storage.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()
            assert storage.mongo_uri == _test_config.mongo_uri
            assert storage.db_name == "secondbrain_test"
            assert storage.collection_name == "embeddings_test"
            assert storage._index_created is False

    def test_init_custom(self) -> None:
        """Test initialization with custom values."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage(
                mongo_uri=_test_config.mongo_uri,
                db_name="custom_db",
                collection_name="custom_collection",
            )
            assert storage.mongo_uri == _test_config.mongo_uri
            assert storage.db_name == "custom_db"
            assert storage.collection_name == "custom_collection"

    def test_validate_connection_success(self) -> None:
        """Test connection validation when successful."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_client = MagicMock()
            mock_client.admin.command.return_value = {"ok": 1}

            with patch.object(storage, "_client", mock_client):
                assert storage.validate_connection() is True

    def test_validate_connection_failure(self) -> None:
        """Test connection validation when failing."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_client = MagicMock()
            mock_client.admin.command.side_effect = Exception("Connection refused")

            with patch.object(storage, "_client", mock_client):
                assert storage.validate_connection() is False

    def test_ensure_index_success(self) -> None:
        """Test ensure_index sets up for local MongoDB (no Atlas Search)."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with patch.object(storage, "_collection", mock_collection):
                # Local MongoDB does not use Atlas Search indexes
                storage.ensure_index()
                # _index_created is False because we use manual cosine similarity
                assert storage._index_created is False
                # No Atlas Search index creation
                mock_collection.create_search_index.assert_not_called()

    def test_ensure_index_already_created(self) -> None:
        """Test index creation is skipped when already created."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()
            storage._index_created = True

            mock_collection = MagicMock()

            with patch.object(storage, "_collection", mock_collection):
                storage.ensure_index()
                mock_collection.create_search_index.assert_not_called()

    def test_ensure_index_catches_exception(self) -> None:
        """Test index creation catches exceptions and marks as not created."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.create_search_index.side_effect = Exception("Index error")

            with patch.object(storage, "_collection", mock_collection):
                storage.ensure_index()
                assert storage._index_created is False

    def test_store_success(self) -> None:
        """Test storing a document."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.inserted_id = "test_id"

            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                doc = {
                    "chunk_id": "test-chunk",
                    "text": "test text",
                    "embedding": [0.1, 0.2],
                    "metadata": {"source": "test.pdf"},
                }
                result = storage.store(doc)
                assert result == "test_id"
                mock_collection.insert_one.assert_called_once()

    def test_store_connection_error(self) -> None:
        """Test store raises error when connection is invalid."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError),
            ):
                storage.store(
                    {
                        "chunk_id": "test-chunk",
                        "text": "test text",
                        "embedding": [0.1, 0.2],
                        "metadata": {},
                    }
                )

    def test_store_batch_success(self) -> None:
        """Test storing multiple documents."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.inserted_ids = ["id1", "id2"]

            mock_collection = MagicMock()
            mock_collection.insert_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                docs = [
                    {"chunk_id": "chunk1", "text": "text1", "embedding": [0.1]},
                    {"chunk_id": "chunk2", "text": "text2", "embedding": [0.2]},
                ]
                result = storage.store_batch(docs)
                assert result == 2
                mock_collection.insert_many.assert_called_once()

    def test_get_stats_success(self) -> None:
        """Test getting database statistics."""
        from secondbrain.config import get_config

        get_config.cache_clear()
        with patch("secondbrain.storage.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.count_documents.return_value = 10
            mock_collection.distinct.return_value = ["file1.pdf", "file2.pdf"]

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                stats = storage.get_stats()
                assert stats["total_chunks"] == 10
                assert stats["unique_sources"] == 2
                assert stats["database"] == "secondbrain_test"
                assert stats["collection"] == "embeddings_test"

    def test_delete_by_source_success(self) -> None:
        """Test deleting by source file."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 5

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_source("test.pdf")
                assert result == 5
                mock_collection.delete_many.assert_called_once_with(
                    {"source_file": "test.pdf"}
                )

    def test_delete_by_chunk_id_success(self) -> None:
        """Test deleting by chunk ID."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 1

            mock_collection = MagicMock()
            mock_collection.delete_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_chunk_id("chunk-123")
                assert result == 1
                mock_collection.delete_one.assert_called_once_with(
                    {"chunk_id": "chunk-123"}
                )

    def test_delete_all_success(self) -> None:
        """Test deleting all documents."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 100

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_all()
                assert result == 100
                mock_collection.delete_many.assert_called_once_with({})

    def test_list_chunks_success(self) -> None:
        """Test listing chunks with filters."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "chunk1",
                    "source_file": "test.pdf",
                    "page_number": 1,
                    "chunk_text": "text1",
                },
                {
                    "chunk_id": "chunk2",
                    "source_file": "test.pdf",
                    "page_number": 2,
                    "chunk_text": "text2",
                },
            ]

            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                chunks = storage.list_chunks(source_filter="test.pdf", limit=50)
                assert len(chunks) == 2
                assert chunks[0]["chunk_id"] == "chunk1"
                assert chunks[1]["source_file"] == "test.pdf"


class TestStatisticsAndMetadata:
    """Tests for statistics and metadata operations."""

    def test_get_stats_empty_database(self) -> None:
        """Test getting statistics from empty database."""
        from secondbrain.config import get_config

        get_config.cache_clear()
        with patch("secondbrain.storage.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.count_documents.return_value = 0
            mock_collection.distinct.return_value = []

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                stats = storage.get_stats()
                assert stats["total_chunks"] == 0
                assert stats["unique_sources"] == 0
                assert stats["database"] == "secondbrain_test"
                assert stats["collection"] == "embeddings_test"

    def test_get_stats_with_many_sources(self) -> None:
        """Test statistics with many unique sources."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Create 150 unique sources
            many_sources = [f"file{i}.pdf" for i in range(150)]

            mock_collection = MagicMock()
            mock_collection.count_documents.return_value = 500
            mock_collection.distinct.return_value = many_sources

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                stats = storage.get_stats()
                assert stats["total_chunks"] == 500
                assert stats["unique_sources"] == 150

    def test_statistics_consistency(self) -> None:
        """Test that statistics are internally consistent."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.count_documents.return_value = 100
            mock_collection.distinct.return_value = [
                "file1.pdf",
                "file2.pdf",
                "file3.pdf",
            ]

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                stats = storage.get_stats()
                # Total should be >= unique sources (each source has at least 1 chunk)
                assert stats["total_chunks"] >= stats["unique_sources"]

    def test_metadata_ingestion_timestamp(self) -> None:
        """Test that ingestion timestamps are in ISO format."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.inserted_id = "test_id"

            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                doc = {
                    "chunk_id": "test-chunk",
                    "text": "test text",
                    "embedding": [0.1, 0.2],
                    "metadata": {"ingested_at": "2024-01-01T00:00:00+00:00"},
                }
                _ = storage.store(doc)

                # Verify insert_one was called
                call_args = mock_collection.insert_one.call_args
                stored_doc = call_args[0][0]
                assert "ingested_at" in stored_doc["metadata"]
                # Should contain ISO format indicator
                assert "T" in stored_doc["metadata"]["ingested_at"]

    def test_metadata_preservation(self) -> None:
        """Test that metadata survives round-trip through storage."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock the insert and find
            mock_result = MagicMock()
            mock_result.inserted_id = "test_id"

            mock_cursor = MagicMock()
            mock_cursor.__iter__.return_value = [
                {
                    "chunk_id": "test-chunk",
                    "source_file": "test.pdf",
                    "page_number": 1,
                    "chunk_text": "test text",
                }
            ]

            mock_collection = MagicMock()
            mock_collection.insert_one.return_value = mock_result
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Store with custom metadata
                doc = {
                    "chunk_id": "test-chunk",
                    "text": "test text",
                    "embedding": [0.1, 0.2],
                    "metadata": {
                        "custom_field": "custom_value",
                        "numeric_field": 42,
                        "boolean_field": True,
                    },
                }
                _ = storage.store(doc)

                # Verify metadata was passed through
                call_args = mock_collection.insert_one.call_args
                stored_doc = call_args[0][0]
                assert stored_doc["metadata"]["custom_field"] == "custom_value"
                assert stored_doc["metadata"]["numeric_field"] == 42
                assert stored_doc["metadata"]["boolean_field"] is True


class TestIndexReadyTimeout:
    """Tests for index ready timeout scenarios (local MongoDB no-op behavior)."""

    def test_wait_for_index_timeout_after_max_retries(self) -> None:
        """Test that _wait_for_index_ready is a no-op for local MongoDB."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Local MongoDB does not wait for Atlas Search index
                storage._wait_for_index_ready()
                # No calls to list_search_indexes (no Atlas Search)
                mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_success_before_timeout(self) -> None:
        """Test that _wait_for_index_ready succeeds immediately (no-op)."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Completes immediately without checking index status
                storage._wait_for_index_ready()
                # No retry logic for local MongoDB
                mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_retry_logic(self) -> None:
        """Test that no retry logic is used for local MongoDB."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # No retries for local MongoDB
                storage._wait_for_index_ready()
                mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_exception_handling(self) -> None:
        """Test that exceptions are not raised for local MongoDB."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # No exceptions for local MongoDB (no-op)
                storage._wait_for_index_ready()
                mock_collection.list_search_indexes.assert_not_called()

    def test_add_ingestion_timestamp_flat_format(self) -> None:
        """Test _add_ingestion_timestamp with flat ingested_at format."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            doc = {"text": "test", "ingested_at": "2024-01-01T00:00:00Z"}
            result = storage._add_ingestion_timestamp(doc)

            # Should update the flat ingested_at field
            assert "ingested_at" in result
            assert result["ingested_at"] != "2024-01-01T00:00:00Z"
            assert result["text"] == "test"

    def test_add_ingestion_timestamp_nested_format(self) -> None:
        """Test _add_ingestion_timestamp with nested metadata.ingested_at format."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            doc = {"text": "test", "metadata": {"ingested_at": "2024-01-01T00:00:00Z"}}
            result = storage._add_ingestion_timestamp(doc)

            # Should update the nested metadata.ingested_at field
            assert "metadata" in result
            assert result["metadata"]["ingested_at"] != "2024-01-01T00:00:00Z"
            assert result["text"] == "test"

    def test_close_closes_async_client(self) -> None:
        """Test that close method closes async client with suppress."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock async client
            mock_async_client = MagicMock()
            storage._async_client = mock_async_client

            storage.close()

            # Should call close on async client
            mock_async_client.close.assert_called_once()
            assert storage._async_client is None

    def test_close_handles_async_client_error(self) -> None:
        """Test that close suppresses exceptions from async client close."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # Mock async client that raises exception
            mock_async_client = MagicMock()
            mock_async_client.close.side_effect = Exception("Close error")
            storage._async_client = mock_async_client

            # Should not raise
            storage.close()

            assert storage._async_client is None

    def test_list_chunks_exact_match_regex(self) -> None:
        """Test list_chunks with exact match (no prefix) regex on source_file."""
        with patch("secondbrain.storage.config") as mock_config_func:
            from secondbrain.config import Config
            _test_config = Config()
            mock_config_func.return_value.mongo_uri = _test_config.mongo_uri
            mock_config_func.return_value.mongo_db = "secondbrain_test"
            mock_config_func.return_value.mongo_collection = "embeddings_test"
            mock_config_func.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_chunk = {"chunk_id": "1", "source_file": "test.pdf"}
            mock_cursor = MagicMock()
            mock_cursor.skip.return_value = mock_cursor
            mock_cursor.limit.return_value = mock_cursor
            mock_cursor.__iter__.return_value = [mock_chunk]
            
            mock_collection = MagicMock()
            mock_collection.find.return_value = mock_cursor

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Use a filter that won't match prefix but will match exact
                result = storage.list_chunks(source_filter="exact", use_prefix_match=False)

                # Should use exact regex (no ^ prefix)
                call_args = mock_collection.find.call_args[0][0]
                assert "$regex" in call_args["source_file"]
                # Exact match regex should not have ^ prefix
                assert not call_args["source_file"]["$regex"].startswith("^")
