"""Tests for remaining storage module coverage gaps."""

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestStorageEdgeCases:
    """Tests for edge cases and remaining coverage gaps in storage module."""

    @pytest.fixture
    def storage(self):
        """Create a VectorStorage instance with mocked config."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27018"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01

            storage = VectorStorage()
            yield storage

    def test_close_closes_sync_only(self, storage: VectorStorage) -> None:
        """Test sync close handles only sync client."""
        mock_client = MagicMock()
        storage._client = mock_client
        storage._async_client = None

        storage.close()

        mock_client.close.assert_called_once()
        assert storage._client is None
        assert storage._async_client is None

    def test_close_closes_both_clients(self, storage: VectorStorage) -> None:
        """Test sync close closes both clients."""
        mock_client = MagicMock()
        storage._client = mock_client

        storage.close()

        mock_client.close.assert_called_once()
        assert storage._client is None

    def test_async_client_property_creates_client(self, storage: VectorStorage) -> None:
        """Test async_client property creates HTTPX client when needed."""
        # Ensure no async client exists
        storage._async_client = None

        client = storage.async_client

        assert client is not None
        assert isinstance(client, httpx.AsyncClient)

    def test_async_client_property_reuses_client(self, storage: VectorStorage) -> None:
        """Test async_client property reuses existing client."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        storage._async_client = mock_client

        client = storage.async_client

        assert client is mock_client

    @pytest.mark.asyncio
    async def test_do_validate_async_handles_exception(
        self, storage: VectorStorage
    ) -> None:
        """Test _do_validate_async handles exceptions gracefully."""
        from pymongo.errors import ConnectionFailure

        mock_admin = MagicMock()
        mock_admin.command = MagicMock(
            side_effect=ConnectionFailure("Connection failed")
        )

        mock_client = MagicMock()
        mock_client.admin = mock_admin

        with patch.object(storage, "_client", mock_client):
            result = await storage._do_validate_async()
            assert result is False

    @pytest.mark.asyncio
    async def test_store_batch_async_preserves_ingested_at(
        self, storage: VectorStorage
    ) -> None:
        """Test store_batch_async preserves existing ingested_at timestamp."""
        captured_docs = []

        def mock_insert_many(docs):
            for doc in docs:
                captured_docs.append(doc)
            mock_result = MagicMock()
            mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
            return mock_result

        mock_collection = MagicMock()
        mock_collection.insert_many = mock_insert_many

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            # Document with existing ingested_at
            docs = [
                {
                    "chunk_id": "chunk1",
                    "text": "text1",
                    "embedding": [0.1] * 384,
                    "metadata": {"ingested_at": "original_time"},
                }
            ]
            await storage.store_batch_async(docs)

            assert len(captured_docs) == 1
            # The timestamp should be updated to current time
            assert "ingested_at" in captured_docs[0]["metadata"]
            assert captured_docs[0]["metadata"]["ingested_at"] != "original_time"

    def test_require_connection_async_raises_on_failure(self) -> None:
        """Test _require_connection_async raises StorageConnectionError on failure."""
        with patch("secondbrain.storage.sync.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27018"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384

            storage = VectorStorage()

            async def test_it():
                with (
                    patch.object(
                        storage, "validate_connection_async", return_value=False
                    ),
                    pytest.raises(StorageConnectionError),
                ):
                    await storage._require_connection_async("test")

            asyncio.run(test_it())
