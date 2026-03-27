"""Tests for delete operations in VectorStorage."""

# NOTE: Use the `storage_with_mock` fixture from conftest.py to avoid
# ~1s overhead per test. Example:
#     def test_something(self, storage_with_mock):
#         with patch.object(storage_with_mock, "_collection", mock_coll):
#             # test code
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestDeleteBySource:
    """Test suite for delete by source operations."""

    def test_delete_by_source_success(self) -> None:
        """Test that delete by source successfully removes documents."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

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

    def test_delete_by_source_no_matches(self) -> None:
        """Test that delete by source returns 0 when no matches found."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 0

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_source("nonexistent.pdf")
                assert result == 0
                mock_collection.delete_many.assert_called_once_with(
                    {"source_file": "nonexistent.pdf"}
                )

    def test_delete_by_source_connection_failure(self) -> None:
        """Test that delete by source raises StorageConnectionError on failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError) as exc_info,
            ):
                storage.delete_by_source("test.pdf")

            assert "Cannot connect to MongoDB" in str(exc_info.value)
            assert "delete by source" in str(exc_info.value)

    def test_delete_by_source_large_batch(self) -> None:
        """Test that delete by source handles large batches correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 1000

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_source("large_file.pdf")
                assert result == 1000


class TestDeleteByChunkId:
    """Test suite for delete by chunk ID operations."""

    def test_delete_by_chunk_id_success(self) -> None:
        """Test that delete by chunk ID successfully removes a document."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

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

    def test_delete_by_chunk_id_not_found(self) -> None:
        """Test that delete by chunk ID returns 0 when not found."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 0

            mock_collection = MagicMock()
            mock_collection.delete_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_chunk_id("nonexistent-chunk")
                assert result == 0
                mock_collection.delete_one.assert_called_once_with(
                    {"chunk_id": "nonexistent-chunk"}
                )

    def test_delete_by_chunk_id_connection_failure(self) -> None:
        """Test that delete by chunk ID raises StorageConnectionError on failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError) as exc_info,
            ):
                storage.delete_by_chunk_id("chunk-123")

            assert "Cannot connect to MongoDB" in str(exc_info.value)
            assert "delete by chunk ID" in str(exc_info.value)

    def test_delete_by_chunk_id_uuid_format(self) -> None:
        """Test that delete by chunk ID handles UUID format correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 1

            mock_collection = MagicMock()
            mock_collection.delete_one.return_value = mock_result

            uuid_chunk_id = "550e8400-e29b-41d4-a716-446655440000"

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_chunk_id(uuid_chunk_id)
                assert result == 1
                mock_collection.delete_one.assert_called_once_with(
                    {"chunk_id": uuid_chunk_id}
                )


class TestDeleteAll:
    """Test suite for delete all operations."""

    def test_delete_all_success(self) -> None:
        """Test that delete all successfully removes all documents."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

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

    def test_delete_all_empty_database(self) -> None:
        """Test that delete all returns 0 on empty database."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 0

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_all()
                assert result == 0
                mock_collection.delete_many.assert_called_once_with({})

    def test_delete_all_connection_failure(self) -> None:
        """Test that delete all raises StorageConnectionError on failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError) as exc_info,
            ):
                storage.delete_all()

            assert "Cannot connect to MongoDB" in str(exc_info.value)
            assert "delete all" in str(exc_info.value)

    def test_delete_all_large_dataset(self) -> None:
        """Test that delete all handles large datasets correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 50000

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_all()
                assert result == 50000


