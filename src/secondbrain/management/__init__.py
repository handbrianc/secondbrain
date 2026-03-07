"""Management module for document operations.

This module provides classes for listing, deleting, and checking status
of documents stored in the vector database.
"""

from typing import Any

from secondbrain.storage import ChunkInfo, DatabaseStats, VectorStorage
from secondbrain.utils.connections import ensure_service_available

__all__ = [
    "BaseManager",
    "Deleter",
    "Lister",
    "StatusChecker",
]


class BaseManager:
    """Base class for management operations with MongoDB availability validation.

    This class provides a shared implementation of the service validation
    pattern used across all management operations (list, delete, status).
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize the base manager.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose: bool = verbose
        self.storage: VectorStorage = VectorStorage()

    def _ensure_storage_available(self) -> None:
        """Ensure MongoDB is available, raise if not.

        Raises:
            ServiceUnavailableError: If MongoDB connection cannot be established.
        """
        ensure_service_available("MongoDB", self.storage.validate_connection)

    def __enter__(self) -> "BaseManager":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
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
    ) -> list[ChunkInfo]:
        """List chunks with optional filters.

        Args:
            source_filter: Filter by source file.
            chunk_id: Filter by specific chunk ID.
            limit: Maximum number of results.
            offset: Pagination offset.

        Returns:
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
    ) -> int:
        """Delete documents from storage.

        Args:
            source: Delete by source file.
            chunk_id: Delete by specific chunk ID.
            all: Delete all documents.

        Returns:
            Number of deleted documents.
        """
        if all:
            return self.storage.delete_all()

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            return self.storage.delete_by_source(source)

        return 0


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

        Returns:
            Dictionary of database statistics.
        """
        return self.storage.get_stats()
