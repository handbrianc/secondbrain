"""Abstract base class for vector storage implementations."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
import logging
import math
import re
from typing import Any

from bson.binary import Binary

from secondbrain.storage.pipeline import build_search_pipeline
from secondbrain.types import (
    ChunkInfo,
    SearchResult,
    _validate_chunk_info,
    _validate_search_result,
)

logger = logging.getLogger(__name__)


class BaseVectorStorage(ABC):
    """Abstract base for vector storage implementations.

    Provides all shared transformation logic (encoding, document preparation,
    timestamp handling, pipeline building).  Concrete subclasses provide only
    the transport-layer primitives (insert/aggregate/find/delete/count) and
    inherit the full public API from this class.

    Inheritance order recommended::

        class VectorStorage(ValidatableService, BaseVectorStorage):
            ...

        class AsyncVectorStorage(BaseVectorStorage):
            # ValidatableService methods resolved via getattr trick or delegation
            ...

    Subclasses MUST provide the following abstract transport methods::

        def _execute_insert_one(self, doc: dict[str, Any]) -> Any: ...
        def _execute_insert_many(self, docs: list[dict[str, Any]]) -> Any: ...
        def _execute_aggregate(self, pipeline: list[dict[str, Any]]) -> Any: ...
        def _execute_find(
            self,
            query: dict[str, Any],
            projection: dict[str, Any],
            skip: int,
            limit: int,
        ) -> Any: ...
        def _execute_delete_many(self, query: dict[str, Any]) -> Any: ...
        def _execute_delete_one(self, query: dict[str, Any]) -> Any: ...
        def _execute_count(self, query: dict[str, Any]) -> int: ...
        def _execute_distinct(self, field: str) -> list[Any]: ...

    Public API
    ----------
    store, store_batch, search, list_chunks, delete_by_source,
    delete_by_chunk_id, delete_all, get_stats (and their async counterparts).

    Shared helpers
    --------------
    _prepare_document_for_storage, _add_ingestion_timestamps,
    _build_search_pipeline, _require_connection, _wait_for_index_ready.

    Required subclass state
    -----------------------
    ``mongo_uri``, ``db_name``, ``collection_name``.
    """

    __slots__ = ()

    # ------------------------------------------------------------------
    # Required subclass state
    # ------------------------------------------------------------------

    mongo_uri: str
    db_name: str
    collection_name: str

    # ------------------------------------------------------------------
    # Encoding / embedding helpers (pure transformation, no I/O)
    # ------------------------------------------------------------------

    def _encode_embedding(self, embedding: list[float]) -> bytes:
        """Convert float list to binary float32 array."""
        import struct

        return struct.pack(f"{len(embedding)}f", *embedding)

    def _decode_embedding(
        self, binary: bytes, dimensions: int | None = None
    ) -> list[float]:
        """Convert binary float32 array back to float list."""
        import struct

        if dimensions is None:
            dimensions = len(binary) // 4  # 4 bytes per float32
        return list(struct.unpack(f"{dimensions}f", binary))

    def _normalize_embedding(self, embedding: bytes | list[float]) -> list[float]:
        """Normalize embedding to list format."""
        if isinstance(embedding, Binary):
            return self._decode_embedding(bytes(embedding))
        if isinstance(embedding, bytes):
            return self._decode_embedding(embedding)
        return embedding

    # ------------------------------------------------------------------
    # Document preparation helpers (called by concrete store methods)
    # ------------------------------------------------------------------

    def _prepare_embedding_for_storage(
        self, embedding: list[float]
    ) -> bytes | list[float]:
        """Prepare embedding for storage based on config.

        Args:
            embedding: List of floats to store.

        Returns:
            Binary data if binary format enabled, otherwise original list.
        """
        # NOTE: Binary format is deprecated. Kept for backward compat only.
        # Subclasses must set self._config to a Config-like object.
        config = getattr(self, "_config", None)
        if config and getattr(config, "embedding_storage_format", None) == "binary":
            return Binary(self._encode_embedding(embedding))
        return embedding

    def _prepare_document_for_storage(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Prepare document for storage with optimizations.

        Computes and injects the magnitude field for O(1) retrieval
        during search instead of O(d) recomputation.
        """
        result = doc.copy()
        if "embedding" in result:
            embedding = result["embedding"]
            # Compute magnitude from raw list[float] (before binary encoding)
            if isinstance(embedding, list) and len(embedding) > 0:
                result["magnitude"] = math.sqrt(sum(x * x for x in embedding))
            result["embedding"] = self._prepare_embedding_for_storage(
                result["embedding"]
            )
        return result

    def _add_ingestion_timestamps(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add ingestion timestamps to multiple documents.

        Supports both old (nested metadata) and new (flattened) formats.
        """
        from datetime import UTC, datetime

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

    def _add_ingestion_timestamp(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Add ingestion timestamp to a single document.

        Supports both old (nested metadata) and new (flattened) formats.
        """
        result = doc.copy()
        now_str = self._add_ingestion_timestamps([result])[0]["ingested_at"]

        # Replace the timestamp we just added (which came from our helper)
        if "ingested_at" in result:
            result["ingested_at"] = now_str
        elif "metadata" in result:
            result.setdefault("metadata", {})
            result["metadata"]["ingested_at"] = now_str

        return result

    # ------------------------------------------------------------------
    # Pipeline construction (stateless, pure function composition)
    # ------------------------------------------------------------------

    def _build_search_pipeline(
        self,
        embedding: list[float],
        *,
        top_k: int,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Construct the shared vector-search aggregation pipeline.

        Identical logic for sync and async transports – only the call site differs.
        """
        return build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

    # ------------------------------------------------------------------
    # Interface: connection validation (concrete classes get these from
    # ValidatableService via the same MRO that also gives us ABC.__new__)
    # ------------------------------------------------------------------

    @abstractmethod
    def validate_connection(
        self, force: bool = False
    ) -> bool: ...  # Provided by ValidatableService

    @abstractmethod
    async def validate_connection_async(
        self, force: bool = False
    ) -> bool: ...  # Provided by ValidatableService

    # ------------------------------------------------------------------
    # Connection guards (call into ValidatableService via subclass)
    # ------------------------------------------------------------------

    def _require_connection(self, operation: str = "database operation") -> None:
        """Synchronously validate connection before a storage operation.

        Raises
        ------
            StorageConnectionError: If MongoDB is unreachable.
        """
        # Result is False if unreachable; concrete class mixes in ValidatableService
        # which provides validate_connection() returning bool
        if not self.validate_connection():
            self._raise_connection_error(operation)

    async def _require_connection_async(
        self, operation: str = "database operation"
    ) -> None:
        """Asynchronously validate connection before a storage operation.

        Raises
        ------
            StorageConnectionError: If MongoDB is unreachable.
        """
        if not await self.validate_connection_async():
            self._raise_connection_error(operation)

    def _raise_connection_error(self, operation: str) -> None:
        """Raise StorageConnectionError with context."""
        from secondbrain.exceptions import StorageConnectionError

        raise StorageConnectionError(
            f"Cannot connect to MongoDB at {self.mongo_uri}. "
            f"Database: {self.db_name}, Collection: {self.collection_name}. "
            f"Operation: {operation}."
        )

    def _wait_for_index_ready(self) -> None:
        """No-op – local MongoDB has no Atlas Search index to wait for."""

    async def _wait_for_index_ready_async(self) -> None:
        """No-op – local MongoDB has no Atlas Search index to wait for."""
        # Atlas-search subclasses override this with polling logic

    # ------------------------------------------------------------------
    # Transport-layer abstracts – MUST be implemented by concrete classes
    # ------------------------------------------------------------------

    @abstractmethod
    def _execute_insert_one(self, doc: dict[str, Any]) -> Any:
        """Insert a single document and return the InsertOneResult."""

    @abstractmethod
    def _execute_insert_many(self, docs: list[dict[str, Any]]) -> Any:
        """Insert multiple documents and return the InsertManyResult."""

    @abstractmethod
    def _execute_aggregate(self, pipeline: list[dict[str, Any]]) -> Any:
        """Run an aggregation pipeline and return a cursor (iterable)."""

    @abstractmethod
    def _execute_find(
        self,
        query: dict[str, Any],
        projection: dict[str, Any],
        skip: int,
        limit: int,
    ) -> Any:
        """Execute a find query and return a cursor (iterable)."""

    @abstractmethod
    def _execute_delete_many(self, query: dict[str, Any]) -> Any:
        """Delete all matching documents and return DeleteResult."""

    @abstractmethod
    def _execute_delete_one(self, query: dict[str, Any]) -> Any:
        """Delete a single document and return DeleteResult."""

    @abstractmethod
    def _execute_count(self, query: dict[str, Any]) -> int:
        """Count matching documents."""

    @abstractmethod
    def _execute_distinct(self, field: str) -> list[Any]:
        """Get distinct values for a field."""

    # ------------------------------------------------------------------
    # Shared public API (template-method: builds on abstract transports)
    # ------------------------------------------------------------------

    def store(self, document: dict[str, Any]) -> str:
        """Store a document with embedding."""
        self._require_connection("store document")
        doc = self._prepare_document_for_storage(document)
        result = self._execute_insert_one(doc)
        return str(result.inserted_id)

    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Store multiple documents."""
        self._require_connection("store batch")
        docs_with_timestamps = self._add_ingestion_timestamps(documents)
        docs_prepared = [
            self._prepare_document_for_storage(doc) for doc in docs_with_timestamps
        ]
        result = self._execute_insert_many(docs_prepared)
        return len(result.inserted_ids)

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
        pipeline = self._build_search_pipeline(
            embedding=embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )
        raw: list[dict[str, Any]] = list(self._execute_aggregate(pipeline))
        return [_validate_search_result(r) for r in raw]

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        use_prefix_match: bool = True,
    ) -> list[ChunkInfo]:
        """List chunks with optional filters."""
        self._require_connection("list chunks")
        query: dict[str, Any] = {}
        if source_filter:
            escaped_filter = re.escape(source_filter)
            if use_prefix_match:
                query["source_file"] = {"$regex": f"^{escaped_filter}"}
            else:
                query["source_file"] = {"$regex": escaped_filter}
        if chunk_id:
            query["chunk_id"] = chunk_id
        projection = {
            "_id": 0,
            "chunk_id": 1,
            "source_file": 1,
            "page_number": 1,
            "chunk_text": 1,
        }
        cursor = self._execute_find(query, projection, skip=offset, limit=limit)
        raw: list[dict[str, Any]] = list(cursor)
        return [_validate_chunk_info(r) for r in raw]

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file."""
        self._require_connection("delete by source")
        result = self._execute_delete_many({"source_file": source})
        return int(result.deleted_count)

    def delete_by_chunk_id(self, chunk_id: str) -> int:
        """Delete a specific chunk."""
        self._require_connection("delete by chunk ID")
        result = self._execute_delete_one({"chunk_id": chunk_id})
        return int(result.deleted_count)

    def delete_all(self) -> int:
        """Delete all documents."""
        self._require_connection("delete all")
        result = self._execute_delete_many({})
        return int(result.deleted_count)

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        self._require_connection("get stats")
        total = self._execute_count({})
        unique_sources = len(self._execute_distinct("source_file"))
        return {
            "total_chunks": total,
            "unique_sources": unique_sources,
            "database": self.db_name,
            "collection": self.collection_name,
        }
