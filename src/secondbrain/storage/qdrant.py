"""Qdrant vector storage backend for SecondBrain.

The Qdrant vector store. All chunk metadata (including
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
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from secondbrain.config import config
from secondbrain.constants import MAX_LIST_LIMIT
from secondbrain.types import (
    ChunkInfo,
    SearchResult,
    _validate_chunk_info,
    _validate_search_result,
)
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
)
from secondbrain.utils.tracing import trace_operation

if TYPE_CHECKING:
    from secondbrain.storage.structure_sqlite import DocumentStructure

logger = logging.getLogger(__name__)

_INDEXED_FIELDS = (
    "source_file",
    "file_type",
    "chunk_id",
    "text_hash",
    "chapter_id",
    "section_id",
    "chunk_role",
    "printed_page",
)

# Points per refresh_structural_payload scroll/upsert round (~256 dense
# vectors ≈ 2 MB per round, design §7).
_REFRESH_BATCH_SIZE = 256

_OUTPUT_KEYS = (
    "chunk_id",
    "source_file",
    "page_number",
    "printed_page",
    "page_pos",
    "chunk_text",
    "element_type",
    "chunk_role",
    "section_label",
    "node_id",
    "chapter_id",
    "section_id",
    "heading_path",
    "t_start",
    "t_end",
)

_CONNECTION_TTL = 60.0


@contextmanager
def _traced_qdrant_operation(
    collection: str, operation: str, **attributes: Any
) -> Generator[Any]:
    """Span for a Qdrant client operation.

    Emits a ``qdrant_<operation>`` span carrying the collection name and the
    operation type (``qdrant.collection`` / ``qdrant.operation``), so slow or
    failing Qdrant work is identifiable per collection in traces. Extra
    *attributes* are stamped on the span when tracing is enabled.

    When tracing is disabled ``trace_operation`` yields ``None`` and the span
    degenerates to plain execution (zero overhead), mirroring the
    ``if span:`` pattern used in :mod:`secondbrain.search`.
    """
    with trace_operation(f"qdrant_{operation}") as span:
        if span is not None:
            span.set_attribute("qdrant.collection", collection)
            span.set_attribute("qdrant.operation", operation)
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(f"qdrant.{key}", value)
        yield span


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
        circuit_breaker_config: CircuitBreakerConfig | None = None,
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
        # Circuit breaker for the connection-validation path. Constructed with
        # a config (``StorageFactory``) → enabled; ``None`` → disabled, which
        # leaves ``validate_connection`` behaving exactly as before.
        self._circuit_breaker_enabled = circuit_breaker_config is not None
        self._circuit_breaker: CircuitBreaker | None = None
        if self._circuit_breaker_enabled and circuit_breaker_config is not None:
            self._circuit_breaker = CircuitBreaker(
                config=circuit_breaker_config,
                service_name=self.__class__.__name__,
            )

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
                    try:
                        client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name=field,
                            field_schema=models.PayloadSchemaType.KEYWORD,
                        )
                    except Exception as index_error:
                        # Idempotent provisioning (design §7): an index that
                        # already exists (or is rejected by the server) must
                        # not fail collection setup — the field still
                        # round-trips inside payloads, only the server-side
                        # index is skipped.
                        logger.debug(
                            "Payload index %r not created: %s: %s",
                            field,
                            type(index_error).__name__,
                            index_error,
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
                logger.debug("Keyword %r is not a plain integer; no int match", value)
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
        with _traced_qdrant_operation(self.collection_name, "scroll", limit=limit):
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
        with _traced_qdrant_operation(self.collection_name, "search", top_k=top_k):
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
        with _traced_qdrant_operation(self.collection_name, "upsert"):
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
        with _traced_qdrant_operation(
            self.collection_name, "upsert", points=len(documents)
        ):
            self._get_client().upsert(
                collection_name=self.collection_name,
                points=points,
            )
        return len(documents)

    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        """Async wrapper over :meth:`store_batch`."""
        return await asyncio.to_thread(self.store_batch, documents)

    # ------------------------------------------------------------------
    # Structural payload refresh (design §7)
    # ------------------------------------------------------------------

    def refresh_structural_payload(
        self,
        source_file: str,
        structure: DocumentStructure | None = None,
    ) -> int:
        """Annotate stored points that predate structural annotation.

        Re-ingesting a document skips embedding/storing for chunks whose
        ``text_hash`` is already stored, so those legacy points keep payload
        without the structural keys. This method scroll-reads exactly the
        target document's points **whose ``node_id`` is empty** — freshly
        stored (already-annotated) points are excluded by the same filter —
        annotates each against *structure*, and upserts the full record
        (payload + vector) back. Per-point payloads forbid
        ``set_payload``-by-filter (design §9 trap 5), hence read-modify-write.

        Args:
            source_file: The document key; MUST equal the payload
                ``source_file`` string (design §9 trap 6).
            structure: The captured tree to annotate against. When None, the
                tree is lazily loaded from the structure store; when no tree
                exists (or the store fails) there is nothing to annotate and
                0 is returned.

        Returns
        -------
            The number of points re-upserted with structural keys. Never
            raises: qdrant failures are warned and reported as the partial
            count so ingest continues.
        """
        if structure is None:
            structure = self._load_structure_tree(source_file)
        if structure is None:
            return 0
        self._ensure_collection()
        # ``is_empty`` is a plain boolean flag on qdrant-client 1.20's
        # ``FieldCondition`` (verified against the pinned client).
        refresh_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_file", match=models.MatchValue(value=source_file)
                ),
                models.FieldCondition(key="node_id", is_empty=True),
            ]
        )
        refreshed = 0
        seen_ids: set[str] = set()
        offset: Any = None
        try:
            while True:
                records, offset = self._get_client().scroll(
                    collection_name=self.collection_name,
                    scroll_filter=refresh_filter,
                    limit=_REFRESH_BATCH_SIZE,
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                )
                if not records:
                    break
                page_ids = {str(record.id) for record in records}
                if page_ids <= seen_ids:
                    # Points with no matching node are skipped (never
                    # upserted) and keep matching the is_empty filter; this
                    # guard stops the cursor from stalling on them forever.
                    break
                seen_ids |= page_ids
                points = self._annotated_refresh_points(records, structure)
                if points:
                    with _traced_qdrant_operation(
                        self.collection_name, "upsert", points=len(points)
                    ):
                        self._get_client().upsert(
                            collection_name=self.collection_name,
                            points=points,
                        )
                    refreshed += len(points)
                if offset is None:
                    break
        except Exception as e:
            logger.warning(
                "Structural payload refresh incomplete for %s (%s: %s)",
                source_file,
                type(e).__name__,
                e,
            )
        return refreshed

    def _annotated_refresh_points(
        self,
        records: Sequence[Any],
        structure: DocumentStructure,
    ) -> list[models.PointStruct]:
        """Build upsert points for the scroll records that got a node.

        Each record is annotated statelessly against the tree (equivalent to
        the reading-order walk because tree ranges are nested: a child's
        range is contained in its parent's). Records for which no node is
        found are dropped — they stay refreshable (bounded re-read waste,
        design §7) instead of being rewritten unchanged.
        """
        from secondbrain.document.structure_annotate import (
            ANNOTATION_PAYLOAD_KEYS,
            annotate_chunks,
        )

        chunks: list[dict[str, Any]] = []
        for record in records:
            payload = dict(record.payload or {})
            chunks.append(
                {
                    "page": payload.get("page_number"),
                    "text": payload.get("chunk_text", ""),
                    **{
                        key: payload[key]
                        for key in ("t_start", "t_end")
                        if key in payload
                    },
                }
            )
        annotated = annotate_chunks(chunks, structure)
        points: list[models.PointStruct] = []
        for record, chunk in zip(records, annotated, strict=True):
            if "node_id" not in chunk:
                continue
            payload = dict(record.payload or {})
            payload.update(
                {key: chunk[key] for key in ANNOTATION_PAYLOAD_KEYS if key in chunk}
            )
            points.append(
                models.PointStruct(
                    id=record.id,
                    vector=record.vector,
                    payload=payload,
                )
            )
        return points

    def _load_structure_tree(self, source_file: str) -> DocumentStructure | None:
        """Lazily load the stored tree for *source_file* (None on any failure)."""
        try:
            from secondbrain.storage.structure_sqlite import StructureStore

            return StructureStore().load_tree(source_file)
        except Exception as e:
            logger.warning(
                "Structure tree unavailable for %s (%s: %s); payload refresh skipped",
                source_file,
                type(e).__name__,
                e,
            )
            return None

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
            with _traced_qdrant_operation(self.collection_name, "facet"):
                resp = self._get_client().facet(
                    collection_name=self.collection_name,
                    key="source_file",
                    limit=MAX_LIST_LIMIT,
                )
            seen: set[str] = set()
            for bucket in resp.hits:
                value = bucket.value
                if isinstance(value, str) and value not in seen:
                    seen.add(value)
            return sorted(seen)
        except AttributeError, TypeError:
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
    # Document-structure scans (replaces legacy ``collection`` reaches)
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
        printed_page: int | str | None = None,
        page_number: int | list[int] | None = None,
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
        if printed_page is not None:
            must_conds.append(
                models.Filter(should=self._key_conditions("printed_page", printed_page))
            )
        if page_number is not None:
            if isinstance(page_number, list):
                must_conds.append(
                    models.Filter(
                        must=[
                            models.FieldCondition(
                                key="page_number",
                                match=models.MatchAny(
                                    any=[int(p) for p in page_number]
                                ),
                            )
                        ]
                    )
                )
            else:
                must_conds.append(
                    models.Filter(
                        should=self._key_conditions("page_number", page_number)
                    )
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

        Ports the legacy ``_probe_document_structure`` OR-filter
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

        Mirrors the legacy ``collection.find({"source_file": src, "chunk_role": "body"},
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

        Mirrors the legacy ``collection.count_documents({"source_file": s,
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
        with _traced_qdrant_operation(
            self.collection_name, "count", role=chunk_role or "all"
        ):
            total = int(
                self._get_client()
                .count(
                    collection_name=self.collection_name,
                    count_filter=scroll_filter,
                    exact=True,
                )
                .count
            )
        return total

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete(self, scroll_filter: models.Filter | None) -> int:
        self._ensure_collection()
        if scroll_filter is None:
            scroll_filter = models.Filter(must=[])
        with _traced_qdrant_operation(self.collection_name, "delete"):
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
        """Stats matching the legacy ``get_stats`` shape for the ``status`` CLI."""
        self._ensure_collection()
        with _traced_qdrant_operation(self.collection_name, "count"):
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

    def validate_connection(
        self, force: bool = False, bypass_circuit_breaker: bool = False
    ) -> bool:
        """TTL-cached reachability probe; returns False on failure, never raises.

        When a circuit breaker is configured, the raw probe runs through it
        (``CircuitBreaker.call``): while the circuit is OPEN the probe is
        skipped entirely and the method degrades gracefully to ``False`` —
        the same signal callers already handle for an unreachable server —
        without any network call. The connection cache is left untouched on
        that path so the probe re-runs as soon as the circuit half-opens.

        With ``bypass_circuit_breaker=True`` (startup-wait probes) the raw
        probe runs directly and the breaker is neither consulted nor updated
        — success or failure — so transient startup failures cannot open the
        circuit while waiting for the server to come up.

        Args:
            force: If True, bypass the connection cache and re-probe.
            bypass_circuit_breaker: Run the probe without consulting or
                updating the circuit breaker.

        Returns
        -------
            True if the Qdrant server answered, False otherwise.
        """
        now = time.monotonic()
        if (
            not force
            and self._conn_valid is not None
            and (now - self._conn_checked_at) < _CONNECTION_TTL
        ):
            return self._conn_valid

        if self._circuit_breaker is not None and not bypass_circuit_breaker:
            try:
                self._conn_valid = self._circuit_breaker.call(self._probe_connection)
            except CircuitBreakerError:
                logger.warning(
                    "Circuit breaker open for %s; skipping Qdrant reachability probe",
                    self.__class__.__name__,
                )
                return False
        else:
            self._conn_valid = self._probe_connection()
        self._conn_checked_at = now
        return self._conn_valid

    def _probe_connection(self) -> bool:
        """One raw Qdrant reachability probe (no caching, no circuit breaker).

        Returns
        -------
            True if the Qdrant server answered ``get_collections()``.
        """
        try:
            with _traced_qdrant_operation(self.collection_name, "ping"):
                self._get_client().get_collections()
        except Exception:
            return False
        return True

    async def validate_connection_async(
        self, force: bool = False, bypass_circuit_breaker: bool = False
    ) -> bool:
        """Async wrapper over :meth:`validate_connection`."""
        return await asyncio.to_thread(
            self.validate_connection, force, bypass_circuit_breaker
        )

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
