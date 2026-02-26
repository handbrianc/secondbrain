"""Management module for list, delete, and status operations."""

import logging
from typing import Any

from secondbrain.storage import StorageConnectionError, VectorStorage

logger = logging.getLogger(__name__)


class Lister:
    """Handles listing of documents."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize lister.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.storage = VectorStorage()

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List chunks with filters.

        Args:
            source_filter: Filter by source file
            chunk_id: Filter by chunk ID
            limit: Max results
            offset: Pagination offset

        Returns:
            list: List of chunks
        """
        if not self.storage.validate_connection():
            raise RuntimeError("Cannot connect to MongoDB")

        return self.storage.list_chunks(
            source_filter=source_filter,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )


class Deleter:
    """Handles deletion of documents."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize deleter.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.storage = VectorStorage()

    def delete(
        self,
        source: str | None = None,
        chunk_id: str | None = None,
        all: bool = False,
    ) -> int:
        """Delete documents.

        Args:
            source: Source file to delete
            chunk_id: Specific chunk ID to delete
            all: Delete all

        Returns:
            int: Number of deleted documents
        """
        if not self.storage.validate_connection():
            raise RuntimeError("Cannot connect to MongoDB")

        if all:
            return self.storage.delete_all()

        if chunk_id:
            return self.storage.delete_by_chunk_id(chunk_id)

        if source:
            return self.storage.delete_by_source(source)

        return 0


class StatusChecker:
    """Handles status checking."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize status checker.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.storage = VectorStorage()

    def get_status(self) -> dict[str, Any]:
        """Get database status.

        Returns:
            dict: Status information
        """
        if not self.storage.validate_connection():
            raise RuntimeError("Cannot connect to MongoDB")

        return self.storage.get_stats()
