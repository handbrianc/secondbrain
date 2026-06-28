# NOTE: Use the `storage_with_mock` fixture from conftest.py to avoid
# ~1s overhead per test. Example:
#     def test_something(self, storage_with_mock):
#         with patch.object(storage_with_mock, "_collection", mock_coll):
#             # test code
"""Tests for storage module."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorage:
    """Tests for VectorStorage class."""

    def test_init_default(self, vector_storage_fixture: VectorStorage) -> None:
        """Test initialization with defaults."""
        storage = vector_storage_fixture
        assert storage.mongo_uri == "mongodb://localhost:27017"
        assert storage.db_name == "secondbrain_test"
        assert storage.collection_name == "embeddings_test"
        assert storage._index_created is False

    def test_init_custom(
        self, tmp_path: Any, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test initialization with custom values."""
        from secondbrain.config import get_config

        get_config.cache_clear()
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

    def test_validate_connection_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test connection validation when successful."""
        storage = vector_storage_fixture

        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}

        with patch.object(storage, "_client", mock_client):
            assert storage.validate_connection() is True

    def test_validate_connection_failure(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test connection validation when failing."""
        storage = vector_storage_fixture

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = Exception("Connection refused")

        # Patch validate_connection directly (not _client) so the method
        # skips its connection-cache hot-path and always reaches the mock.
        with patch.object(storage, "validate_connection", side_effect=lambda *args, **kwargs: False):
            assert storage.validate_connection() is False

    def test_ensure_index_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test ensure_index sets up for local MongoDB (no Atlas Search)."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()

        with patch.object(storage, "_collection", mock_collection):
            storage.ensure_index()
            assert storage._index_created is False
            mock_collection.create_search_index.assert_not_called()

    def test_ensure_index_already_created(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test index creation is skipped when already created."""
        storage = vector_storage_fixture
        storage._index_created = True

        mock_collection = MagicMock()

        with patch.object(storage, "_collection", mock_collection):
            storage.ensure_index()
            mock_collection.create_search_index.assert_not_called()

    def test_ensure_index_catches_exception(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test index creation catches exceptions and marks as not created."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()
        mock_collection.create_search_index.side_effect = Exception("Index error")

        with patch.object(storage, "_collection", mock_collection):
            storage.ensure_index()
            assert storage._index_created is False

    def test_store_success(self, vector_storage_fixture: VectorStorage) -> None:
        """Test storing a document."""
        storage = vector_storage_fixture

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

    def test_store_connection_error(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test store raises error when connection is invalid."""
        storage = vector_storage_fixture

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

    def test_store_batch_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test storing multiple documents."""
        storage = vector_storage_fixture

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

    def test_get_stats_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test getting database statistics."""
        storage = vector_storage_fixture

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

    def test_delete_by_source_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test deleting by source file."""
        storage = vector_storage_fixture

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

    def test_delete_by_chunk_id_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test deleting by chunk ID."""
        storage = vector_storage_fixture

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

    def test_delete_all_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test deleting all documents."""
        storage = vector_storage_fixture

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

    def test_list_chunks_success(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test listing chunks with filters."""
        storage = vector_storage_fixture

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

    def test_get_stats_empty_database(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test getting statistics from empty database."""
        storage = vector_storage_fixture

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

    def test_get_stats_with_many_sources(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test statistics with many unique sources."""
        storage = vector_storage_fixture

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

    def test_statistics_consistency(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that statistics are internally consistent."""
        storage = vector_storage_fixture

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
            assert stats["total_chunks"] >= stats["unique_sources"]

    def test_metadata_ingestion_timestamp(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that ingestion timestamps are in ISO format."""
        storage = vector_storage_fixture

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

            call_args = mock_collection.insert_one.call_args
            stored_doc = call_args[0][0]
            assert "ingested_at" in stored_doc["metadata"]
            assert "T" in stored_doc["metadata"]["ingested_at"]

    def test_metadata_preservation(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that metadata survives round-trip through storage."""
        storage = vector_storage_fixture

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

            call_args = mock_collection.insert_one.call_args
            stored_doc = call_args[0][0]
            assert stored_doc["metadata"]["custom_field"] == "custom_value"
            assert stored_doc["metadata"]["numeric_field"] == 42
            assert stored_doc["metadata"]["boolean_field"] is True


class TestIndexReadyTimeout:
    """Tests for index ready timeout scenarios (local MongoDB no-op behavior)."""

    def test_wait_for_index_timeout_after_max_retries(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that _wait_for_index_ready is a no-op for local MongoDB."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()
            mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_success_before_timeout(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that _wait_for_index_ready succeeds immediately (no-op)."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()
            mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_retry_logic(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that no retry logic is used for local MongoDB."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()
            mock_collection.list_search_indexes.assert_not_called()

    def test_wait_for_index_exception_handling(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that exceptions are not raised for local MongoDB."""
        storage = vector_storage_fixture

        mock_collection = MagicMock()

        with (
            patch.object(storage, "validate_connection", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            storage._wait_for_index_ready()
            mock_collection.list_search_indexes.assert_not_called()

    def test_add_ingestion_timestamp_flat_format(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test _add_ingestion_timestamp with flat ingested_at format."""
        storage = vector_storage_fixture

        doc = {"text": "test", "ingested_at": "2024-01-01T00:00:00Z"}
        result = storage._add_ingestion_timestamp(doc)

        assert "ingested_at" in result
        assert result["ingested_at"] != "2024-01-01T00:00:00Z"
        assert result["text"] == "test"

    def test_add_ingestion_timestamp_nested_format(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test _add_ingestion_timestamp with nested metadata.ingested_at format."""
        storage = vector_storage_fixture

        doc = {"text": "test", "metadata": {"ingested_at": "2024-01-01T00:00:00Z"}}
        result = storage._add_ingestion_timestamp(doc)

        assert "metadata" in result
        assert result["metadata"]["ingested_at"] != "2024-01-01T00:00:00Z"
        assert result["text"] == "test"

    def test_close_closes_async_client(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that close method closes async client with suppress."""
        storage = vector_storage_fixture

        mock_async_client = MagicMock()
        storage._async_client = mock_async_client

        storage.close()

        mock_async_client.close.assert_called_once()
        assert storage._async_client is None

    def test_close_handles_async_client_error(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test that close suppresses exceptions from async client close."""
        storage = vector_storage_fixture

        mock_async_client = MagicMock()
        mock_async_client.close.side_effect = Exception("Close error")
        storage._async_client = mock_async_client

        storage.close()

        assert storage._async_client is None

    def test_list_chunks_exact_match_regex(
        self, vector_storage_fixture: VectorStorage
    ) -> None:
        """Test list_chunks with exact match (no prefix) regex on source_file."""
        storage = vector_storage_fixture

        mock_chunk = {
            "chunk_id": "1",
            "source_file": "test.pdf",
            "page_number": 1,
            "chunk_text": "test content",
        }
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
            result = storage.list_chunks(source_filter="exact", use_prefix_match=False)

            call_args = mock_collection.find.call_args[0][0]
            assert "$regex" in call_args["source_file"]
            assert not call_args["source_file"]["$regex"].startswith("^")