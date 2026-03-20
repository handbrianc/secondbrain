"""Tests for AsyncVectorStorage using Motor."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.storage import AsyncVectorStorage


class TestAsyncVectorStorage:
    """Tests for AsyncVectorStorage class."""

    @pytest.fixture
    def async_storage(self) -> Generator[AsyncVectorStorage, None, None]:
        """Create an AsyncVectorStorage instance with mocked config."""
        with patch("secondbrain.storage.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "secondbrain_test"
            mock_config.return_value.mongo_collection = "embeddings_test"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 3
            mock_config.return_value.index_ready_retry_delay = 0.01
            mock_config.return_value.connection_cache_ttl = 60.0
            mock_config.return_value.embedding_storage_format = "json"

            storage = AsyncVectorStorage()
            yield storage

    @pytest.mark.asyncio
    async def test_init_with_defaults(self, async_storage: AsyncVectorStorage) -> None:
        """Test initialization with default config values."""
        assert async_storage.mongo_uri == "mongodb://localhost:27017"
        assert async_storage.db_name == "secondbrain_test"
        assert async_storage.collection_name == "embeddings_test"
        assert async_storage._index_created is False

    @pytest.mark.asyncio
    async def test_init_with_overrides(self) -> None:
        """Test initialization with custom parameters."""
        with patch("secondbrain.storage.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://default:27017"
            mock_config.return_value.mongo_db = "default_db"
            mock_config.return_value.mongo_collection = "default_collection"
            mock_config.return_value.embedding_dimensions = 384
            mock_config.return_value.index_ready_retry_count = 15
            mock_config.return_value.index_ready_retry_delay = 0.1
            mock_config.return_value.connection_cache_ttl = 60.0
            mock_config.return_value.embedding_storage_format = "json"

            storage = AsyncVectorStorage(
                mongo_uri="mongodb://custom:27017",
                db_name="custom_db",
                collection_name="custom_collection",
            )

            assert storage.mongo_uri == "mongodb://custom:27017"
            assert storage.db_name == "custom_db"
            assert storage.collection_name == "custom_collection"

    @pytest.mark.asyncio
    async def test_async_client_property(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test async_client property creates Motor client."""
        from motor.motor_asyncio import AsyncIOMotorClient

        client = async_storage.async_client
        assert isinstance(client, AsyncIOMotorClient)

    @pytest.mark.asyncio
    async def test_async_db_property(self, async_storage: AsyncVectorStorage) -> None:
        """Test async_db property creates database reference."""
        db = async_storage.async_db
        assert db is not None
        assert db.name == "secondbrain_test"

    @pytest.mark.asyncio
    async def test_async_collection_property(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test async_collection property creates collection reference."""
        collection = async_storage.async_collection
        assert collection is not None
        assert collection.name == "embeddings_test"

    @pytest.mark.asyncio
    async def test_do_validate_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test async validation returns True on success."""
        # Mock the async_client.admin.command to return a successful result
        async_storage._async_client = MagicMock()
        async_storage._async_client.admin.command = AsyncMock(return_value={"ok": 1})

        result = await async_storage._do_validate_async()
        assert result is True

    @pytest.mark.asyncio
    async def test_do_validate_async_failure(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test async validation returns False on failure."""
        async_storage._async_client = MagicMock()
        async_storage._async_client.admin.command = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        result = await async_storage._do_validate_async()
        assert result is False

    @pytest.mark.asyncio
    async def test_require_connection_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _require_connection_async succeeds when valid."""
        with patch.object(
            async_storage, "validate_connection_async", return_value=True
        ):
            # Should not raise
            await async_storage._require_connection_async("test operation")

    @pytest.mark.asyncio
    async def test_require_connection_async_failure(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _require_connection_async raises on failure."""
        with (
            patch.object(
                async_storage, "validate_connection_async", return_value=False
            ),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await async_storage._require_connection_async("test operation")

    @pytest.mark.asyncio
    async def test_store_async_success(self, async_storage: AsyncVectorStorage) -> None:
        """Test store_async inserts document successfully."""
        mock_result = MagicMock()
        mock_result.inserted_id = "test_id_123"

        mock_collection = MagicMock()
        mock_collection.insert_one = AsyncMock(return_value=mock_result)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            doc = {
                "chunk_id": "chunk-123",
                "source_file": "test.pdf",
                "embedding": [0.1] * 384,
                "chunk_text": "Test text",
            }
            result = await async_storage.store_async(doc)

            assert result == "test_id_123"
            mock_collection.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_async_adds_timestamp(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test store_async adds ingestion timestamp."""
        captured_doc = None

        async def mock_insert_one(doc):
            nonlocal captured_doc
            captured_doc = doc
            mock_result = MagicMock()
            mock_result.inserted_id = "test_id"
            return mock_result

        mock_collection = MagicMock()
        mock_collection.insert_one = mock_insert_one

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            doc = {
                "chunk_id": "chunk-123",
                "source_file": "test.pdf",
                "embedding": [0.1] * 384,
                "chunk_text": "Test text",
                "metadata": {},  # Add metadata for timestamp
            }
            await async_storage.store_async(doc)

            assert captured_doc is not None
            assert "ingested_at" in captured_doc.get("metadata", {})

    @pytest.mark.asyncio
    async def test_store_async_connection_failure(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test store_async raises on connection failure."""
        with (
            patch.object(
                async_storage, "validate_connection_async", return_value=False
            ),
            pytest.raises(StorageConnectionError, match="Cannot connect"),
        ):
            await async_storage.store_async({"test": "doc"})

    @pytest.mark.asyncio
    async def test_store_batch_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test store_batch_async inserts multiple documents."""
        mock_result = MagicMock()
        mock_result.inserted_ids = ["id1", "id2", "id3"]

        mock_collection = MagicMock()
        mock_collection.insert_many = AsyncMock(return_value=mock_result)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            docs = [
                {
                    "chunk_id": f"chunk{i}",
                    "source_file": f"test{i}.pdf",
                    "embedding": [0.1] * 384,
                    "chunk_text": f"Text {i}",
                }
                for i in range(3)
            ]
            result = await async_storage.store_batch_async(docs)

            assert result == 3
            mock_collection.insert_many.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_batch_async_adds_timestamps(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test store_batch_async adds timestamps to all documents."""
        captured_docs: list[dict] = []

        async def mock_insert_many(docs: list[dict]) -> MagicMock:
            captured_docs.extend(docs)
            mock_result = MagicMock()
            mock_result.inserted_ids = [f"id{i}" for i in range(len(docs))]
            return mock_result

        mock_collection = MagicMock()
        mock_collection.insert_many = mock_insert_many

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            docs = [
                {
                    "chunk_id": f"chunk{i}",
                    "source_file": f"test{i}.pdf",
                    "embedding": [0.1] * 384,
                    "chunk_text": f"Text {i}",
                    "metadata": {},  # Add metadata for timestamp
                }
                for i in range(3)
            ]
            await async_storage.store_batch_async(docs)

            assert len(captured_docs) == 3
            for doc in captured_docs:
                assert "ingested_at" in doc.get("metadata", {})

    @pytest.mark.asyncio
    async def test_search_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test search_async returns search results."""
        mock_results = [
            {
                "chunk_id": "chunk1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "test text",
                "score": 0.9,
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=mock_results)

        mock_collection = MagicMock()
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            results = await async_storage.search_async(embedding=[0.1] * 384, top_k=5)

            assert len(results) == 1
            assert results[0]["score"] == 0.9

    @pytest.mark.asyncio
    async def test_search_async_with_filters(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test search_async with source and file type filters."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.aggregate = MagicMock(return_value=mock_cursor)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            await async_storage.search_async(
                embedding=[0.1] * 384,
                top_k=5,
                source_filter="test.pdf",
                file_type_filter="pdf",
            )

            mock_collection.aggregate.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_chunks_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test list_chunks_async returns chunks."""
        mock_chunks = [
            {
                "chunk_id": "chunk1",
                "source_file": "test.pdf",
                "page_number": 1,
                "chunk_text": "test text",
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=mock_chunks)

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            result = await async_storage.list_chunks_async(limit=50, offset=0)

            assert len(result) == 1
            assert result[0]["chunk_id"] == "chunk1"

    @pytest.mark.asyncio
    async def test_list_chunks_async_with_filters(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test list_chunks_async with filters."""
        mock_cursor = MagicMock()
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.find = MagicMock(return_value=mock_cursor)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            result = await async_storage.list_chunks_async(
                source_filter="test.pdf",
                chunk_id="chunk1",
                limit=50,
                offset=0,
            )

            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_delete_by_source_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test delete_by_source_async deletes documents."""
        mock_result = MagicMock()
        mock_result.deleted_count = 5

        mock_collection = MagicMock()
        mock_collection.delete_many = AsyncMock(return_value=mock_result)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            result = await async_storage.delete_by_source_async("test.pdf")

            assert result == 5
            mock_collection.delete_many.assert_called_once_with(
                {"source_file": "test.pdf"}
            )

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test delete_by_chunk_id_async deletes single chunk."""
        mock_result = MagicMock()
        mock_result.deleted_count = 1

        mock_collection = MagicMock()
        mock_collection.delete_one = AsyncMock(return_value=mock_result)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            result = await async_storage.delete_by_chunk_id_async("chunk-123")

            assert result == 1
            mock_collection.delete_one.assert_called_once_with(
                {"chunk_id": "chunk-123"}
            )

    @pytest.mark.asyncio
    async def test_delete_all_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test delete_all_async deletes all documents."""
        mock_result = MagicMock()
        mock_result.deleted_count = 100

        mock_collection = MagicMock()
        mock_collection.delete_many = AsyncMock(return_value=mock_result)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            result = await async_storage.delete_all_async()

            assert result == 100
            mock_collection.delete_many.assert_called_once_with({})

    @pytest.mark.asyncio
    async def test_get_stats_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test get_stats_async returns statistics."""
        mock_collection = MagicMock()
        mock_collection.count_documents = AsyncMock(return_value=100)
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=["file1.pdf", "file2.pdf"])
        mock_collection.distinct = MagicMock(return_value=mock_cursor)

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            stats = await async_storage.get_stats_async()

            assert stats["total_chunks"] == 100
            assert stats["unique_sources"] == 2
            assert stats["database"] == "secondbrain_test"
            assert stats["collection"] == "embeddings_test"

    @pytest.mark.asyncio
    async def test_aclose_closes_client(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test aclose closes the Motor client."""
        mock_client = MagicMock()
        mock_client.close = MagicMock()
        async_storage._async_client = mock_client

        await async_storage.aclose()

        mock_client.close.assert_called_once()
        assert async_storage._async_client is None

    @pytest.mark.asyncio
    async def test_aclose_handles_missing_client(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test aclose handles missing client gracefully."""
        async_storage._async_client = None

        # Should not raise
        await async_storage.aclose()

    @pytest.mark.asyncio
    async def test_context_manager_sync(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test synchronous context manager."""
        with async_storage as storage:
            assert storage is async_storage

    @pytest.mark.asyncio
    async def test_context_manager_async(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test async context manager."""
        async with async_storage as storage:
            assert storage is async_storage

    @pytest.mark.asyncio
    async def test_wait_for_index_ready_async_success(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _wait_for_index_ready_async succeeds when index is ready."""
        mock_index = MagicMock()
        mock_index.get = MagicMock(
            side_effect=lambda key, default=None: {
                "name": "embedding_index",
                "status": "READY",
            }.get(key, default)
        )

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[mock_index])

        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(return_value=mock_cursor)

        with (
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            # Should return without error
            await async_storage._wait_for_index_ready_async()

    @pytest.mark.asyncio
    async def test_wait_for_index_ready_async_timeout(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _wait_for_index_ready_async with timeout."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(return_value=mock_cursor)

        with (
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            # Should complete after retries
            await async_storage._wait_for_index_ready_async()

    @pytest.mark.asyncio
    async def test_ensure_index_async_creates_index(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _ensure_index_async creates new index."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_collection = MagicMock()
        mock_collection.list_search_indexes = MagicMock(return_value=mock_cursor)
        mock_collection.create_search_index = AsyncMock()

        with (
            patch.object(async_storage, "validate_connection_async", return_value=True),
            patch.object(
                type(async_storage), "async_collection", new_callable=PropertyMock
            ) as mock_prop,
        ):
            mock_prop.return_value = mock_collection
            await async_storage._ensure_index_async()

            mock_collection.create_search_index.assert_called_once()
            assert async_storage._index_created is True

    @pytest.mark.asyncio
    async def test_ensure_index_async_skips_existing(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test _ensure_index_async skips if already created."""
        async_storage._index_created = True

        mock_collection = MagicMock()
        mock_collection.create_search_index = AsyncMock()

        with patch.object(
            type(async_storage), "async_collection", new_callable=PropertyMock
        ) as mock_prop:
            mock_prop.return_value = mock_collection
            await async_storage._ensure_index_async()

            mock_collection.create_search_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_encode_decode_embedding(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test embedding encoding and decoding."""
        embedding = [0.1, 0.2, 0.3, 0.4]

        encoded = async_storage._encode_embedding(embedding)
        decoded = async_storage._decode_embedding(encoded)

        assert len(decoded) == len(embedding)
        for orig, dec in zip(embedding, decoded, strict=True):
            assert abs(orig - dec) < 0.0001

    @pytest.mark.asyncio
    async def test_prepare_document_for_storage(
        self, async_storage: AsyncVectorStorage
    ) -> None:
        """Test document preparation for storage."""
        doc = {
            "chunk_id": "chunk-123",
            "embedding": [0.1, 0.2, 0.3],
            "text": "test",
        }

        prepared = async_storage._prepare_document_for_storage(doc)

        assert prepared["chunk_id"] == "chunk-123"
        assert prepared["text"] == "test"
        # Embedding should be preserved (json format)
        assert prepared["embedding"] == [0.1, 0.2, 0.3]
