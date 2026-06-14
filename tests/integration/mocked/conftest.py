"""Pytest fixtures for secondbrain integration tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from pymongo import MongoClient

from secondbrain.storage import VectorStorage

if TYPE_CHECKING:
    pass  # type: ignore[unused-ignore]

EMBEDDING_DIMENSIONS = 768


@pytest.fixture
def mock_mongo_client() -> Generator[MongoClient[Any], None, None]:
    """Provide mock MongoDB client for integration tests."""
    import mongomock  # type: ignore[unused-ignore]

    client = mongomock.MongoClient()
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def test_db(mock_mongo_client: MongoClient[Any]) -> Any:
    """Get test database from mocked MongoDB client."""
    return mock_mongo_client["test_secondbrain"]


@pytest.fixture
def test_collection(test_db: Any) -> Any:
    """Get test embeddings collection."""
    return test_db["test_embeddings"]


@pytest.fixture
def sample_embedding() -> list[float]:
    """Generate a sample embedding vector for testing."""
    import random

    random.seed(42)
    return [random.random() for _ in range(EMBEDDING_DIMENSIONS)]


class MockEmbeddingGenerator:
    """Mock embedding generator that returns predictable embeddings."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIMENSIONS) -> None:
        self._embedding_dim = embedding_dim

    def generate(self, text: str) -> list[float]:
        text_hash = hash(text.strip().lower())
        import random

        random.seed(text_hash)
        return [random.random() for _ in range(self._embedding_dim)]

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.generate(text) for text in texts]

    def validate_connection(self) -> bool:
        return True

    def close(self) -> None:
        pass

    async def aclose(self) -> None:
        pass


@pytest.fixture
def mock_embedder(sample_embedding: list[float]) -> Any:
    """Create a mock embedding generator that returns predictable embeddings."""
    return MockEmbeddingGenerator()


@pytest.fixture
def stored_chunks(test_collection: Any, sample_embedding: list[float]) -> list[str]:
    """Store sample chunks in the test collection for testing list/search operations."""
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
        test_collection.insert_one(chunk)
        chunks.append(chunk["chunk_id"])

    return chunks


@pytest.fixture
def ingestor_with_mock_embedder(sample_embedding: list[float]) -> Any:
    """Create a DocumentIngestor with mocked embedding generation."""
    from secondbrain.document import DocumentIngestor

    ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10, verbose=False)
    return ingestor


@pytest.fixture
def storage_with_index(test_collection: Any) -> Any:
    """Create a VectorStorage instance for integration testing."""
    from secondbrain.config import get_config

    original_mongo_uri = os.environ.get("SECONDBRAIN_MONGO_URI")
    original_mongo_db = os.environ.get("SECONDBRAIN_MONGO_DB")
    original_mongo_collection = os.environ.get("SECONDBRAIN_MONGO_COLLECTION")
    original_embedding_model = os.environ.get("SECONDBRAIN_LOCAL_EMBEDDING_MODEL")

    test_mongo_uri = os.environ.get(
        "SECONDBRAIN_MONGO_URI",
        "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin",
    )
    test_mongo_db = os.environ.get("SECONDBRAIN_MONGO_DB", "secondbrain_test")

    os.environ["SECONDBRAIN_MONGO_URI"] = test_mongo_uri
    os.environ["SECONDBRAIN_MONGO_DB"] = test_mongo_db
    os.environ["SECONDBRAIN_MONGO_COLLECTION"] = "test_embeddings"
    os.environ["SECONDBRAIN_LOCAL_EMBEDDING_MODEL"] = "all-MiniLM-L6-v2"

    get_config.cache_clear()

    storage = VectorStorage(
        mongo_uri=test_mongo_uri,
        db_name=test_mongo_db,
        collection_name="test_embeddings",
    )

    test_collection.create_index("source_file")

    try:
        yield storage
    finally:
        storage._client = None
        storage._db = None
        storage._collection = None
        # Restore original environment variables
        if original_mongo_uri is not None:
            os.environ["SECONDBRAIN_MONGO_URI"] = original_mongo_uri
        elif "SECONDBRAIN_MONGO_URI" in os.environ:
            del os.environ["SECONDBRAIN_MONGO_URI"]

        if original_mongo_db is not None:
            os.environ["SECONDBRAIN_MONGO_DB"] = original_mongo_db
        elif "SECONDBRAIN_MONGO_DB" in os.environ:
            del os.environ["SECONDBRAIN_MONGO_DB"]

        if original_mongo_collection is not None:
            os.environ["SECONDBRAIN_MONGO_COLLECTION"] = original_mongo_collection
        elif "SECONDBRAIN_MONGO_COLLECTION" in os.environ:
            del os.environ["SECONDBRAIN_MONGO_COLLECTION"]

        if original_embedding_model is not None:
            os.environ["SECONDBRAIN_LOCAL_EMBEDDING_MODEL"] = original_embedding_model
        elif "SECONDBRAIN_LOCAL_EMBEDDING_MODEL" in os.environ:
            del os.environ["SECONDBRAIN_LOCAL_EMBEDDING_MODEL"]

        # Clear and re-cache config to pick up restored env vars
        get_config.cache_clear()


@pytest.fixture
def search_workflow(storage_with_index: Any, sample_embedding: list[float]) -> Any:
    """Create a Searcher-like workflow for testing search operations."""
    from secondbrain.search import Searcher

    storage_with_index.ensure_index()

    mock_embed = MockEmbeddingGenerator()

    return {
        "searcher": Searcher(verbose=False),
        "storage": storage_with_index,
        "embedding_gen": mock_embed,
    }