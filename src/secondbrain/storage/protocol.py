"""Vector storage protocol — the backend-agnostic public surface.

``Searcher``, the ingestors, ``Lister``/``Deleter``, the ``status`` command and
the RAG pipeline depend only on this interface. Both the Qdrant backend and the
in-memory fake implement it, so a backend swap never reaches a consumer.

The document structure (for structure-based summarization) is queried via the
two chunk-scan methods ``get_source_chunks`` and ``find_chunks`` rather than a
Mongo ``collection`` handle.
"""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from secondbrain.types import ChunkInfo, SearchResult


@runtime_checkable
class VectorStorageProtocol(Protocol):
    """Public API for any vector/metadata storage backend.

    Implementations: :class:`~secondbrain.storage.qdrant.QdrantVectorStorage`
    (production) and the in-memory mock (fast tests).
    """

    def search(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Search for similar chunks, optionally filtered by payload fields."""
        ...

    async def search_async(
        self,
        embedding: list[float],
        top_k: int = 5,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> Sequence[SearchResult]:
        """Async variant of :meth:`search`."""
        ...

    def store(self, document: dict[str, Any]) -> str:
        """Upsert a single chunk; return its id."""
        ...

    def store_batch(self, documents: list[dict[str, Any]]) -> int:
        """Upsert a batch of chunks; return the number of documents."""
        ...

    async def store_batch_async(self, documents: list[dict[str, Any]]) -> int:
        """Async variant of :meth:`store_batch`."""
        ...

    def list_chunks(
        self,
        source_filter: str | None = None,
        chunk_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        use_prefix_match: bool = True,
    ) -> Sequence[ChunkInfo]:
        """List chunks with optional filters and offset/limit pagination."""
        ...

    def list_source_files(self) -> list[str]:
        """Return every distinct source file path in the store."""
        ...

    def has_existing_hashes(self, hashes: list[str]) -> set[str]:
        """Return the subset of ``hashes`` already present in the store."""
        ...

    def get_source_chunks(
        self,
        source_file: str,
        *,
        limit: int | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Return a source's chunks ordered by page number."""
        ...

    def find_chunks(
        self,
        source_file: str | None = None,
        *,
        chapter_id: str | None = None,
        section_id: str | None = None,
        section_id_pattern: str | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Return chunks matching metadata filters (optional section regex)."""
        ...

    def find_structural_chunks(
        self,
        element_types: list[str] | None = None,
        chunk_roles: list[str] | None = None,
        source_prefix: str | None = None,
        limit: int | None = None,
    ) -> Sequence[ChunkInfo]:
        """Return structural chunks (element_type OR chunk_role) ordered by page.

        Matches chunks whose ``element_type`` is in *element_types* OR whose
        ``chunk_role`` is in *chunk_roles*; when both are empty every chunk
        matches (all-chunks fallback). Optionally scopes to ``source_file``
        values starting with *source_prefix*, ordered by ascending
        ``page_number`` and truncated to *limit*.
        """
        ...

    def get_body_chunks(
        self,
        source_file: str,
        *,
        limit: int | None = None,
        page_gte: int | None = None,
        with_text: bool = True,
    ) -> Sequence[ChunkInfo]:
        """Return a source's body chunks ordered by page, optionally page/limit."""
        ...

    def count_chunks(
        self,
        source_file: str | None = None,
        chunk_role: str | None = None,
    ) -> int:
        """Count chunks matching optional source_file / chunk_role filters."""
        ...

    def delete_by_source(self, source: str) -> int:
        """Delete all chunks from a source file; return the count."""
        ...

    def delete_by_chunk_id(self, chunk_id: str) -> int:
        """Delete a specific chunk; return the count (0 or 1)."""
        ...

    def delete_all(self) -> int:
        """Delete all chunks; return the count."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Return storage statistics (total chunks, unique sources)."""
        ...

    def validate_connection(self, force: bool = False) -> bool:
        """Return True if the backend is reachable; never raises."""
        ...

    def close(self) -> None:
        """Release backend resources."""
        ...

    def __enter__(self) -> Any:
        """Enter a context manager; return self."""
        ...

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit a context manager and close the backend."""
        ...
