"""Management module for document operations.

This module provides classes for listing, deleting, and checking status
of documents stored in the vector database.
"""

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

from secondbrain.document.ingestor._constants import get_file_type
from secondbrain.storage import ChunkInfo, DatabaseStats, StorageFactory
from secondbrain.utils.connections import ensure_service_available

if TYPE_CHECKING:
    from secondbrain.storage.structure_sqlite import StructureStore

__all__ = [
    "BaseManager",
    "Deleter",
    "Lister",
    "StatusChecker",
]

logger = logging.getLogger(__name__)


class BaseManager:
    """Base class for management operations with storage availability validation.

    This class provides a shared implementation of the service validation
    pattern used across all management operations (list, delete, status).
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize the base manager.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose: bool = verbose
        self.storage = StorageFactory.create_from_config()

    def _ensure_storage_available(self) -> None:
        """Ensure vector storage is available, raise if not.

        Raises
        ------
            ServiceUnavailableError: If storage connection cannot be established.
        """
        ensure_service_available("vector storage", self.storage.validate_connection)

    def __enter__(self) -> Self:
        """Enter runtime context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit runtime context manager."""
        self.storage.close()

    def close(self) -> None:
        """Close storage connection."""
        self.storage.close()


class Lister(BaseManager):
    """Handles listing of ingested documents and chunks."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize lister.

        Args:
            verbose: Enable verbose logging.
        """
        super().__init__(verbose=verbose)

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[ChunkInfo]:
        """List chunks with optional filters.

        Args:
            source_filter: Filter by source file.
            chunk_id: Filter by specific chunk ID.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns
        -------
            List of chunk information.
        """
        return self.storage.list_chunks(
            source_filter=source_filter,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )


class Deleter(BaseManager):
    """Handles deletion of documents from storage.

    Besides the vector-store points, document-level deletes also remove the
    per-document structure tree persisted by structure-aware ingestion
    (``add-structure-aware-ingestion`` §6.5). A broken structure store never
    fails a delete — it degrades to a logged warning.
    """

    def __init__(
        self,
        verbose: bool = False,
        structure_store: StructureStore | None = None,
    ) -> None:
        """Initialize deleter.

        Args:
            verbose: Enable verbose logging.
            structure_store: Optional pre-built structure store (tests /
                advanced callers). When ``None``, the store is lazily built
                from the configured SQLite path on first tree cleanup.
        """
        super().__init__(verbose=verbose)
        # Lazily built against the shared conversation SQLite file (same
        # pattern as the ingestor's structure-store wiring): construction
        # stays cheap and a broken store is marked for the deleter's
        # lifetime so it can never fail a delete.
        self._structure_store = structure_store
        self._structure_store_broken = False

    def _get_structure_store(self) -> StructureStore | None:
        """Return the lazily-built structure store, or None when unavailable.

        Returns
        -------
            The cached :class:`StructureStore`, or None when construction
            keeps failing (a warning is logged once and deletes proceed
            without tree cleanup).
        """
        if self._structure_store_broken:
            return None
        if self._structure_store is None:
            from secondbrain.storage.structure_sqlite import StructureStore

            try:
                self._structure_store = StructureStore()
            except Exception as e:
                self._structure_store_broken = True
                logger.warning(
                    "Structure store unavailable (%s: %s); stored structure "
                    "trees will not be deleted",
                    type(e).__name__,
                    e,
                )
                return None
        return self._structure_store

    def _delete_structure_trees(self, sources: Sequence[str]) -> None:
        """Delete the stored structure trees for *sources* (never raises).

        Args:
            sources: The document keys whose trees should be removed.
        """
        if not sources:
            return
        store = self._get_structure_store()
        if store is None:
            return
        for source in sources:
            try:
                store.delete_structure(source)
            except Exception as e:
                logger.warning(
                    "Failed to delete stored structure tree for %s: %s: %s",
                    source,
                    type(e).__name__,
                    e,
                )

    def _collect_source_files(self) -> list[str]:
        """Enumerate the stored source_file keys (best-effort, never raises).

        Used by the bulk ``--all`` delete to snapshot the affected keys
        BEFORE the points are deleted (afterwards the listing is empty).

        Returns
        -------
            The distinct source keys, or an empty list when enumeration
            fails (a warning is logged and tree cleanup is skipped).
        """
        try:
            return list(self.storage.list_source_files())
        except Exception as e:
            logger.warning(
                "Could not enumerate source files for structure-tree cleanup: %s: %s",
                type(e).__name__,
                e,
            )
            return []

    def delete(
        self,
        source: str | None = None,
        chunk_id: str | None = None,
        all: bool = False,
        file_type: str | None = None,
    ) -> int:
        """Delete documents from storage.

        Document-level deletes (``--source``, ``--all``, ``--file-type``)
        also remove the stored structure trees of the affected source files;
        deleting a single chunk leaves the document (and its tree) intact.

        Args:
            source: Delete by source file.
            chunk_id: Delete by specific chunk ID.
            all: Delete all documents.
            file_type: Delete every chunk whose source file type matches the
                stored ``file_type`` category (e.g. ``'pdf'``, ``'markdown'``).

        Returns
        -------
            Number of deleted documents.
        """
        if all:
            # Snapshot the affected keys first: after delete_all() the
            # listing no longer shows them.
            sources = self._collect_source_files()
            count = self.storage.delete_all()
            self._delete_structure_trees(sources)
            return count

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            count = self.storage.delete_by_source(source)
            if count:
                self._delete_structure_trees([source])
            return count

        if file_type:
            return self._delete_by_file_type(file_type)

        return 0

    def _delete_by_file_type(self, file_type: str) -> int:
        """Delete all chunks whose source file resolves to *file_type*.

        The storage protocol exposes no file-type-filtered delete, so the
        distinct source files are enumerated via ``list_source_files()`` and
        each matching source is deleted with ``delete_by_source()``. This
        mirrors how the ``file_type`` payload is written at ingest time
        (the category is derived from the source path's extension), so
        resolving the category per source matches the stored values exactly.
        Sources whose points were actually deleted also have their stored
        structure trees removed.
        """
        deleted = 0
        deleted_sources: list[str] = []
        for source in self.storage.list_source_files():
            if get_file_type(Path(source)) == file_type:
                removed = self.storage.delete_by_source(source)
                if removed:
                    deleted += removed
                    deleted_sources.append(source)
        self._delete_structure_trees(deleted_sources)
        return deleted


class StatusChecker(BaseManager):
    """Handles status reporting for the storage."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize status checker.

        Args:
            verbose: Enable verbose logging.
        """
        super().__init__(verbose=verbose)

    def get_status(self) -> DatabaseStats:
        """Get database statistics.

        Returns
        -------
            Dictionary of database statistics.
        """
        return cast(DatabaseStats, self.storage.get_stats())

    def connection_status(self) -> str:
        """Return the vector storage connectivity as ``'reachable'``/``'unreachable'``.

        Uses the protocol's ``validate_connection`` probe, which never raises,
        so the ``status`` command stays printable when the backend is offline.
        """
        try:
            connected = bool(self.storage.validate_connection())
        except Exception:
            # Defensive: the protocol promises validate_connection never
            # raises, but a misbehaving backend must not break `status`.
            connected = False
        return "reachable" if connected else "unreachable"

    def estimate_storage_size(self, total_chunks: int) -> int:
        """Approximate the stored data footprint from the chunk count.

        The storage protocol exposes no byte-size readout, so the ``status``
        command estimates the dominant per-chunk terms: one float32 embedding
        vector plus the raw chunk text (the configured chunk size in chars,
        approximating one byte per character). It is intentionally labeled
        approximate in the output.
        """
        from secondbrain.config import config

        cfg = config()
        vector_bytes = total_chunks * cfg.embedding_dimensions * 4
        text_bytes = total_chunks * cfg.chunk_size
        return vector_bytes + text_bytes
