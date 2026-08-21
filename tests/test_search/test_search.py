"""Tests for the storage search API against a local-mode Qdrant backend."""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage

DIM = 4


@pytest.fixture
def storage() -> QdrantVectorStorage:
    """A QdrantVectorStorage backed by a local-mode (in-memory) Qdrant."""
    instance = QdrantVectorStorage(collection_name="test_search_coll")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def _doc(chunk_id: str, source: str, text: str) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "source_file": source,
        "page_number": 1,
        "chunk_text": text,
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }


@pytest.mark.unit
class TestVectorStorage:
    """Tests for the storage search API."""

    def test_search_basic(self, storage: QdrantVectorStorage) -> None:
        """Test basic search functionality returns ranked results."""
        storage.store_batch(
            [
                _doc("1", "test.pdf", "sample text"),
                _doc("2", "test.pdf", "more text"),
            ]
        )

        results = list(storage.search([0.1, 0.2, 0.3, 0.4], top_k=5))

        assert len(results) == 2
        assert {r["chunk_id"] for r in results} == {"1", "2"}
        assert all(r["chunk_text"] in {"sample text", "more text"} for r in results)

    def test_search_with_source_filter(
        self, storage: QdrantVectorStorage,
    ) -> None:
        """Test search with a source filter returns only matching source."""
        storage.store_batch(
            [
                _doc("1", "test.pdf", "sample text"),
                _doc("2", "other.pdf", "other chunk"),
            ]
        )

        results = list(storage.search([0.1, 0.2, 0.3, 0.4], source_filter="test.pdf"))

        assert len(results) == 1
        assert results[0]["source_file"] == "test.pdf"
