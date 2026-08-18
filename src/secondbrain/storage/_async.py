"""Async MongoDB vector storage backend (AsyncVectorStorage, Motor)."""

import asyncio
import contextlib
import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from motor.motor_asyncio import AsyncIOMotorClient

from secondbrain.config import Config, config
from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.base import BaseVectorStorage
from secondbrain.storage.models import DatabaseStats
from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.types import (
    ChunkInfo,
    SearchResult,
    _validate_chunk_info,
    _validate_search_result,
)
from secondbrain.utils.connections import ValidatableService
from secondbrain.utils.perf_monitor import async_timing

logger = logging.getLogger(__name__)


class AsyncVectorStorage(ValidatableService, BaseVectorStorage):
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
        """Initialize async vector storage with Motor.

        NOTE: This method is synchronous. The caller should invoke
        ``await storage.ensure_filter_indexes_async()`` afterward to create
        B-tree indexes. This separation keeps test fixtures simple (no async
        __init__) while still providing fully-initialized clients.
        """
        cfg = config()
        self.mongo_uri: str = mongo_uri or cfg.mongo_uri
        self.db_name: str = db_name or cfg.mongo_db
        self.collection_name: str = collection_name or cfg.mongo_collection
        self._config: Config = cfg
        self._async_client: AsyncIOMotorClient | None = None
        self._async_db: Any = None
        self._async_collection: Any = None
        self._index_created: bool = False
        self._index_ready_retry_count: int = cfg.index_ready_retry_count
        self._index_ready_retry_delay: float = cfg.index_ready_retry_delay
        super().__init__(cache_ttl=config().connection_cache_ttl)

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
        """Wait for MongoDB vector search index to be ready asynchronously.

        For local MongoDB Community Edition, this is a no-op because
        _ensure_index_async() sets _index_created = False (no Atlas Search index).
        For Atlas Search deployments, proceeds with index readiness polling.
        """
        await self._ensure_index_async()

        # Guard: Skip polling for local MongoDB (no Atlas Search indexes exist)
        if not self._index_created:
            logger.debug(
                "Skipping index readiness check: local MongoDB without Atlas Search"
            )
            return

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
        """Skip index creation for local MongoDB.

        Local MongoDB Community Edition does not support Atlas Search indexes.
        Vector search is performed using manual cosine similarity calculation
        in the aggregation pipeline (O(n) complexity).

        Note: After calling this method, check self._index_created before
        calling _wait_for_index_ready_async(). If _index_created is False,
        the index does not exist and waiting is pointless.
        """
        # Always use fallback search for local MongoDB
        self._index_created = False

    async def _ensure_filter_indexes_async(self) -> None:
        """Create B-tree indexes for frequently filtered fields.

        These are standard MongoDB indexes (not Atlas Search vector indexes) that
        accelerate $regex prefix queries on source_file and equality filters on
        file_type. These work in MongoDB Community Edition.

        Indexes created:
            - (source_file, 1) for prefix-filtered listing queries
            - (file_type, 1) for file type equality filters

        Idempotent: MongoDB's create_index is a no-op if the index already exists
        with the same spec.
        """
        try:
            await self.async_collection.create_index(
                [("source_file", 1)],
                name="ix_source_file",
                background=True,
            )
            await self.async_collection.create_index(
                [("file_type", 1)],
                name="ix_file_type",
                background=True,
            )
            logger.info("Created filter indexes: ix_source_file, ix_file_type")
        except Exception as e:
            logger.warning(
                "Failed to create filter indexes (non-fatal): %s: %s",
                type(e).__name__,
                e,
            )

    @property
    def async_client(self) -> AsyncIOMotorClient:
        """Get or create Motor async client instance."""
        if self._async_client is None:
            self._async_client = AsyncIOMotorClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=10000,
                maxPoolSize=100,
                minPoolSize=20,
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

    def close(self) -> None:
        """Close resources and release async connections.

        Note: This cannot properly close AsyncIOMotorClient (requires aclose()).
        Use aclose() for proper async cleanup or context manager.
        """
        if self._async_client is not None:
            # AsyncIOMotorClient.close() exists but aclose() is preferred
            # For sync context, we can only close the underlying resources
            with contextlib.suppress(Exception):
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

    def _do_validate(self) -> bool:
        """Validate synchronously using Motor.

        Provided to satisfy the ValidatableService abstract requirement.
        Async code paths should use _do_validate_async directly.
        """
        try:
            # Blocking ping — only used when sync validate_connection() is
            # called on AsyncVectorStorage (rare, but required by ABC).
            asyncio.run(self.async_client.admin.command("ping"))
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Validator concrete implementations — satisfy base.py ABC while
    # delegating to ValidatableService cache/proxy logic
    # ------------------------------------------------------------------

    def validate_connection(self, force: bool = False) -> bool:
        """Validate connection to MongoDB."""
        return super().validate_connection(force=force)

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Validate connection to MongoDB asynchronously."""
        return await super().validate_connection_async(force=force)

    # ------------------------------------------------------------------
    # Transport-layer stubs — satisfy new base.py ABC requirements
    # ------------------------------------------------------------------

    async def _execute_insert_one(self, doc: dict[str, Any]) -> Any:
        return await self.async_collection.insert_one(doc)

    async def _execute_insert_many(self, docs: list[dict[str, Any]]) -> Any:
        return await self.async_collection.insert_many(docs)

    async def _execute_aggregate(self, pipeline: list[dict[str, Any]]) -> Any:
        return self.async_collection.aggregate(pipeline)

    async def _execute_find(
        self,
        query: dict[str, Any],
        projection: dict[str, Any],
        skip: int,
        limit: int,
    ) -> Any:
        return self.async_collection.find(query, projection).skip(skip).limit(limit)

    async def _execute_delete_many(self, query: dict[str, Any]) -> Any:
        return await self.async_collection.delete_many(query)

    async def _execute_delete_one(self, query: dict[str, Any]) -> Any:
        return await self.async_collection.delete_one(query)

    async def _execute_count(self, query: dict[str, Any]) -> int:  # type: ignore[override]
        return cast(int, await self.async_collection.count_documents(query))

    async def _execute_distinct(self, field: str) -> list[Any]:  # type: ignore[override]
        return cast("list[Any]", await self.async_collection.distinct(field))

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

    async def has_existing_hashes_async(self, hashes: list[str]) -> set[str]:
        """Return the subset of ``hashes`` whose ``text_hash`` already exists.

        Args:
            hashes: List of text hashes to check.

        Returns
        -------
            Set of hashes that already exist in the collection. Empty if none
            match or ``hashes`` is empty.
        """
        if not hashes:
            return set()
        cursor = await self._execute_find(
            {"text_hash": {"$in": hashes}}, {"text_hash": 1}, skip=0, limit=0
        )
        docs = await cursor.to_list(length=None)
        return {
            str(doc["text_hash"]) for doc in docs if doc.get("text_hash") is not None
        }

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

        # Use vector search pipeline for local MongoDB
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        agg_cursor = self.async_collection.aggregate(pipeline)
        raw: list[dict[str, Any]] = await agg_cursor.to_list(length=None)
        return [_validate_search_result(r) for r in raw]

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
            query["source_file"] = {"$regex": re.escape(source_filter)}
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
                    "element_type": 1,
                    "chunk_text": 1,
                },
            )
            .skip(offset)
            .limit(limit)
        )

        raw: list[dict[str, Any]] = await cursor.to_list(length=None)
        return [_validate_chunk_info(r) for r in raw]

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

    async def get_stats_async(self) -> DatabaseStats:
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
