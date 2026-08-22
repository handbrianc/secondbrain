"""Qdrant vector storage backend for SecondBrain.

Replaces the MongoDB vector store. All chunk metadata (including
``chunk_text``) lives in the Qdrant payload, so ``search`` returns everything
the Searcher needs in a single round trip. The payload uses *top-level* keys
(nested ``metadata`` is intentionally avoided).

This module imports ``qdrant_client`` at runtime only — construction never
touches the network and never requires a running Qdrant server (the client and
collection are created lazily on first write/search).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
import uuid
from collections.abc import Sequence
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from secondbrain.config import config
from secondbrain.types import (
    ChunkInfo,
    SearchResult,
    _validate_chunk_info,
    _validate_search_result,
)

logger = logging.getLogger(__name__)

_INDEXED_FIELDS = (
    "source_file",
    "file_type",
    "chunk_id",
    "text_hash",
    "chapter_id",
    "section_id",
)

_OUTPUT_KEYS = (
    "chunk_id",
    "source_file",
    "page_number",
    "chunk_text",
    "element_type",
    "chunk_role",
    "section_label",
)

_CONNECTION_TTL = 60.0


class QdrantVectorStorage:
    """Production vector/metadata storage backed by Qdrant.

    Implements :class:`~secondbrain.storage.protocol.VectorStorageProtocol`.
    The client and collection are created lazily so the object can be built
    without a running Qdrant server.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        cfg = config()
        self.url = url or cfg.qdrant_url
        self.api_key = api_key if api_key is not None else cfg.qdrant_api_key
        self.collection_name = collection_name or cfg.qdrant_collection
        self._dimensions = cfg.embedding_dimensions
        self._client: QdrantClient | None = None
        self._collection_ready = False
        self._collection_lock = threading.Lock()
        self._conn_valid: bool | None = None
        self._conn_checked_at: float = 0.0

    # ------------------------------------------------------------------
    # Client / collection management (lazy)
    # ------------------------------------------------------------------

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=self.url, api_key=self.api_key, check_compatibility=False
            )
        return self._client

    def _ensure_collection(self) -> None:
        """Provision collection + payload indexes once per instance (locked)."""
        if self._collection_ready:
            return
        with self._collection_lock:
            if self._collection_ready:
                return
            client = self._get_client()
            try:
                existing = {c.name for c in client.get_collections().collections}
                if self.collection_name not in existing:
                    client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=self._dimensions,
                            distance=models.Distance.COSINE,
                        ),
                    )
                for field in _INDEXED_FIELDS:
                    client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field,
                        field_schema=models.PayloadSchemaType.KEYWORD,
                    )
                self._collection_ready = True
            except Exception:  # pragma: no cover - server-dependent path
                logger.debug("Qdrant collection provisioning failed", exc_info=True)
                raise

    # ------------------------------------------------------------------
    # Payload / filter helpers (pure)
    # ------------------------------------------------------------------

    @staticmethod
    def _match_value_condition(key: str, value: Any) -> models.Condition:
        return models.FieldCondition(key=key, match=models.MatchValue(value=value))

    @staticmethod
    def _match_text_condition(key: str, value: str) -> models.Condition:
        return models.FieldCondition(key=key, match=models.MatchText(text=value))

    @staticmethod
    def _key_conditions(key: str, value: Any) -> list[models.Condition]:
        """Build OR-conditions for a keyword match, coercing plain ints.

        Stored numeric ids (e.g. ``chapter_id``) may be ints while the caller
        passes a string; Qdrant ``MatchValue`` is type-strict, so match both
        forms for a plain-integer string.
        """
        conditions: list[models.Condition] = [
            models.FieldCondition(key=key, match=models.MatchValue(value=value))
        ]
        if isinstance(value, str):
            try:
                as_int = int(value)
                if str(as_int) == value:
                    conditions.append(
                        models.FieldCondition(
                            key=key, match=models.MatchValue(value=as_int)
                        )
                    )
            except ValueError:
                pass
        return conditions

    def _build_search_filter(
        self,
        source_filter: str | None,
        file_type_filter: str | None,
    ) -> models.Filter | None:
        conditions: list[models.Condition] = []
        if source_filter:
            conditions.append(self._match_text_condition("source_file", source_filter))
        if file_type_filter:
            conditions.append(
                self._match_value_condition("file_type", file_type_filter)
            )
        if not conditions:
            return None
        return models.Filter(must=conditions)

    @staticmethod
    def _payload_to_chunk(payload: dict[str, Any]) -> dict[str, Any]:
        return {key: payload.get(key) for key in _OUTPUT_KEYS}

    def _point_to_search_result(
        self, point: Any, payload: dict[str, Any]
    ) -> dict[str, Any]:
        result = self._payload_to_chunk(payload)
        result["score"] = float(point.score)
        return result

    # ------------------------------------------------------------------
    # Scroll helper (cursor pagination, offset applied in-process)
    # ------------------------------------------------------------------

    def _scroll_records(
        self,
        scroll_filter: models.Filter | None,
        limit: int | None,
    ) -> list[Any]:
        records: list[Any] = []
        next_offset: Any = None
        while True:
            remaining = None if limit is None else limit - len(records)
            if remaining is not None and remaining <= 0:
                break
            page_size = min(remaining, 256) if remaining is not None else 256
            points, next_offset = self._get_client().scroll(
                collection_name=self.collection_name,
                scroll_filter=scroll_filter,
                limit=page_size,
                offset=next_offset,
                with_payload=True,
            )
            records.extend(points)
            if not points or next_offset is None:
                break
        return records

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar chunks; apply a payload filter when given."""
        self._ensure_collection()
        query_filter = self._build_search_filter(source_filter, file_type_filter)
        resp = self._get_client().query_points(
            collection_name=self.collection_name,
            query=embedding,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        results: list[SearchResult] = []
        for point in resp.points:
            payload = dict(point.payload or {})
            results.append(
                _validate_search_result(self._point_to_search_result(point, payload))
            )
        return results

    async def search_async(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Async wrapper over :meth:`search`."""
        return await asyncio.to_thread(
            self.search, embedding, top_k, source_filter, file_type_filter
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        """Derive a valid Qdrant point id (UUID) from a chunk_id.

        Qdrant point ids must be integers or UUIDs. Stored ``chunk_id`` values
        are uuid4 strings, but arbitrary ids are handled by hashing to a stable
        UUID v5. Lookup always filters on the payload ``chunk_id`` field, so the
        point id shape does not affect search/delete.
        """
        try:
            return str(uuid.UUID(chunk_id))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))

    def _point_from_document(self, document: dict[str, Any]) -> models.PointStruct:
        chunk_id = str(document["chunk_id"])
        payload = {k: v for k, v in document.items() if k != "embedding"}
        return models.PointStruct(
            id=self._point_id(chunk_id),
            vector=document.get("embedding", []),
            payload=payload,
        )

    def store(self, document: dict[str, Any]) -> str:
        """Upsert a single point; return its id."""
        self._ensure_collection()
        point = self._point_from_document(document)
        self._get_client().upsert(
            collection_name=self.collection_name,
            points=[point],
        )
        return str(point.id)

    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Upsert a batch of points; return the number of documents."""
        if not documents:
            return 0
        self._ensure_collection()
        points = [self._point_from_document(doc) for doc in documents]
        self._get_client().upsert(
            collection_name=self.collection_name,
            points=points,
        )
        return len(documents)

    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        """Async wrapper over :meth:`store_batch`."""
        return await asyncio.to_thread(self.store_batch, documents)

    # ------------------------------------------------------------------
    # Metadata reads
    # ------------------------------------------------------------------

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        use_prefix_match: bool = True,
    ) -> Sequence[ChunkInfo]:
        """List chunks with optional filters and offset/limit pagination."""
        self._ensure_collection()
        conditions: list[models.Condition] = []
        if source_filter:
            conditions.append(
                self._match_text_condition("source_file", source_filter)
                if use_prefix_match
                else self._match_value_condition("source_file", source_filter)
            )
        if chunk_id:
            conditions.append(self._match_value_condition("chunk_id", chunk_id))
        scroll_filter = models.Filter(must=conditions) if conditions else None
        records = self._scroll_records(scroll_filter, limit + offset)
        selected = records[offset : offset + limit]
        return [
            _validate_chunk_info(self._payload_to_chunk(dict(p.payload or {})))
            for p in selected
        ]

    def list_source_files(self) -> list[str]:
        """Distinct ``source_file`` values (facet, else scroll-and-dedupe)."""
        self._ensure_collection()
        try:
            resp = self._get_client().facet(
                collection_name=self.collection_name,
                key="source_file",
            )
            seen: set[str] = set()
            for bucket in resp.hits:
                value = bucket.value
                if isinstance(value, str) and value not in seen:
                    seen.add(value)
            return sorted(seen)
        except (AttributeError, TypeError):
            seen = set()
            for record in self._scroll_records(None, None):
                src = (record.payload or {}).get("source_file")
                if isinstance(src, str) and src not in seen:
                    seen.add(src)
            return sorted(seen)

    def has_existing_hashes(self, hashes: list[str]) -> set[str]:
        """Return the subset of ``hashes`` whose ``text_hash`` already exists."""
        if not hashes:
            return set()
        self._ensure_collection()
        condition: models.Condition = models.FieldCondition(
            key="text_hash",
            match=models.MatchAny(any=hashes),
        )
        records = self._scroll_records(models.Filter(must=[condition]), None)
        return {
            str(p.payload["text_hash"])
            for p in records
            if (p.payload or {}).get("text_hash") is not None
        }

    # ------------------------------------------------------------------
    # Document-structure scans (replaces Mongo ``collection`` reaches)
    # ------------------------------------------------------------------

    def get_source_chunks(
        self,
        source_file: str,
        *,
        limit: int | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Chunks of a source, ordered by ``page_number``."""
        self._ensure_collection()
        condition = self._match_value_condition("source_file", source_file)
        records = self._scroll_records(models.Filter(must=[condition]), None)
        records.sort(key=lambda p: (p.payload or {}).get("page_number") or 0)
        if limit is not None:
            records = records[:limit]
        chunks: list[ChunkInfo] = []
        for p in records:
            payload = dict(p.payload or {})
            if not with_text:
                payload.pop("chunk_text", None)
            chunks.append(_validate_chunk_info(self._payload_to_chunk(payload)))
        return chunks

    def find_chunks(
        self,
        source_file: str | None = None,
        *,
        chapter_id: str | None = None,
        section_id: str | None = None,
        section_id_pattern: str | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Chunks matching equality filters; optional Python regex on section_id."""
        self._ensure_collection()
        must_conds: list[models.Condition] = []
        if source_file:
            must_conds.append(
                models.Filter(should=self._key_conditions("source_file", source_file))
            )
        if chapter_id:
            must_conds.append(
                models.Filter(should=self._key_conditions("chapter_id", chapter_id))
            )
        if section_id:
            must_conds.append(
                models.Filter(should=self._key_conditions("section_id", section_id))
            )
        records = self._scroll_records(
            models.Filter(must=must_conds) if must_conds else None,
            None,
        )
        if section_id_pattern:
            pattern = re.compile(section_id_pattern)
            records = [
                p
                for p in records
                if pattern.search(str((p.payload or {}).get("section_id") or ""))
            ]
        chunks: list[ChunkInfo] = []
        for p in records:
            payload = dict(p.payload or {})
            if not with_text:
                payload.pop("chunk_text", None)
            chunks.append(_validate_chunk_info(self._payload_to_chunk(payload)))
        return chunks

    def find_structural_chunks(
        self,
        element_types: list[str] | None = None,
        chunk_roles: list[str] | None = None,
        source_prefix: str | None = None,
        limit: int | None = None,
    ) -> Sequence[ChunkInfo]:
        """Chunks that carry a structural role, ordered by ascending page number.

        Matches chunks whose ``element_type`` is in *element_types* OR whose
        ``chunk_role`` is in *chunk_roles* (Qdrant ``should`` = logical OR).
        When both lists are empty/None every chunk matches — this is used as the
        "all chunks" fallback when structure probing returns too few candidates.
        If *source_prefix* is given, only chunks whose ``source_file`` starts
        with that prefix are considered. Results are ordered by ascending
        ``page_number`` and truncated to *limit*.

        Ports the Mongo ``_probe_document_structure`` OR-filter
        (``{"$or": [{"element_type": {"$in": [...]}}, {"chunk_role": {"$in": [...]}}]}``)
        plus its ``{"source_file": {"$regex": "^<prefix>"}}`` scoping.
        """
        self._ensure_collection()
        should: list[models.Condition] = []
        if element_types:
            should.append(
                models.FieldCondition(
                    key="element_type",
                    match=models.MatchAny(any=element_types),
                )
            )
        if chunk_roles:
            should.append(
                models.FieldCondition(
                    key="chunk_role",
                    match=models.MatchAny(any=chunk_roles),
                )
            )
        must: list[models.Condition] = []
        if source_prefix:
            must.append(self._match_text_condition("source_file", source_prefix))
        scroll_filter = (
            models.Filter(must=must, should=should) if (must or should) else None
        )
        records = self._scroll_records(scroll_filter, None)
        records.sort(key=lambda p: (p.payload or {}).get("page_number") or 0)
        if limit is not None:
            records = records[:limit]
        return [
            _validate_chunk_info(self._payload_to_chunk(dict(p.payload or {})))
            for p in records
        ]

    def get_body_chunks(
        self,
        source_file: str,
        *,
        limit: int | None = None,
        page_gte: int | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Return a source's body chunks (``chunk_role == 'body'``) ordered by page.

        Mirrors the Mongo ``coll.find({"source_file": src, "chunk_role": "body"},
        {...}).sort("page_number", 1).limit(n)`` reads used by the chapter/section
        reconstruction path. If *page_gte* is given, only chunks on or after that
        page are returned (used for appendix extraction); the page filter is
        applied before the *limit* so the truncation is exact.
        """
        self._ensure_collection()
        conditions: list[models.Condition] = [
            self._match_value_condition("source_file", source_file),
            self._match_value_condition("chunk_role", "body"),
        ]
        if page_gte is not None:
            conditions.append(
                models.FieldCondition(
                    key="page_number",
                    range=models.Range(gte=page_gte),
                )
            )
        records = self._scroll_records(models.Filter(must=conditions), None)
        records.sort(key=lambda p: (p.payload or {}).get("page_number") or 0)
        if limit is not None:
            records = records[:limit]
        chunks: list[ChunkInfo] = []
        for p in records:
            payload = dict(p.payload or {})
            if not with_text:
                payload.pop("chunk_text", None)
            chunks.append(_validate_chunk_info(self._payload_to_chunk(payload)))
        return chunks

    def count_chunks(
        self,
        source_file: str | None = None,
        chunk_role: str | None = None,
    ) -> int:
        """Count chunks matching optional ``source_file`` / ``chunk_role`` filters.

        Mirrors the Mongo ``coll.count_documents({"source_file": s,
        "chunk_role": "body"})`` used by the chapter-enumeration path to pick the
        source with the most body chunks. Filters are exact keyword matches.
        """
        self._ensure_collection()
        conditions: list[models.Condition] = []
        if source_file:
            conditions.append(self._match_value_condition("source_file", source_file))
        if chunk_role:
            conditions.append(self._match_value_condition("chunk_role", chunk_role))
        scroll_filter = models.Filter(must=conditions) if conditions else None
        return int(
            self._get_client()
            .count(
                collection_name=self.collection_name,
                count_filter=scroll_filter,
                exact=True,
            )
            .count
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(self, scroll_filter: models.Filter | None) -> int:
        self._ensure_collection()
        if scroll_filter is None:
            scroll_filter = models.Filter(must=[])
        count = (
            self._get_client()
            .count(
                collection_name=self.collection_name,
                count_filter=scroll_filter,
                exact=True,
            )
            .count
        )
        self._get_client().delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(filter=scroll_filter),
        )
        return int(count)

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file; return the count."""
        return self._delete(
            models.Filter(must=[self._match_value_condition("source_file", source)])
        )

    def delete_by_chunk_id(self, chunk_id: str) -> int:
        """Delete a specific chunk; return the count (0 or 1)."""
        return self._delete(
            models.Filter(must=[self._match_value_condition("chunk_id", chunk_id)])
        )

    def delete_all(self) -> int:
        """Delete all chunks; return the count."""
        return self._delete(None)

    # ------------------------------------------------------------------
    # Stats / lifecycle
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Stats matching the Mongo ``get_stats`` shape for the ``status`` CLI."""
        self._ensure_collection()
        total = (
            self._get_client()
            .count(
                collection_name=self.collection_name,
                exact=True,
            )
            .count
        )
        return {
            "total_chunks": total,
            "unique_sources": len(self.list_source_files()),
            "database": "qdrant",
            "collection": self.collection_name,
        }

    def validate_connection(self, force: bool = False) -> bool:
        """TTL-cached reachability probe; returns False on failure, never raises."""
        now = time.monotonic()
        if (
            not force
            and self._conn_valid is not None
            and (now - self._conn_checked_at) < _CONNECTION_TTL
        ):
            return self._conn_valid
        try:
            self._get_client().get_collections()
            self._conn_valid = True
        except Exception:
            self._conn_valid = False
        self._conn_checked_at = now
        return self._conn_valid

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Async wrapper over :meth:`validate_connection`."""
        return await asyncio.to_thread(self.validate_connection, force)

    def _wait_for_index_ready(self, *args: Any, **kwargs: Any) -> None:
        """No-op: Qdrant creates indexes synchronously (docker_manager calls this)."""

    def close(self) -> None:
        """Close the underlying client if it was ever created."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                logger.debug("Error closing Qdrant client", exc_info=True)
            self._client = None

    def __enter__(self) -> QdrantVectorStorage:
        """Context-manager entry; return self for use."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context-manager exit; close the client."""
        self.close()


__all__ = ["QdrantVectorStorage"]
