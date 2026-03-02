"""Search module for semantic search."""

import logging
from collections.abc import Sequence
from typing import Any

from secondbrain.config import get_config
from secondbrain.embedding import EmbeddingGenerator
from secondbrain.storage import SearchResult, StorageConnectionError, VectorStorage

logger = logging.getLogger(__name__)


class Searcher:
    """Handles semantic search."""

    def __init__(self, verbose: bool = False) -> None:
        """Initialize searcher.

        Args:
            verbose: Enable verbose logging
        """
        self.verbose = verbose
        self.config = get_config()
        self.embedding_gen = EmbeddingGenerator()
        self.storage = VectorStorage()

    def search(
        self,
        query: str,
        top_k: int | None = None,
        source_filter: str | None = None,
        file_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar documents.

        Args:
            query: Search query text
            top_k: Number of results
            source_filter: Filter by source file
            file_type_filter: Filter by file type

        Returns:
            list: Search results with scores
        """
        top_k = top_k or self.config.default_top_k

        # Validate connections
        if not self.embedding_gen.validate_connection():
            raise RuntimeError("Cannot connect to Ollama service")

        if not self.storage.validate_connection():
            raise RuntimeError("Cannot connect to MongoDB")

        # Generate query embedding
        query_embedding = self.embedding_gen.generate(query)

        # Search in storage
        raw_results: Sequence[SearchResult] = self.storage.search(
            embedding=query_embedding,
            top_k=top_k,
            source_filter=source_filter,
            file_type_filter=file_type_filter,
        )

        # Convert SearchResult to dict[str, Any] for CLI compatibility
        results: list[dict[str, Any]] = [dict(r) for r in raw_results]
        return results
