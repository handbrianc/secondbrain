"""Mock VectorStorage for testing without MongoDB.

This provides an in-memory implementation of VectorStorage that mimics
the behavior of the real MongoDB-based storage for testing purposes.
"""

from __future__ import annotations

import math
from typing import Any



class MockVectorStorage:
    """In-memory mock vector storage for testing.

    Provides a MongoDB-like interface without requiring actual database connections.
    Uses cosine similarity for semantic search simulation.
    """

    def __init__(self) -> None:
        """Initialize mock storage with empty chunk store."""
        self._chunks: dict[str, dict[str, Any]] = {}
        self._chunk_ids: list[str] = []
        self._initialized = False

    def _calculate_cosine_similarity(
        self, vec1: list[float], vec2: list[float]
    ) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            vec1: First vector.
            vec2: Second vector.

        Returns:
            Cosine similarity score (range: -1 to 1).
        """
        if not vec1 or not vec2:
            return 0.0

        # Ensure same length
        min_len = min(len(vec1), len(vec2))
        vec1 = vec1[:min_len]
        vec2 = vec2[:min_len]

        # Calculate dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Calculate magnitudes
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))

        # Avoid division by zero
        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def initialize(self) -> None:
        """Initialize the mock storage (no-op, but provides interface compatibility)."""
        self._initialized = True

    def ensure_index(self) -> None:
        """Ensure vector search index exists (no-op for mock)."""
        pass

    def store(self, chunk: dict[str, Any]) -> None:
        """Store a single chunk.

        Args:
            chunk: Chunk dictionary with chunk_id, chunk_text, embedding, etc.
        """
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            raise ValueError("Chunk must have a chunk_id")

        # Store chunk
        self._chunks[chunk_id] = chunk
        if chunk_id not in self._chunk_ids:
            self._chunk_ids.append(chunk_id)

    def store_batch(self, chunks: list[dict[str, Any]]) -> None:
        """Store multiple chunks.

        Args:
            chunks: List of chunk dictionaries.
        """
        for chunk in chunks:
            self.store(chunk)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        threshold: float = 0.0,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks.

        Args:
            query_embedding: Query embedding vector.
            top_k: Maximum number of results to return.
            threshold: Minimum similarity threshold.
            **kwargs: Additional parameters (ignored for mock).

        Returns:
            List of matching chunks with similarity scores.
        """
        if not query_embedding or not self._chunks:
            return []

        scored_chunks = []
        for chunk_id, chunk in self._chunks.items():
            chunk_embedding = chunk.get("embedding", [])
            if not chunk_embedding:
                continue

            similarity = self._calculate_cosine_similarity(
                query_embedding, chunk_embedding
            )

            if similarity >= threshold:
                result = chunk.copy()
                result["similarity"] = similarity
                result["score"] = similarity
                scored_chunks.append(result)

        # Sort by similarity descending
        scored_chunks.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        return scored_chunks[:top_k]

    def search_by_text(
        self,
        query_text: str,
        embed_gen: Any | None = None,
        top_k: int = 5,
        threshold: float = 0.0,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks using text query.

        Args:
            query_text: Query text string.
            embed_gen: Embedding generator (required for text search).
            top_k: Maximum number of results to return.
            threshold: Minimum similarity threshold.
            **kwargs: Additional parameters.

        Returns:
            List of matching chunks with similarity scores.
        """
        if not embed_gen:
            # Return empty results if no embedding generator
            return []

        # Generate query embedding
        query_embedding = embed_gen.generate(query_text)

        return self.search(query_embedding, top_k=top_k, threshold=threshold, **kwargs)

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get a chunk by ID.

        Args:
            chunk_id: Chunk identifier.

        Returns:
            Chunk dictionary or None if not found.
        """
        return self._chunks.get(chunk_id)

    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk by ID.

        Args:
            chunk_id: Chunk identifier.

        Returns:
            True if deleted, False if not found.
        """
        if chunk_id in self._chunks:
            del self._chunks[chunk_id]
            if chunk_id in self._chunk_ids:
                self._chunk_ids.remove(chunk_id)
            return True
        return False

    def delete_by_prefix(self, prefix: str) -> int:
        """Delete chunks with IDs starting with prefix.

        Args:
            prefix: ID prefix to match.

        Returns:
            Number of chunks deleted.
        """
        to_delete = [cid for cid in self._chunk_ids if cid.startswith(prefix)]
        for cid in to_delete:
            self.delete(cid)
        return len(to_delete)

    def delete_all(self) -> int:
        """Delete all chunks.

        Returns:
            Number of chunks deleted.
        """
        count = len(self._chunks)
        self._chunks.clear()
        self._chunk_ids.clear()
        return count

    def count(self) -> int:
        """Get total chunk count.

        Returns:
            Number of chunks in storage.
        """
        return len(self._chunks)

    def get_all_chunks(self) -> list[dict[str, Any]]:
        """Get all chunks.

        Returns:
            List of all chunk dictionaries.
        """
        return list(self._chunks.values())

    def get_chunk_ids(self) -> list[str]:
        """Get all chunk IDs.

        Returns:
            List of chunk IDs.
        """
        return self._chunk_ids.copy()

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics.

        Returns:
            Dictionary with storage statistics.
        """
        return {
            "total_chunks": len(self._chunks),
            "total_ids": len(self._chunk_ids),
            "initialized": self._initialized,
        }

    def validate_connection(self) -> bool:
        """Validate storage connection (always True for mock).

        Returns:
            True (mock storage is always available).
        """
        return True

    async def validate_connection_async(self) -> bool:
        """Async validation (always True for mock).

        Returns:
            True (mock storage is always available).
        """
        return True

    def close(self) -> None:
        """Close storage (no-op for mock)."""
        pass

    async def aclose(self) -> None:
        """Async close (no-op for mock)."""
        pass

    def __enter__(self) -> MockVectorStorage:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def __len__(self) -> int:
        """Get chunk count."""
        return len(self._chunks)

    def __contains__(self, chunk_id: str) -> bool:
        """Check if chunk exists."""
        return chunk_id in self._chunks