class TestDeleteEdgeCases:
    """Test suite for delete operation edge cases."""

    def test_delete_by_source_with_special_characters(self) -> None:
        """Test that delete by source handles special characters correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 3

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_source("/path/with spaces/file.pdf")
                assert result == 3
                mock_collection.delete_many.assert_called_once_with(
                    {"source_file": "/path/with spaces/file.pdf"}
                )

    def test_delete_by_chunk_id_empty_string(self) -> None:
        """Test that delete by chunk ID handles empty string correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 0

            mock_collection = MagicMock()
            mock_collection.delete_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = storage.delete_by_chunk_id("")
                assert result == 0
                mock_collection.delete_one.assert_called_once_with({"chunk_id": ""})

    def test_delete_operations_return_int_type(self) -> None:
        """Test that delete operations return int type."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 5

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result
            mock_collection.delete_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result1 = storage.delete_by_source("test.pdf")
                result2 = storage.delete_by_chunk_id("chunk-1")
                result3 = storage.delete_all()

                assert isinstance(result1, int)
                assert isinstance(result2, int)
                assert isinstance(result3, int)


class TestAsyncDeleteOperations:
    """Test suite for async delete operations."""

    @pytest.mark.asyncio
    async def test_delete_by_source_async_success(self) -> None:
        """Test that async delete by source succeeds."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 5

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection_async", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = await storage.delete_by_source_async("test.pdf")
                assert result == 5

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id_async_success(self) -> None:
        """Test that async delete by chunk ID succeeds."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 1

            mock_collection = MagicMock()
            mock_collection.delete_one.return_value = mock_result

            with (
                patch.object(storage, "validate_connection_async", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = await storage.delete_by_chunk_id_async("chunk-123")
                assert result == 1

    @pytest.mark.asyncio
    async def test_delete_all_async_success(self) -> None:
        """Test that async delete all succeeds."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result = MagicMock()
            mock_result.deleted_count = 100

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_result

            with (
                patch.object(storage, "validate_connection_async", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                result = await storage.delete_all_async()
                assert result == 100

    @pytest.mark.asyncio
    async def test_delete_by_source_async_connection_failure(self) -> None:
        """Test that async delete by source raises on connection failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection_async", return_value=False),
                pytest.raises(StorageConnectionError),
            ):
                await storage.delete_by_source_async("test.pdf")

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id_async_connection_failure(self) -> None:
        """Test that async delete by chunk ID raises on connection failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection_async", return_value=False),
                pytest.raises(StorageConnectionError),
            ):
                await storage.delete_by_chunk_id_async("chunk-123")

    @pytest.mark.asyncio
    async def test_delete_all_async_connection_failure(self) -> None:
        """Test that async delete all raises on connection failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection_async", return_value=False),
                pytest.raises(StorageConnectionError),
            ):
                await storage.delete_all_async()


class TestDeleteIntegrationScenarios:
    """Test suite for delete integration scenarios."""

    def test_delete_by_source_then_verify_count(self) -> None:
        """Test that delete by source followed by count verification works."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_delete_result = MagicMock()
            mock_delete_result.deleted_count = 10

            mock_collection = MagicMock()
            mock_collection.delete_many.return_value = mock_delete_result
            mock_collection.count_documents.return_value = 5

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                deleted = storage.delete_by_source("test.pdf")
                remaining = storage.get_stats()["total_chunks"]

                assert deleted == 10
                assert remaining == 5
                assert mock_collection.delete_many.call_count == 1
                assert mock_collection.count_documents.call_count == 1

    def test_sequential_delete_operations(self) -> None:
        """Test that sequential delete operations work correctly."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_result_source = MagicMock()
            mock_result_source.deleted_count = 5

            mock_result_chunk = MagicMock()
            mock_result_chunk.deleted_count = 1

            mock_result_all = MagicMock()
            mock_result_all.deleted_count = 100

            mock_collection = MagicMock()
            mock_collection.delete_many.side_effect = [
                mock_result_source,
                mock_result_all,
            ]
            mock_collection.delete_one.return_value = mock_result_chunk

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                r1 = storage.delete_by_source("file1.pdf")
                r2 = storage.delete_by_chunk_id("chunk-1")
                r3 = storage.delete_all()

                assert r1 == 5
                assert r2 == 1
                assert r3 == 100
                assert mock_collection.delete_many.call_count == 2
                assert mock_collection.delete_one.call_count == 1
