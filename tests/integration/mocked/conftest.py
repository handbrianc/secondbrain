"""Pytest fixtures for secondbrain integration tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from qdrant_client import QdrantClient

from secondbrain.embedding.mock import MockEmbeddingGenerator
from secondbrain.storage.qdrant import QdrantVectorStorage

EMBEDDING_DIMENSIONS = 384


@pytest.fixture
def sample_embedding() -> list[float]:
    """Generate a sample embedding vector for testing."""
    import random

    random.seed(42)
    return [random.random() for _ in range(EMBEDDING_DIMENSIONS)]


@pytest.fixture
def qdrant_storage() -> Generator[QdrantVectorStorage]:
    """Local-mode (in-memory) Qdrant-backed storage for mocked integration tests."""
    storage = QdrantVectorStorage(collection_name="test_embeddings")
    storage._client = QdrantClient(":memory:")
    storage._dimensions = EMBEDDING_DIMENSIONS
    yield storage
    storage.close()


@pytest.fixture
def mock_embedder(sample_embedding: list[float]) -> Any:
    """Create a mock embedding generator that returns predictable embeddings."""
    mock_gen = MockEmbeddingGenerator(
        model_name="mock-384", dimension=EMBEDDING_DIMENSIONS
    )

    def mock_generate(self: Any, text: str) -> list[float]:
        return sample_embedding

    # Patch MockEmbeddingGenerator.generate at the class level for duration of test
    original_generate = MockEmbeddingGenerator.generate
    MockEmbeddingGenerator.generate = mock_generate  # type: ignore[method-assign]

    try:
        yield mock_gen
    finally:
        MockEmbeddingGenerator.generate = original_generate  # type: ignore[method-assign]


@pytest.fixture
def stored_chunks(
    qdrant_storage: QdrantVectorStorage, sample_embedding: list[float]
) -> list[str]:
    """Store sample chunks in the Qdrant storage for testing list/search operations."""
    import random
    from uuid import uuid4

    random.seed(123)  # Fixed seed for reproducibility

    chunks = []
    for i in range(5):
        chunk = {
            "chunk_id": str(uuid4()),
            "source_file": f"test_document_{i % 2}.pdf",
            "page_number": i + 1,
            "chunk_text": f"This is chunk {i} with some sample content for testing.",
            "embedding": [random.random() for _ in range(EMBEDDING_DIMENSIONS)],
            "metadata": {
                "file_type": "pdf",
                "ingested_at": "2024-01-01T00:00:00+00:00",
                "chunk_index": i,
            },
        }
        qdrant_storage.store(chunk)
        chunks.append(chunk["chunk_id"])

    return chunks


@pytest.fixture
def ingestor_with_mock_embedder(sample_embedding: list[float]) -> Any:
    """Create a DocumentIngestor with mocked embedding generation."""
    from secondbrain.document import DocumentIngestor

    ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10, verbose=False)

    original_generate = MockEmbeddingGenerator.generate

    def mock_generate(self: Any, text: str) -> list[float]:
        return sample_embedding

    MockEmbeddingGenerator.generate = mock_generate  # type: ignore[method-assign]

    try:
        yield ingestor
    finally:
        MockEmbeddingGenerator.generate = original_generate  # type: ignore[method-assign]
