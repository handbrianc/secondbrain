"""Sync MongoDB vector storage backend (VectorStorage)."""

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
)

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
from secondbrain.utils.perf_monitor import async_timing, timing
from secondbrain.utils.tracing import trace_operation

logger = logging.getLogger(__name__)


class VectorStorage(ValidatableService, BaseVectorStorage):
    """Handles vector storage in MongoDB.

    Uses ValidatableService base class for connection validation with caching.
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        """Initialize vector storage.

        Args:
            mongo_uri: Override MongoDB URI.
            db_name: Override database name.
            collection_name: Override collection name.
        """
        cfg = config()
        self.mongo_uri: str = mongo_uri or cfg.mongo_uri
        self.db_name: str = db_name or cfg.mongo_db
        self.collection_name: str = collection_name or cfg.mongo_collection
        self._config: Config = cfg
        self._client: MongoClient[Any] | None = None
        self._db: Database[Any] | None = None
        self._collection: Collection[Any] | None = None
        self._index_created: bool = False
        self._async_client: httpx.AsyncClient | None = None
        self._index_ready_retry_count: int = cfg.index_ready_retry_count
        self._index_ready_retry_delay: float = cfg.index_ready_retry_delay
        super().__init__(cache_ttl=cfg.connection_cache_ttl)

    def _require_connection(self, operation: str = "database operation") -> None:
        """Validate MongoDB connection and raise StorageConnectionError if unavailable.

        Args:
            operation: Description of the operation being attempted.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.
        """
        if not self.validate_connection():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}. "
                f"Database: {self.db_name}, Collection: {self.collection_name}. "
                f"Operation: {operation}."
            )

    def _add_ingestion_timestamp(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Add ingestion timestamp to document.

        Supports both old (nested metadata) and new (flattened) formats.

        Args:
            doc: Document to add timestamp to.

        Returns
        -------
            Document with updated timestamp (copy).
        """
        result = doc.copy()
        now = datetime.now(UTC).isoformat()

        # Support new flattened format
        if "ingested_at" in result:
            result["ingested_at"] = now
        # Support old nested format for backward compatibility
        elif "metadata" in result and "ingested_at" in result["metadata"]:
            result["metadata"]["ingested_at"] = now

        return result

    def _wait_for_index_ready(self) -> None:
        """No-op for local MongoDB.

        Local MongoDB does not use Atlas Search indexes, so no waiting is needed.
        """
        pass

    async def _require_connection_async(
        self, operation: str = "database operation"
    ) -> None:
        """Validate MongoDB connection asynchronously and raise error if unavailable.

        Args:
            operation: Description of the operation being attempted.

        Raises
        ------
            StorageConnectionError: If MongoDB connection is unavailable.
        """
        if not await self.validate_connection_async():
            raise StorageConnectionError(
                f"Cannot connect to MongoDB at {self.mongo_uri}. "
                f"Database: {self.db_name}, Collection: {self.collection_name}. "
                f"Operation: {operation}."
            )

    async def _wait_for_index_ready_async(self) -> None:
        """No-op for local MongoDB.

        Local MongoDB does not use Atlas Search indexes, so no waiting is needed.
        """
        pass

    def close(self) -> None:
        """Close resources and release connections.

        Closes sync MongoClient and releases async client resources.
        Note: For proper async cleanup in async context, use aclose().
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
            # AsyncIOMotorClient.close() is synchronous-safe; motor stubs don't expose it on abstract base
            with contextlib.suppress(Exception):
                self._async_client.close()  # type: ignore[attr-defined]
            self._async_client = None

    async def aclose(self) -> None:
        """Close both sync and async MongoDB client instances.

        Closes the synchronous pymongo.MongoClient and releases any async
        HTTP client resources to prevent resource leaks.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __del__(self) -> None:
        """Destructor - cleanup resources."""
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None

    def __enter__(self) -> "VectorStorage":
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

    @property
    def client(self) -> MongoClient[Any]:
        """Get or create MongoDB client instance.

        Configured with connection pooling for optimal performance:
        - maxPoolSize: Maximum number of connections in the pool
        - minPoolSize: Minimum number of connections to maintain
        - maxIdleTimeMS: Maximum time a connection can idle
        - waitQueueTimeoutMS: Timeout for waiting for available connection

        MAGIC NUMBER RATIONALE:
        -----------------------
        - maxPoolSize=50: Sufficient for concurrent batch processing
          Typical ingestion: 10-20 parallel files, each needs 2-3 connections
          (read, write, index check). 50 provides headroom without exhaustion.

        - minPoolSize=10: Maintains warm connection pool
          Prevents connection latency on first request
          10 connections ~ 5-10MB memory overhead, acceptable trade-off

        - maxIdleTimeMS=300000 (5 min): Reap idle connections
          Prevents MongoDB from closing idle connections (default 10 min)
          Proactive cleanup avoids "socket closed" errors

        - serverSelectionTimeoutMS=5000 (5s): Fail fast on connection issues
          Too short: False positives on network hiccups
          Too long: Poor UX on actual failures
          5s balances responsiveness with reliability

        - waitQueueTimeoutMS=5000 (5s): Timeout if pool exhausted
          Indicates overload condition (shouldn't happen with 50 pool size)
          Fail fast rather than hang indefinitely
        """
        if self._client is None:
            self._client = MongoClient(
                self.mongo_uri,
                directConnection=True,
                serverSelectionTimeoutMS=10000,
                maxPoolSize=100,
                minPoolSize=20,
                maxIdleTimeMS=300000,
                waitQueueTimeoutMS=10000,
            )
        return self._client

    @property
    def db(self) -> Database[Any]:
        """Get or create database instance."""
        if self._db is None:
            self._db = self.client[self.db_name]
        return self._db

    @property
    def collection(self) -> Collection[Any]:
        """Get or create collection instance."""
        if self._collection is None:
            self._collection = self.db[self.collection_name]
        return self._collection

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create the HTTPX async client instance.

        Returns
        -------
            httpx.AsyncClient instance for async HTTP operations.
        """
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=60.0)
        return self._async_client

    async def _request_async(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Make an asynchronous HTTP request."""
        return await self.async_client.request(method, url, **kwargs)

    async def _do_validate_async(self) -> bool:
        """Async version of MongoDB validation.

        Uses asyncio.to_thread() to run synchronous MongoDB operations.

        Returns
        -------
            True if connection is valid, False otherwise.
        """
        try:
            _ = await asyncio.to_thread(lambda: self.client.admin.command("ping"))
            return True
        except Exception:
            return False

    def _do_validate(self) -> bool:
        """Validate synchronous MongoDB connection.

        Returns
        -------
            True if connection is valid, False otherwise.
        """
        try:
            _ = self.client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError):
            return False

    # ------------------------------------------------------------------
    # Transport-layer stubs — satisfy new base.py ABC requirements
    # ------------------------------------------------------------------

    def _execute_insert_one(self, doc: dict[str, Any]) -> Any:
        return self.collection.insert_one(doc)

    def _execute_insert_many(self, docs: list[dict[str, Any]]) -> Any:
        return self.collection.insert_many(docs)

    def _execute_aggregate(self, pipeline: list[dict[str, Any]]) -> Any:
        return self.collection.aggregate(pipeline)

    def _execute_find(
        self,
        query: dict[str, Any],
        projection: dict[str, Any],
        skip: int,
        limit: int,
    ) -> Any:
        return self.collection.find(query, projection).skip(skip).limit(limit)

    def _execute_delete_many(self, query: dict[str, Any]) -> Any:
        return self.collection.delete_many(query)

    def _execute_delete_one(self, query: dict[str, Any]) -> Any:
        return self.collection.delete_one(query)

    def _execute_count(self, query: dict[str, Any]) -> int:
        return cast(int, self.collection.count_documents(query))

    def _execute_distinct(self, field: str) -> list[Any]:
        return cast("list[Any]", self.collection.distinct(field))

    def ensure_index(self) -> None:
        """Create indexes for local MongoDB.

        Creates B-tree indexes for filter fields (source_file, file_type).
        NOTE: Vector search still uses O(n) cosine similarity in aggregation.
        """
        try:
            self.collection.create_index(
                [("source_file", 1)],
                name="ix_source_file",
                background=True,
            )
            self.collection.create_index(
                [("file_type", 1)],
                name="ix_file_type",
                background=True,
            )
        except Exception as e:
            logger.warning(
                "Failed to create filter indexes (non-fatal): %s: %s",
                type(e).__name__,
                e,
            )
        # Always use fallback search for local MongoDB
        self._index_created = False
        logger.debug("Using local MongoDB without Atlas Search indexes")

    @timing("storage_store")
    def store(self, document: dict[str, Any]) -> str:
        """Store a document with embedding."""
        self._require_connection("store document")

        doc = self._prepare_document_for_storage(document)
        with trace_operation("storage_insert_one"):
            result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    @timing("storage_store_batch")
    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents."""
        self._require_connection("store batch")

        # Add timestamps to all documents (supports both old and new formats)
        docs_with_timestamps = self._add_ingestion_timestamps(documents)

        docs_prepared = [
            self._prepare_document_for_storage(doc) for doc in docs_with_timestamps
        ]

        with trace_operation("storage_insert_many"):
            result = self.collection.insert_many(docs_prepared)
        return len(result.inserted_ids)

    @timing("storage_search")
    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar embeddings."""
        self._require_connection("search")

        self._wait_for_index_ready()

        # Use vector search pipeline for local MongoDB
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        with trace_operation("storage_aggregate"):
            raw: list[dict[str, Any]] = list(self.collection.aggregate(pipeline))
        return [_validate_search_result(r) for r in raw]

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        use_prefix_match: bool = True,
    ) -> list[ChunkInfo]:
        """List chunks with optional filters.

        Uses indexed queries where possible for better performance.

        Args:
            source_filter: Filter by source file.
            chunk_id: Filter by specific chunk ID.
            limit: Maximum number of results to return.
            offset: Pagination offset.
            use_prefix_match: If True, use $regex with anchored prefix for better index usage.

        Returns
        -------
            list of ChunkInfo objects.
        """
        self._require_connection("list chunks")

        query: dict[str, Any] = {}
        if source_filter:
            # Escape regex special characters to prevent regex injection
            escaped_filter = re.escape(source_filter)
            if use_prefix_match:
                query["source_file"] = {"$regex": f"^{escaped_filter}"}
            else:
                query["source_file"] = {"$regex": escaped_filter}
        if chunk_id:
            query["chunk_id"] = chunk_id

        cursor = (
            self.collection.find(
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

        raw: list[dict[str, Any]] = list(cursor)
        return [_validate_chunk_info(r) for r in raw]

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file.

        Args:
            source: Source file path.

        Returns
        -------
            int: Number of deleted documents.
        """
        self._require_connection("delete by source")

        result = self.collection.delete_many({"source_file": source})
        return int(result.deleted_count)

    def delete_by_chunk_id(self, chunk_id: str) -> int:
        """Delete a specific chunk.

        Args:
            chunk_id: Chunk ID.

        Returns
        -------
            int: Number of deleted documents.
        """
        self._require_connection("delete by chunk ID")

        result = self.collection.delete_one({"chunk_id": chunk_id})
        return int(result.deleted_count)

    def delete_all(self) -> int:
        """Delete all documents.

        Returns
        -------
            int: Number of deleted documents.
        """
        self._require_connection("delete all")

        result = self.collection.delete_many({})
        return int(result.deleted_count)

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Check if MongoDB connection is available asynchronously.

        Args:
            force: If True, bypass cache and check connection.

        Returns
        -------
            True if connection is valid, False otherwise.
        """
        current_time = time.monotonic()

        if (
            not force
            and self._connection_valid is not None
            and current_time - self._connection_checked_at < self._connection_cache_ttl
        ):
            return self._connection_valid

        try:
            self._connection_valid = await asyncio.to_thread(self._do_validate)
        except Exception as e:
            logger.debug(
                "MongoDB async connection validation failed: %s: %s",
                type(e).__name__,
                e,
            )
            self._connection_valid = False

        self._connection_checked_at = current_time
        return self._connection_valid

    @async_timing("storage_store_async")
    async def store_async(self, document: dict[str, Any]) -> str:
        """Store a document with embedding asynchronously.

        Args:
            document: Document containing chunk_id, text, embedding, and metadata.

        Returns
        -------
            str: Stored document ID.
        """
        await self._require_connection_async("store document")

        doc = self._prepare_document_for_storage(document)
        result = await asyncio.to_thread(lambda: self.collection.insert_one(doc))
        return str(result.inserted_id)

    @async_timing("storage_store_batch_async")
    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents asynchronously.

        Args:
            documents: List of documents to store.

        Returns
        -------
            int: Number of documents stored.
        """
        await self._require_connection_async("store batch")

        # Add timestamps to all documents (supports both old and new formats)
        docs_with_timestamps = self._add_ingestion_timestamps(documents)

        docs_prepared = [
            self._prepare_document_for_storage(doc) for doc in docs_with_timestamps
        ]

        result = await asyncio.to_thread(
            lambda: self.collection.insert_many(docs_prepared)
        )
        return len(result.inserted_ids)

    @async_timing("storage_search_async")
    async def search_async(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar embeddings asynchronously.

        Args:
            embedding: Query embedding vector.
            top_k: Number of results to return.
            source_filter: Filter by source file.
            file_type_filter: Filter by file type.

        Returns
        -------
            Sequence of search results.
        """
        await self._require_connection_async("search")

        # Use vector search pipeline for local MongoDB
        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        raw: list[dict[str, Any]] = list(
            await asyncio.to_thread(lambda: list(self.collection.aggregate(pipeline)))
        )
        return [_validate_search_result(r) for r in raw]

    async def list_chunks_async(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChunkInfo]:
        """List chunks with optional filters asynchronously.

        Args:
            source_filter: Filter by source file.
            chunk_id: Filter by specific chunk ID.
            limit: Maximum number of results to return.
            offset: Pagination offset.

        Returns
        -------
            list of ChunkInfo objects.
        """
        await self._require_connection_async("list chunks")

        query: dict[str, Any] = {}
        if source_filter:
            query["source_file"] = {"$regex": re.escape(source_filter)}
        if chunk_id:
            query["chunk_id"] = chunk_id

        cursor = (
            self.collection.find(
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

        raw: list[dict[str, Any]] = list(await asyncio.to_thread(lambda: list(cursor)))
        return [_validate_chunk_info(r) for r in raw]

    async def delete_by_source_async(self, source: str) -> int:
        """Delete all chunks from a source file asynchronously.

        Args:
            source: Source file path.

        Returns
        -------
            int: Number of deleted documents.
        """
        await self._require_connection_async("delete by source")

        result = await asyncio.to_thread(
            lambda: self.collection.delete_many({"source_file": source})
        )
        return int(result.deleted_count)

    async def delete_by_chunk_id_async(self, chunk_id: str) -> int:
        """Delete a specific chunk asynchronously.

        Args:
            chunk_id: Chunk ID.

        Returns
        -------
            int: Number of deleted documents.
        """
        await self._require_connection_async("delete by chunk ID")

        result = await asyncio.to_thread(
            lambda: self.collection.delete_one({"chunk_id": chunk_id})
        )
        return int(result.deleted_count)

    async def delete_all_async(self) -> int:
        """Delete all documents asynchronously.

        Returns
        -------
            int: Number of deleted documents.
        """
        await self._require_connection_async("delete all")

        result = await asyncio.to_thread(lambda: self.collection.delete_many({}))
        return int(result.deleted_count)

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns
        -------
            DatabaseStats: Statistics dictionary.
        """
        self._require_connection("get stats")

        total = self.collection.count_documents({})
        unique_sources = len(self.collection.distinct("source_file"))

        return {
            "total_chunks": total,
            "unique_sources": unique_sources,
            "database": self.db_name,
            "collection": self.collection_name,
        }

    async def get_stats_async(self) -> DatabaseStats:
        """Get database statistics asynchronously.

        Returns
        -------
            DatabaseStats: Statistics dictionary.
        """
        await self._require_connection_async("get stats")

        total = await asyncio.to_thread(self.collection.count_documents, {})
        unique_sources = await asyncio.to_thread(
            lambda: len(self.collection.distinct("source_file"))
        )

        return cast(
            DatabaseStats,
            {
                "total_chunks": total,
                "unique_sources": unique_sources,
                "database": self.db_name,
                "collection": self.collection_name,
            },
        )
