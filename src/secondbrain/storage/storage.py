"""Vector storage implementation for MongoDB."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
)

from secondbrain.config import Config, get_config
from secondbrain.exceptions import StorageConnectionError
from secondbrain.storage.models import DatabaseStats
from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.types import ChunkInfo, SearchResult
from secondbrain.utils.connections import ValidatableService
from secondbrain.utils.perf_monitor import async_timing, timing

logger = logging.getLogger(__name__)


class VectorStorage(ValidatableService):
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
        config = get_config()
        self.mongo_uri: str = mongo_uri or config.mongo_uri
        self.db_name: str = db_name or config.mongo_db
        self.collection_name: str = collection_name or config.mongo_collection
        self._config: Config = config
        self._client: MongoClient[Any] | None = None
        self._db: Database[Any] | None = None
        self._collection: Collection[Any] | None = None
        self._index_created: bool = False
        self._async_client: httpx.AsyncClient | None = None
        # Config-based retry settings
        self._index_ready_retry_count: int = config.index_ready_retry_count
        self._index_ready_retry_delay: float = config.index_ready_retry_delay
        super().__init__(cache_ttl=config.connection_cache_ttl)

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
        """Add ingestion timestamp to document metadata.

        Args:
            doc: Document to add timestamp to.

        Returns
        -------
            Document with updated timestamp (copy).
        """
        result = doc.copy()
        if "metadata" in result and "ingested_at" in result["metadata"]:
            result["metadata"]["ingested_at"] = datetime.now(UTC).isoformat()
        return result

    def _add_ingestion_timestamps(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add ingestion timestamps to multiple documents.

        Args:
            documents: List of documents to add timestamps to.

        Returns
        -------
            List of documents with updated timestamps.
        """
        now = datetime.now(UTC).isoformat()
        docs_with_timestamps: list[dict[str, Any]] = []

        for doc in documents:
            doc_copy = doc.copy()
            if "metadata" not in doc_copy:
                doc_copy["metadata"] = {}
            doc_copy["metadata"]["ingested_at"] = now
            docs_with_timestamps.append(doc_copy)

        return docs_with_timestamps

    def _wait_for_index_ready(self) -> None:
        """Wait for MongoDB vector search index to be ready.

        Uses exponential backoff: starts at 100ms, doubles each retry,
        max 2 seconds per wait. Total max wait time ~15 seconds.
        """
        self.ensure_index()

        base_delay = 0.1  # 100ms
        max_delay = 2.0  # 2 seconds
        delay = base_delay

        for attempt in range(self._index_ready_retry_count):
            try:
                for idx in self.collection.list_search_indexes():
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

            # Exponential backoff with max delay cap
            time.sleep(delay)
            delay = min(delay * 2, max_delay)  # Double delay, cap at 2s

        logger.warning("Vector search index may not be ready after maximum retries")

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
        """Wait for MongoDB vector search index to be ready asynchronously.

        Uses exponential backoff: starts at 100ms, doubles each retry,
        max 2 seconds per wait. Total max wait time ~15 seconds.
        """
        await asyncio.to_thread(self.ensure_index)

        base_delay = 0.1  # 100ms
        max_delay = 2.0  # 2 seconds
        delay = base_delay

        for attempt in range(self._index_ready_retry_count):
            try:
                indexes = await asyncio.to_thread(
                    lambda: list(self.collection.list_search_indexes())
                )
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
            delay = min(delay * 2, max_delay)  # Double delay, cap at 2s

        logger.warning("Vector search index may not be ready after maximum retries")

    def close(self) -> None:
        """Close resources and release connections."""
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
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
        """
        if self._client is None:
            self._client = MongoClient(
                self.mongo_uri,
                directConnection=True,
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                minPoolSize=10,
                maxIdleTimeMS=300000,
                waitQueueTimeoutMS=5000,
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

    def ensure_index(self) -> None:
        """Create vector index if it does not exist."""
        if self._index_created:
            return

        try:
            from pymongo.operations import SearchIndexModel

            existing_indexes = list(
                self.collection.list_search_indexes("embedding_index")
            )
            if existing_indexes:
                existing_index = existing_indexes[0]
                existing_dims = (
                    existing_index.get("definition", {})
                    .get("fields", [{}])[0]
                    .get("numDimensions")
                )
                current_dims = self._config.embedding_dimensions

                # Check if dimensions mismatch (handle None case)
                dims_mismatch = existing_dims is None or existing_dims != current_dims

                if dims_mismatch:
                    if existing_dims is None:
                        logger.info(
                            "Existing index dimensions unreadable. Dropping and recreating."
                        )
                    else:
                        logger.info(
                            "Dropping old index with %d dimensions to create new index with %d dimensions",
                            existing_dims,
                            current_dims,
                        )
                    try:
                        self.collection.drop_search_index("embedding_index")
                        logger.info("Dropped old index successfully")
                    except Exception as drop_err:
                        logger.error(
                            "Failed to drop old index: %s: %s",
                            type(drop_err).__name__,
                            drop_err,
                        )
                        raise

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
            _ = self.collection.create_search_index(model=search_index_model)
            logger.info(
                "Created vector index with dimensions=%d",
                self._config.embedding_dimensions,
            )
            self._index_created = True
        except Exception as e:
            logger.warning("Could not create index: %s: %s", type(e).__name__, e)
            self._index_created = False

    @timing("storage_store")
    def store(self, document: dict[str, Any]) -> str:
        """Store a document with embedding.

        Args:
            document: Document containing chunk_id, text, embedding, and metadata.

        Returns
        -------
            str: Stored document ID.
        """
        self._require_connection("store document")

        # Add timestamp and store
        doc = self._add_ingestion_timestamp(document)
        result = self.collection.insert_one(doc)
        return str(result.inserted_id)

    @timing("storage_store_batch")
    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents.

        Args:
            documents: List of documents to store.

        Returns
        -------
            int: Number of documents stored.
        """
        self._require_connection("store batch")

        # Add timestamps to all documents
        docs_with_timestamps = self._add_ingestion_timestamps(documents)

        result = self.collection.insert_many(docs_with_timestamps)
        return len(result.inserted_ids)

    @timing("storage_search")
    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar embeddings.

        Args:
            embedding: Query embedding vector.
            top_k: Number of results to return.
            source_filter: Filter by source file.
            file_type_filter: Filter by file type.

        Returns
        -------
            Sequence of search results.
        """
        self._require_connection("search")

        # Ensure index exists and wait for it to be ready
        self._wait_for_index_ready()

        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        results: list[SearchResult] = list(self.collection.aggregate(pipeline))
        return results

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
            if use_prefix_match:
                query["source_file"] = {"$regex": f"^{source_filter}"}
            else:
                query["source_file"] = {"$regex": source_filter}
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
                    "chunk_text": 1,
                },
            )
            .skip(offset)
            .limit(limit)
        )

        chunks: list[ChunkInfo] = list(cursor)
        return chunks

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
        return result.deleted_count

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
        return result.deleted_count

    def delete_all(self) -> int:
        """Delete all documents.

        Returns
        -------
            int: Number of deleted documents.
        """
        self._require_connection("delete all")

        result = self.collection.delete_many({})
        return result.deleted_count

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

        # Add timestamp and store
        doc = self._add_ingestion_timestamp(document)
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

        # Add timestamps to all documents
        docs_with_timestamps = self._add_ingestion_timestamps(documents)

        result = await asyncio.to_thread(
            lambda: self.collection.insert_many(docs_with_timestamps)
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

        await self._wait_for_index_ready_async()

        pipeline = build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        results: list[SearchResult] = list(
            await asyncio.to_thread(lambda: list(self.collection.aggregate(pipeline)))
        )
        return results

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
            query["source_file"] = {"$regex": source_filter}
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
                    "chunk_text": 1,
                },
            )
            .skip(offset)
            .limit(limit)
        )

        chunks: list[ChunkInfo] = list(await asyncio.to_thread(lambda: list(cursor)))
        return chunks

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
        return result.deleted_count

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
        return result.deleted_count

    async def delete_all_async(self) -> int:
        """Delete all documents asynchronously.

        Returns
        -------
            int: Number of deleted documents.
        """
        await self._require_connection_async("delete all")

        result = await asyncio.to_thread(lambda: self.collection.delete_many({}))
        return result.deleted_count

    def get_stats(self) -> DatabaseStats:
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
