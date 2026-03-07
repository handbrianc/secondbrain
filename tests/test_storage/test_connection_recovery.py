"""Tests for connection recovery mechanisms."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestConnectionRecovery:
    """Tests for connection recovery mechanisms."""

    def test_connection_failure_recovery(self) -> None:
        """Test recovery after connection failure."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # First call fails, second succeeds
            call_count = [0]

            def validate_connection():
                call_count[0] += 1
                return call_count[0] != 1

            with patch.object(
                storage, "validate_connection", side_effect=validate_connection
            ):
                # First validation fails
                assert storage.validate_connection() is False
                # After retry, should succeed
                assert storage.validate_connection() is True

    def test_connection_cache_invalidation(self) -> None:
        """Test cache invalidation on failure."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_client = MagicMock()
            mock_client.admin.command.return_value = {"ok": 1}

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_client", mock_client),
            ):
                # First call caches success
                assert storage.validate_connection() is True
                # Invalidate cache
                storage._connection_valid = None
                # Next call should re-validate
                assert storage.validate_connection() is True

    def test_async_connection_recovery(self) -> None:
        """Test async connection recovery patterns."""
        import asyncio

        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            # First call fails, second succeeds
            call_count = [0]

            async def async_validate():
                call_count[0] += 1
                return call_count[0] != 1

            with patch.object(
                storage, "validate_connection_async", side_effect=async_validate
            ):
                # First validation fails
                result1 = asyncio.run(storage.validate_connection_async())
                assert result1 is False
                # After "retry", should succeed
                result2 = asyncio.run(storage.validate_connection_async())
                assert result2 is True

    def test_connection_pool_exhaustion(self) -> None:
        """Test handling of connection pool exhaustion."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_collection = MagicMock()
            mock_collection.count_documents.return_value = 10

            with (
                patch.object(storage, "validate_connection", return_value=True),
                patch.object(storage, "_collection", mock_collection),
            ):
                # Multiple operations should work with connection pooling
                storage.get_stats()
                storage.get_stats()
                storage.get_stats()
                # Should not raise any errors
                assert True

    def test_reconnection_after_close(self) -> None:
        """Test reconnection after explicit close."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            mock_client = MagicMock()
            mock_client.admin.command.return_value = {"ok": 1}

            with patch.object(storage, "_client", mock_client):
                # Initial connection works
                _ = storage.client
                assert storage._client is not None

                # Close connection
                storage.close()
                assert storage._client is None

                # Reconnect should create new client
                _ = storage.client
                assert storage._client is not None

    def test_context_manager_connection(self) -> None:
        """Test context manager patterns."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            mock_client = MagicMock()
            mock_client.admin.command.return_value = {"ok": 1}

            with patch("secondbrain.storage.MongoClient", return_value=mock_client):
                with VectorStorage() as storage:
                    # Connection should be established
                    assert storage.client is not None
                    # Can perform operations
                    assert storage._client is not None

                # After exit, connection should be closed
                assert storage._client is None

    def test_validate_connection_caching(self) -> None:
        """Test that connection validation is cached."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.connection_cache_ttl = 60.0

            storage = VectorStorage()

            mock_client = MagicMock()
            mock_client.admin.command.return_value = {"ok": 1}

            call_count = [0]

            def mock_validate():
                call_count[0] += 1
                return True

            with (
                patch.object(storage, "_do_validate", side_effect=mock_validate),
                patch.object(storage, "_client", mock_client),
            ):
                # First call should validate
                result1 = storage.validate_connection()
                assert result1 is True
                first_count = call_count[0]

                # Second call within cache TTL should use cache
                result2 = storage.validate_connection()
                assert result2 is True
                # Count should not have increased significantly
                assert call_count[0] == first_count

    def test_connection_error_message_includes_context(self) -> None:
        """Test that connection errors include helpful context."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            with (
                patch.object(storage, "validate_connection", return_value=False),
                pytest.raises(StorageConnectionError) as exc_info,
            ):
                storage.store(
                    {
                        "chunk_id": "test",
                        "text": "test",
                        "embedding": [0.1],
                        "metadata": {},
                    }
                )

            # Error message should include connection details
            error_msg = str(exc_info.value)
            assert "mongodb://localhost:27017" in error_msg
            assert "secondbrain" in error_msg
            assert "store document" in error_msg
