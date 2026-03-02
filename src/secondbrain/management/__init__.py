from typing import Any

from secondbrain.storage import ChunkInfo, StorageConnectionError, VectorStorage
from secondbrain.utils.connections import ServiceUnavailableError


class Lister:
    """Handles listing of ingested documents and chunks."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize lister.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose = verbose
        self.storage = VectorStorage()

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
        self._ensure_storage_available()

        return self.storage.list_chunks(
            source_filter=source_filter,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )

    def _ensure_storage_available(self) -> None:
        """Ensure MongoDB is available, raise if not."""
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)


class Deleter:
    """Handles deletion of documents from storage."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize deleter.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose = verbose
        self.storage = VectorStorage()

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
        self._ensure_storage_available()

        if all:
            return self.storage.delete_all()

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            return self.storage.delete_by_source(source)

        return 0

    def _ensure_storage_available(self) -> None:
        """Ensure MongoDB is available, raise if not."""
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)


class StatusChecker:
    """Handles status reporting for the storage."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize status checker.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose = verbose
        self.storage = VectorStorage()

    def get_status(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary of database statistics.
        """
        self._ensure_storage_available()

        return self.storage.get_stats()

    def _ensure_storage_available(self) -> None:
        """Ensure MongoDB is available, raise if not."""
        from secondbrain.utils.connections import ensure_service_available

        ensure_service_available("MongoDB", self.storage.validate_connection)
