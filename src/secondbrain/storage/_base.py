"""Shared base class for vector storage implementations."""

import math
import struct
from abc import ABC
from typing import Any

from bson.binary import Binary


class BaseVectorStorage(ABC):  # noqa: B024
    """Abstract base for vector storage implementations.

    Contains shared private methods for encoding/decoding embeddings,
    preparing documents, and batch timestamp insertion. These methods
    are pure transformation logic independent of sync vs async MongoDB client.

    Subclasses must provide ``self._config``: Config instance.
    """

    __slots__ = ()

    def _encode_embedding(self, embedding: list[float]) -> bytes:
        """Convert float list to binary float32 array.

        Args:
            embedding: List of floats (float64 or float32).

        Returns:
            Binary data packed as float32 array.
        """
        return struct.pack(f"{len(embedding)}f", *embedding)

    def _decode_embedding(
        self, binary: bytes, dimensions: int | None = None
    ) -> list[float]:
        """Convert binary float32 array back to float list.

        Args:
            binary: Binary data from float32 array.
            dimensions: Expected dimensions (auto-detected if None).

        Returns:
            List of floats decoded from binary.
        """
        if dimensions is None:
            dimensions = len(binary) // 4  # 4 bytes per float32
        return list(struct.unpack(f"{dimensions}f", binary))

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
        if self._config.embedding_storage_format == "binary":  # type: ignore[assignment]
            return Binary(self._encode_embedding(embedding))
        return embedding

    def _normalize_embedding(self, embedding: bytes | list[float]) -> list[float]:
        """Normalize embedding to list format for use.

        Args:
            embedding: Binary data or list of floats.

        Returns:
            List of floats.
        """
        if isinstance(embedding, Binary):
            return self._decode_embedding(bytes(embedding))
        if isinstance(embedding, bytes):
            return self._decode_embedding(embedding)
        return embedding

    def _add_ingestion_timestamps(
        self, documents: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add ingestion timestamps to multiple documents.

        Supports both old (nested metadata) and new (flattened) formats.
        All documents in batch get the same timestamp for consistency.

        Args:
            documents: List of documents to add timestamps to.

        Returns:
            List of documents with updated timestamps.
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

    def _prepare_document_for_storage(self, doc: dict[str, Any]) -> dict[str, Any]:
        """Prepare document for storage with optimizations.

        Computes and injects the magnitude field for O(1) retrieval
        during search instead of O(d) recomputation.

        Args:
            doc: Document to prepare.

        Returns:
            Document with optimized embedding format and pre-computed magnitude.
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
