"""Management module for document operations.

This module provides classes for listing, deleting, and checking status
of documents stored in the vector database.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self, cast

from secondbrain.document.ingestor._constants import get_file_type
from secondbrain.storage import ChunkInfo, DatabaseStats, StorageFactory
from secondbrain.utils.connections import ensure_service_available

__all__ = [
    "BaseManager",
    "Deleter",
    "Lister",
    "StatusChecker",
]


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
    """Handles deletion of documents from storage."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize deleter.

        Args:
            verbose: Enable verbose logging.
        """
        super().__init__(verbose=verbose)

    def delete(
        self,
        source: str | None = None,
        chunk_id: str | None = None,
        all: bool = False,
        file_type: str | None = None,
    ) -> int:
        """Delete documents from storage.

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
            return self.storage.delete_all()

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            return self.storage.delete_by_source(source)

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
        """
        deleted = 0
        for source in self.storage.list_source_files():
            if get_file_type(Path(source)) == file_type:
                deleted += self.storage.delete_by_source(source)
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
