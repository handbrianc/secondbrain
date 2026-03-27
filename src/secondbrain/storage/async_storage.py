"""Asynchronous vector storage for MongoDB using Motor."""

import asyncio
import logging
import struct
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from bson.binary import Binary
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.operations import SearchIndexModel

from secondbrain.config import Config, get_config
from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.types import ChunkInfo, SearchResult
from secondbrain.utils.connections import ValidatableService
from secondbrain.utils.perf_monitor import async_timing

logger = logging.getLogger(__name__)


class AsyncVectorStorage(ValidatableService):
    """Asynchronous vector storage using Motor (official async MongoDB driver).

    This class provides a native async/await API for MongoDB operations using Motor,
    eliminating the need for asyncio.to_thread() wrappers. This offers better
    performance for concurrent operations compared to the synchronous VectorStorage
    class with to_thread() wrappers.

    Key Differences from VectorStorage:
    -----------------------------------
    - Uses motor.motor_asyncio.AsyncIOMotorClient instead of pymongo.MongoClient
    - All operations are native async/await (no thread blocking)
    - Better performance for concurrent I/O operations
    - Same API surface as VectorStorage for easy migration
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize async vector storage with Motor."""
        config = get_config()
        self.mongo_uri: str = mongo_uri or config.mongo_uri
        self.db_name: str = db_name or config.mongo_db
        self.collection_name: str = collection_name or config.mongo_collection
        self._config: Config = config
        self._async_client: AsyncIOMotorClient | None = None
        self._async_db: Any = None
        self._async_collection: Any = None
        self._index_created: bool = False
        self._index_ready_retry_count: int = config.index_ready_retry_count
        self._index_ready_retry_delay: float = config.index_ready_retry_delay
        super().__init__(cache_ttl=config.connection_cache_ttl)

    async def _require_connection_async(
        self, operation: str = "database operation"
    ) -> None:
        """Validate Motor connection asynchronously."""
        if not await self.validate_connection_async():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}. "
                f"Database: {self.db_name}, Collection: {self.collection_name}. "
                f"Operation: {operation}."
            )

    async def _wait_for_index_ready_async(self) -> None:
        """Wait for MongoDB vector search index to be ready asynchronously."""
        await self._ensure_index_async()

        base_delay = 0.1
        max_delay = 2.0
        delay = base_delay

        for attempt in range(self._index_ready_retry_count):
            try:
                cursor = self.async_collection.list_search_indexes("embedding_index")
                indexes = await cursor.to_list(length=None)
                for idx in indexes:
                    if (
                        idx.get("name") == "embedding_index"
                        and idx.get("status") == "READY"
                    ):
                        return
            except Exception as e:
                logger.debug(
                    "Index not ready, retrying... (attempt %s/%s, delay %.2fs, error: %s: %s)",
                    attempt + 1,
                    self._index_ready_retry_count,
                    delay,
                    type(e).__name__,
                    e,
                )

            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)

        logger.warning("Vector search index may not be ready after maximum retries")

    async def _ensure_index_async(self) -> None:
        """Create vector index asynchronously if it does not exist."""
        if self._index_created:
            return

        try:
            cursor = self.async_collection.list_search_indexes("embedding_index")
            existing_indexes = await cursor.to_list(length=None)

            if existing_indexes:
                existing_index = existing_indexes[0]
                existing_dims = (
                    existing_index.get("definition", {})
                    .get("fields", [{}])[0]
                    .get("numDimensions")
                )
                current_dims = self._config.embedding_dimensions

                # Check if dimensions mismatch - only drop when mismatch is CONFIRMED
                dims_mismatch = (
                    existing_dims is not None and existing_dims != current_dims
                )

                if dims_mismatch:
                    logger.info(
                        "Dropping old index with %d dimensions to create new index with %d dimensions",
                        existing_dims,
                        current_dims,
                    )
                    try:
                        drop_cursor = self.async_collection.drop_search_index(
                            "embedding_index"
                        )
                        await drop_cursor
                        logger.info("Dropped old index successfully")
                    except Exception as drop_err:
                        logger.error(
                            "Failed to drop old index: %s: %s",
                            type(drop_err).__name__,
                            drop_err,
                        )
                        raise
                else:
                    self._index_created = True
                    return

            search_index_model = SearchIndexModel(
                definition={
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": self._config.embedding_dimensions,
                            "similarity": "cosine",
                        }
                    ]
                },
                name="embedding_index",
                type="vectorSearch",
            )
            create_cursor = self.async_collection.create_search_index(
                model=search_index_model
            )
            await create_cursor
            logger.info(
                "Created vector index with dimensions=%d",
                self._config.embedding_dimensions,
            )
            self._index_created = True
        except Exception as e:
            logger.warning("Could not create index: %s: %s", type(e).__name__, e)
            self._index_created = False

    @property
    def async_client(self) -> AsyncIOMotorClient:
        """Get or create Motor async client instance."""
        if self._async_client is None:
            self._async_client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=300000,
            )
        return self._async_client

    @property
    def async_db(self) -> Any:
        """Get or create async database instance."""
        if self._async_db is None:
            self._async_db = self.async_client[self.db_name]
        return self._async_db

    @property
    def async_collection(self) -> Any:
        """Get or create async collection instance."""
        if self._async_collection is None:
            self._async_collection = self.async_db[self.collection_name]
        return self._async_collection

    def _add_ingestion_timestamp(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Add ingestion timestamp to document."""
        result = doc.copy()
        now = datetime.now(UTC).isoformat()

        if "ingested_at" in result:
            result["ingested_at"] = now
        elif "metadata" in result:
            result.setdefault("metadata", {})
            result["metadata"]["ingested_at"] = now
        else:
            result["ingested_at"] = now

        return result

    def _add_ingestion_timestamps(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add ingestion timestamps to multiple documents."""
        now = datetime.now(UTC).isoformat()
        docs_with_timestamps: list[dict[str, Any]] = []

        for doc in documents:
            doc_copy = doc.copy()

            if "ingested_at" in doc_copy:
                doc_copy["ingested_at"] = now
            elif "metadata" in doc_copy:
                doc_copy.setdefault("metadata", {})
                doc_copy["metadata"]["ingested_at"] = now
            else:
                doc_copy["ingested_at"] = now

            docs_with_timestamps.append(doc_copy)

        return docs_with_timestamps

    def _encode_embedding(self, embedding: list[float]) -> bytes:
        """Convert float list to binary float32 array."""
        return struct.pack(f"{len(embedding)}f", *embedding)

    def _decode_embedding(
        self, binary: bytes, dimensions: int | None = None
    ) -> list[float]:
        """Convert binary float32 array back to float list."""
        if dimensions is None:
            dimensions = len(binary) // 4
        return list(struct.unpack(f"{dimensions}f", binary))

    def _prepare_embedding_for_storage(
        self, embedding: list[float]
    ) -> bytes | list[float]:
        """Prepare embedding for storage based on config."""
        if self._config.embedding_storage_format == "binary":
            return Binary(self._encode_embedding(embedding))
        return embedding

    def _normalize_embedding(self, embedding: bytes | list[float]) -> list[float]:
        """Normalize embedding to list format for use."""
        if isinstance(embedding, Binary):
            return self._decode_embedding(bytes(embedding))
        if isinstance(embedding, bytes):
            return self._decode_embedding(embedding)
        return embedding

    def _prepare_document_for_storage(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Prepare document for storage with optimizations."""
        result = doc.copy()
        if "embedding" in result:
            result["embedding"] = self._prepare_embedding_for_storage(
                result["embedding"]
            )
        return result

    def close(self) -> None:
        """Close resources and release async connections."""
        if self._async_client is not None:
            self._async_client.close()
            self._async_client = None

    async def aclose(self) -> None:
        """Close Motor async client and release resources."""
        if self._async_client is not None:
            self._async_client.close()
            self._async_client = None

    def __enter__(self) -> "AsyncVectorStorage":
        """Enter runtime context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit runtime context manager."""
        self.close()

    async def __aenter__(self) -> "AsyncVectorStorage":
        """Enter async runtime context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit async runtime context manager."""
        await self.aclose()

    async def _do_validate_async(self) -> bool:
        """Async validation using Motor."""
        try:
            await self.async_client.admin.command("ping")
            return True
        except Exception:
            return False

    @async_timing("async_storage_store")
    async def store_async(self, document: dict[str, Any]) -> str:
        """Store a document with embedding using native Motor async."""
        await self._require_connection_async("store document")

        doc_with_timestamp = self._add_ingestion_timestamp(document)
        doc = self._prepare_document_for_storage(doc_with_timestamp)

        insert_cursor = self.async_collection.insert_one(doc)
        result = await insert_cursor
        return str(result.inserted_id)

    @async_timing("async_storage_store_batch")
    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents using native Motor async."""
        await self._require_connection_async("store batch")

        docs_with_timestamps = self._add_ingestion_timestamps(documents)

        docs_prepared = [
            self._prepare_document_for_storage(doc) for doc in docs_with_timestamps
        ]

        insert_cursor = self.async_collection.insert_many(docs_prepared)
        result = await insert_cursor
        return len(result.inserted_ids)

    @async_timing("async_storage_search")
    async def search_async(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar embeddings using native Motor async."""
        await self._require_connection_async("search")

        await self._wait_for_index_ready_async()

        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        agg_cursor = self.async_collection.aggregate(pipeline)
        results = await agg_cursor.to_list(length=None)
        return results  # type: ignore[no-any-return]

    async def list_chunks_async(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChunkInfo]:
        """List chunks with optional filters using native Motor async."""
        await self._require_connection_async("list chunks")

        query: dict[str, Any] = {}
        if source_filter:
            query["source_file"] = {"$regex": source_filter}
        if chunk_id:
            query["chunk_id"] = chunk_id

        cursor = (
            self.async_collection.find(
                query,
                {
                    "_id": 0,
                    "chunk_id": 1,
                    "source_file": 1,
                    "page_number": 1,
                    "chunk_text": 1,
                },
            )
            .skip(offset)
            .limit(limit)
        )

        chunks = await cursor.to_list(length=None)
        return chunks  # type: ignore[no-any-return]

    async def delete_by_source_async(self, source: str) -> int:
        """Delete all chunks from a source file using native Motor async."""
        await self._require_connection_async("delete by source")

        delete_cursor = self.async_collection.delete_many({"source_file": source})
        result = await delete_cursor
        return int(result.deleted_count)

    async def delete_by_chunk_id_async(self, chunk_id: str) -> int:
        """Delete a specific chunk using native Motor async."""
        await self._require_connection_async("delete by chunk ID")

        delete_cursor = self.async_collection.delete_one({"chunk_id": chunk_id})
        result = await delete_cursor
        return int(result.deleted_count)

    async def delete_all_async(self) -> int:
        """Delete all documents using native Motor async."""
        await self._require_connection_async("delete all")

        delete_cursor = self.async_collection.delete_many({})
        result = await delete_cursor
        return int(result.deleted_count)

    async def get_stats_async(self) -> dict[str, Any]:
        """Get database statistics using native Motor async."""
        await self._require_connection_async("get stats")

        total = await self.async_collection.count_documents({})
        unique_sources = await self.async_collection.distinct("source_file")

        return {
            "total_chunks": total,
            "unique_sources": len(unique_sources),
            "database": self.db_name,
            "collection": self.collection_name,
        }
