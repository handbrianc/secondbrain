"""Tests for async operations in storage module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.storage import StorageConnectionError, VectorStorage


class TestVectorStorageAsync:
    """Tests for async VectorStorage operations."""

    @pytest.fixture
    def storage(self):
        """Create a VectorStorage instance with mocked config."""
        with patch("secondbrain.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain"
            mock_config.return_value.mongo_collection = "embeddings"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01
            mock_config.return_value.connection_cache_ttl = 60.0

            storage = VectorStorage()
            yield storage

    @pytest.mark.asyncio
    async def test_validate_connection_async_success(
        self, storage: VectorStorage
    ) -> None:
        """Test async connection validation success."""
        mock_client = MagicMock()
        mock_client.admin.command = MagicMock(return_value={"ok": 1})

        with patch.object(storage, "_client", mock_client):
            result = await storage.validate_connection_async()
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_async_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test async connection validation failure."""
        mock_client = MagicMock()
        mock_client.admin.command = MagicMock(
            side_effect=Exception("Connection failed")
        )

        with patch.object(storage, "_client", mock_client):
            result = await storage.validate_connection_async()
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_connection_async_caching(
        self, storage: VectorStorage
    ) -> None:
        """Test async connection validation uses cache."""
        mock_client = MagicMock()
        mock_client.admin.command = MagicMock(return_value={"ok": 1})

        with patch.object(storage, "_client", mock_client):
            result1 = await storage.validate_connection_async()
            assert result1 is True

            call_count = mock_client.admin.command.call_count
            result2 = await storage.validate_connection_async()
            assert result2 is True
            assert mock_client.admin.command.call_count == call_count

    @pytest.mark.asyncio
    async def test_validate_connection_async_force(
        self, storage: VectorStorage
    ) -> None:
        """Test async connection validation with force flag."""
        mock_client = MagicMock()
        mock_client.admin.command = MagicMock(return_value={"ok": 1})

        with patch.object(storage, "_client", mock_client):
            result = await storage.validate_connection_async(force=True)
            assert result is True
            assert mock_client.admin.command.call_count > 0

    @pytest.mark.asyncio
    async def test_store_async_success(self, storage: VectorStorage) -> None:
        """Test async document storage."""
        mock_result = MagicMock()
        mock_result.inserted_id = "test_id"

        mock_collection = MagicMock()
        mock_collection.insert_one = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            doc = {
                "chunk_id": "chunk1",
                "text": "test text",
                "embedding": [0.1] * 384,
                "metadata": {"source": "test.pdf"},
            }
            result = await storage.store_async(doc)
            assert result == "test_id"
            mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_async_adds_timestamp(self, storage: VectorStorage) -> None:
        """Test that store_async adds ingestion timestamp."""
        captured_docs = []

        def mock_insert_one(doc):
            doc_copy = doc.copy()
            if "metadata" not in doc_copy:
                doc_copy["metadata"] = {}
            doc_copy["metadata"]["ingested_at"] = "test_timestamp"
            captured_docs.append(doc_copy)
            mock_result = MagicMock()
            mock_result.inserted_id = "test_id"
            return mock_result

        mock_collection = MagicMock()
        mock_collection.insert_one = mock_insert_one

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            doc = {
                "chunk_id": "chunk1",
                "text": "test text",
                "embedding": [0.1] * 384,
                "metadata": {},
            }
            await storage.store_async(doc)

            assert len(captured_docs) == 1
            assert "metadata" in captured_docs[0]
            assert "ingested_at" in captured_docs[0]["metadata"]

    @pytest.mark.asyncio
    async def test_store_async_connection_failure(self, storage: VectorStorage) -> None:
        """Test store_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.store_async({"test": "doc"})

    @pytest.mark.asyncio
    async def test_store_batch_async_success(self, storage: VectorStorage) -> None:
        """Test async batch document storage."""
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3"]

        mock_collection = MagicMock()
        mock_collection.insert_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            docs = [
                {"chunk_id": f"chunk{i}", "text": f"text{i}", "embedding": [0.1] * 384}
                for i in range(3)
            ]
            result = await storage.store_batch_async(docs)
            assert result == 3
            mock_collection.insert_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_batch_async_adds_timestamps(
        self, storage: VectorStorage
    ) -> None:
        """Test that store_batch_async adds timestamps to all documents."""
        captured_docs = []

        def mock_insert_many(docs):
            for doc in docs:
                if "metadata" not in doc:
                    doc["metadata"] = {}
                doc["metadata"]["ingested_at"] = "test_timestamp"
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
            docs = [
                {"chunk_id": f"chunk{i}", "text": f"text{i}", "embedding": [0.1] * 384}
                for i in range(3)
            ]
            await storage.store_batch_async(docs)

            assert len(captured_docs) == 3
            for doc in captured_docs:
                assert "metadata" in doc
                assert "ingested_at" in doc["metadata"]

    @pytest.mark.asyncio
    async def test_search_async_success(self, storage: VectorStorage) -> None:
        """Test async search."""
        mock_results = [
            {
                "chunk_id": "chunk1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "test text",
                "score": 0.9,
            }
        ]

        mock_collection = MagicMock()
        mock_collection.aggregate = MagicMock(return_value=mock_results)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "_index_created", True),
        ):
            results = await storage.search_async(embedding=[0.1] * 384, top_k=5)
            assert len(results) == 1
            mock_collection.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_async_with_filters(self, storage: VectorStorage) -> None:
        """Test async search with filters."""
        mock_results = []

        mock_collection = MagicMock()
        mock_collection.aggregate = MagicMock(return_value=mock_results)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "_index_created", True),
        ):
            await storage.search_async(
                embedding=[0.1] * 384,
                source_filter="test.pdf",
                file_type_filter="pdf",
            )
            mock_collection.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_chunks_async_success(self, storage: VectorStorage) -> None:
        """Test async list chunks."""
        mock_chunks = [
            {
                "chunk_id": "chunk1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "test text",
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = mock_chunks

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.list_chunks_async(limit=50, offset=0)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_chunks_async_with_filters(self, storage: VectorStorage) -> None:
        """Test async list chunks with filters."""
        mock_chunks = []

        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.__iter__.return_value = mock_chunks

        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.list_chunks_async(
                source_filter="test.pdf",
                chunk_id="chunk1",
                limit=50,
                offset=0,
            )
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_aclose_closes_both_clients(self, storage: VectorStorage) -> None:
        """Test async close closes both sync and async clients."""
        mock_client = MagicMock()
        storage._client = mock_client

        async def mock_aclose():
            pass

        storage._async_client = MagicMock()
        storage._async_client.aclose = mock_aclose

        await storage.aclose()

        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_require_connection_async_success(
        self, storage: VectorStorage
    ) -> None:
        """Test async require connection success."""
        with patch.object(storage, "validate_connection_async", return_value=True):
            await storage._require_connection_async("test operation")

    @pytest.mark.asyncio
    async def test_require_connection_async_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test async require connection failure raises error."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage._require_connection_async("test operation")

    @pytest.mark.asyncio
    async def test_wait_for_index_ready_async_success(
        self, storage: VectorStorage
    ) -> None:
        """Test async wait for index ready success."""
        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(
            return_value=[{"name": "embedding_index", "status": "READY"}]
        )

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "ensure_index", return_value=None),
        ):
            await storage._wait_for_index_ready_async()

    @pytest.mark.asyncio
    async def test_wait_for_index_ready_async_timeout(
        self, storage: VectorStorage
    ) -> None:
        """Test async wait for index ready with timeout."""
        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(return_value=[])

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "ensure_index", return_value=None),
        ):
            await storage._wait_for_index_ready_async()

    @pytest.mark.asyncio
    async def test_wait_for_index_ready_async_exception_handling(
        self, storage: VectorStorage
    ) -> None:
        """Test async wait for index ready handles exceptions."""
        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(
            side_effect=Exception("Index error")
        )

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
            patch.object(storage, "ensure_index", return_value=None),
        ):
            await storage._wait_for_index_ready_async()

    @pytest.mark.asyncio
    async def test_delete_by_source_async_success(self, storage: VectorStorage) -> None:
        """Test async delete by source."""
        mock_result = MagicMock()
        mock_result.deleted_count = 5

        mock_collection = MagicMock()
        mock_collection.delete_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.delete_by_source_async("test.pdf")
            assert result == 5
            mock_collection.delete_many.assert_called_once_with(
                {"source_file": "test.pdf"}
            )

    @pytest.mark.asyncio
    async def test_delete_by_source_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test delete_by_source_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.delete_by_source_async("test.pdf")

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id_async_success(
        self, storage: VectorStorage
    ) -> None:
        """Test async delete by chunk ID."""
        mock_result = MagicMock()
        mock_result.deleted_count = 1

        mock_collection = MagicMock()
        mock_collection.delete_one = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.delete_by_chunk_id_async("chunk-123")
            assert result == 1
            mock_collection.delete_one.assert_called_once_with(
                {"chunk_id": "chunk-123"}
            )

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test delete_by_chunk_id_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.delete_by_chunk_id_async("chunk-123")

    @pytest.mark.asyncio
    async def test_delete_all_async_success(self, storage: VectorStorage) -> None:
        """Test async delete all documents."""
        mock_result = MagicMock()
        mock_result.deleted_count = 100

        mock_collection = MagicMock()
        mock_collection.delete_many = MagicMock(return_value=mock_result)

        with (
            patch.object(storage, "validate_connection_async", return_value=True),
            patch.object(storage, "_collection", mock_collection),
        ):
            result = await storage.delete_all_async()
            assert result == 100
            mock_collection.delete_many.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_delete_all_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test delete_all_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.delete_all_async()

    @pytest.mark.asyncio
    async def test_do_validate_async_success(self, storage: VectorStorage) -> None:
        """Test _do_validate_async returns True on success."""
        mock_client = MagicMock()
        mock_client.admin.command.return_value = {"ok": 1}

        with patch.object(storage, "_client", mock_client):
            result = await storage._do_validate_async()
            assert result is True

    @pytest.mark.asyncio
    async def test_do_validate_async_failure(self, storage: VectorStorage) -> None:
        """Test _do_validate_async returns False on failure."""
        from pymongo.errors import ConnectionFailure

        mock_client = MagicMock()
        mock_client.admin.command.side_effect = ConnectionFailure("Network error")

        with patch.object(storage, "_client", mock_client):
            result = await storage._do_validate_async()
            assert result is False

    @pytest.mark.asyncio
    async def test_request_async(self, storage: VectorStorage) -> None:
        """Test _request_async method."""
        from unittest.mock import AsyncMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"test content"

        mock_async_client = MagicMock()
        mock_async_client.request = AsyncMock(return_value=mock_response)
        storage._async_client = mock_async_client

        result = await storage._request_async("GET", "http://test.com/api")
        assert result.status_code == 200
        assert result.content == b"test content"
        mock_async_client.request.assert_called_once_with("GET", "http://test.com/api")

    @pytest.mark.asyncio
    async def test_aclose_handles_missing_async_client(
        self, storage: VectorStorage
    ) -> None:
        """Test aclose handles missing async client gracefully."""
        mock_client = MagicMock()
        storage._client = mock_client
        storage._async_client = None

        await storage.aclose()

        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test search_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.search_async(embedding=[0.1] * 384)

    @pytest.mark.asyncio
    async def test_list_chunks_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test list_chunks_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.list_chunks_async()

    @pytest.mark.asyncio
    async def test_store_batch_async_connection_failure(
        self, storage: VectorStorage
    ) -> None:
        """Test store_batch_async raises error on connection failure."""
        with (
            patch.object(storage, "validate_connection_async", return_value=False),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await storage.store_batch_async([])
