"""Search module for semantic search functionality.

This module provides the Searcher class for performing semantic searches
against the stored embeddings using vector similarity matching.
"""

import logging
import re
from collections.abc import Sequence
from typing import Any

from secondbrain.config import get_config
from secondbrain.embedding import LocalEmbeddingGenerator
from secondbrain.exceptions import ValidationError
from secondbrain.storage import (
    SearchResult,
    StorageConnectionError,
    VectorStorage,
    build_search_pipeline,
)
from secondbrain.utils.tracing import get_span_name, trace_operation

logger = logging.getLogger(__name__)

__all__ = ["Searcher"]

# Maximum query length to prevent DoS attacks
MAX_QUERY_LENGTH = 10000

# Maximum results limit to prevent resource exhaustion
MAX_TOP_K = 1000

# Pattern to detect potential injection attempts
INJECTION_PATTERNS = [
    r"\.\./",  # Path traversal
    r"<script",  # XSS attempts
    r"javascript:",  # JavaScript protocol
    r"\x00",  # Null bytes
]


def sanitize_query(query: str) -> str:
    """Sanitize search query to prevent injection attacks.

    Args:
        query: Raw search query string.

    Returns
    -------
        Sanitized query string.

    Raises
    ------
        ValueError: If query exceeds maximum length or contains dangerous patterns.
    """
    if not query:
        raise ValueError("Search query cannot be empty")

    if len(query) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Query exceeds maximum length of {MAX_QUERY_LENGTH} characters"
        )

    # Check for injection patterns
    query_lower = query.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            raise ValueError("Query contains invalid characters or patterns")

    # Strip whitespace, remove control characters, then strip again
    # (control char removal may leave trailing spaces)
    sanitized = query.strip()
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sanitized)
    sanitized = sanitized.strip()

    return sanitized


class Searcher:
    """Performs semantic search against stored embeddings.

    Uses sentence-transformers to generate query embeddings and MongoDB for
    vector similarity search against the stored document embeddings.
    """

    def __init__(self, verbose: bool = False) -> None:
        """Initialize searcher.

        Args:
            verbose: Enable verbose logging.
        """
        self.verbose = verbose
        self.config = get_config()
        self.embedding_gen = LocalEmbeddingGenerator()
        self.storage = VectorStorage()

    def close(self) -> None:
        """Close resources and release connections."""
        self.embedding_gen.close()
        self.storage.close()

    async def aclose(self) -> None:
        """Close async resources for embedding generator and storage.

        Asynchronously closes the embedding generator and storage resources,
        checking for async support before calling.
        """
        # Dynamic check for async support - these methods may not exist on all versions
        if hasattr(self.embedding_gen, "aclose"):
            await self.embedding_gen.aclose()  # pyright: ignore[reportAttributeAccessIssue]
        if hasattr(self.storage, "aclose"):
            await self.storage.aclose()  # pyright: ignore[reportAttributeAccessIssue]

    def __enter__(self) -> "Searcher":
        """Enter runtime context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit runtime context manager."""
        self.close()

    async def __aenter__(self) -> "Searcher":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit - closes async resources."""
        await self.aclose()

    def search(
        self,
        query: str,
        top_k: int | None = None,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents using semantic similarity.

        Args:
            query: Search query string.
            top_k: Number of results to return (max: 1000).
            source_filter: Filter by source file.
            file_type_filter: Filter by file type.

        Returns:
            List of search results as dictionaries.

        Raises:
            ValueError: If top_k exceeds maximum limit.
        """
        # Sanitize query to prevent injection attacks
        sanitized_query = sanitize_query(query)

        top_k = top_k or self.config.default_top_k

        # Enforce maximum results limit
        if top_k > MAX_TOP_K:
            raise ValidationError(
                f"top_k ({top_k}) exceeds maximum limit of {MAX_TOP_K}"
            )

        # Validate connections
        if not self.storage.validate_connection():
            raise RuntimeError("Cannot connect to MongoDB")

        # Generate query embedding
        with trace_operation("search_generate_embedding"):
            query_embedding = self.embedding_gen.generate(sanitized_query)

        # Search in storage
        with trace_operation("search_storage"):
            raw_results: Sequence[SearchResult] = self.storage.search(
                embedding=query_embedding,
                top_k=top_k,
                source_filter=source_filter,
                file_type_filter=file_type_filter,
            )

        # Convert SearchResult to dict[str, Any] for CLI compatibility
        results: list[dict[str, Any]] = [dict(r) for r in raw_results]
        return results
