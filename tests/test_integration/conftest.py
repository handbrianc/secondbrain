"""Pytest fixtures for secondbrain integration tests."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pymongo import MongoClient

from secondbrain.embedding import LocalEmbeddingGenerator
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


@pytest.fixture
def mock_embedder(sample_embedding: list[float]) -> Any:
    """Create a mock embedding generator that returns predictable embeddings."""
    original_gen = LocalEmbeddingGenerator.generate
    original_gen_async = LocalEmbeddingGenerator.generate_async

    def mock_generate(self: LocalEmbeddingGenerator, text: str) -> list[float]:
        text_hash = hash(text.strip().lower())
        import random

        random.seed(text_hash)
        return [random.random() for _ in range(EMBEDDING_DIMENSIONS)]

    async def mock_generate_async(
        self: LocalEmbeddingGenerator, text: str
    ) -> list[float]:
        return mock_generate(self, text)

    LocalEmbeddingGenerator.generate = mock_generate
    LocalEmbeddingGenerator.generate_async = mock_generate_async

    try:
        yield mock_generate
    finally:
        LocalEmbeddingGenerator.generate = original_gen
        LocalEmbeddingGenerator.generate_async = original_gen_async


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing document ingestion."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "test_ingestion.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    c.setFont("Helvetica-Bold", 24)
    c.drawString(50 * mm, height - 30 * mm, "Test Document for Integration")

    c.setFont("Helvetica", 12)
    text_y = height - 50 * mm

    text = (
        "This is a test document for integration testing. "
        "It contains multiple paragraphs for testing chunking functionality. "
        "The document includes key terms like document processing, "
        "embedding generation, and vector storage. "
        "These terms help verify that the search workflow works correctly. "
        "Additional content is added to ensure we have enough text for "
        "testing batch processing and multi-chunk scenarios. "
        "The text continues with more information about the project structure "
        "and how the various components work together."
    )

    c.drawString(50 * mm, text_y, text)

    c.showPage()
    c.setFont("Helvetica", 12)
    c.drawString(50 * mm, height - 30 * mm, "Page 2 - Additional Content")
    c.drawString(
        50 * mm,
        height - 50 * mm,
        "More content on the second page to test multi-page documents "
        "and ensure the ingestion pipeline handles page boundaries correctly.",
    )

    c.save()

    return pdf_path


@pytest.fixture
def multi_page_pdf_path(tmp_path: Path) -> Path:
    """Create a multi-page PDF for testing batch processing."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "multi_page_test.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    for page_num in range(3):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50 * mm, height - 30 * mm, f"Page {page_num + 1}")

        c.setFont("Helvetica", 12)
        c.drawString(
            50 * mm,
            height - 50 * mm,
            f"Content for page {page_num + 1} of test document. "
            f"This helps verify batch processing of multiple documents. "
            f"Each page contains unique content for testing the complete workflow.",
        )
        c.showPage()

    c.save()

    return pdf_path


@pytest.fixture
def stored_chunks(test_collection: Any, sample_embedding: list[float]) -> list[str]:
    """Store sample chunks in the test collection for testing list/search operations."""
    import random
    from uuid import uuid4

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

    original_gen = LocalEmbeddingGenerator.generate

    def mock_generate(self: LocalEmbeddingGenerator, text: str) -> list[float]:
        return sample_embedding

    LocalEmbeddingGenerator.generate = mock_generate

    try:
        yield ingestor
    finally:
        LocalEmbeddingGenerator.generate = original_gen


@pytest.fixture
def storage_with_index(test_collection: Any) -> Any:
    """Create a VectorStorage instance for integration testing."""
    os.environ["SECONDBRAIN_MONGO_URI"] = "mongodb://localhost:27017"
    os.environ["SECONDBRAIN_MONGO_DB"] = "test_secondbrain"
    os.environ["SECONDBRAIN_MONGO_COLLECTION"] = "test_embeddings"
    os.environ["SECONDBRAIN_LOCALHOST"] = "http://localhost:11434"
    os.environ["SECONDBRAIN_MODEL"] = "embeddinggemma:latest"

    from secondbrain.config import get_config

    get_config.cache_clear()

    storage = VectorStorage(
        mongo_uri="mongodb://localhost:27017",
        db_name="test_secondbrain",
        collection_name="test_embeddings",
    )

    test_collection.create_index("source_file")

    try:
        yield storage
    finally:
        storage._client = None
        storage._db = None
        storage._collection = None


@pytest.fixture
def search_workflow(storage_with_index: Any, sample_embedding: list[float]) -> Any:
    """Create a Searcher-like workflow for testing search operations."""
    from secondbrain.search import Searcher

    original_gen = LocalEmbeddingGenerator.generate

    def mock_generate(self: LocalEmbeddingGenerator, text: str) -> list[float]:
        hash_val = hash(text.lower())
        import random

        random.seed(hash_val % (2**32))
        return [random.random() for _ in range(EMBEDDING_DIMENSIONS)]

    LocalEmbeddingGenerator.generate = mock_generate

    storage_with_index.ensure_index()

    try:
        yield {
            "searcher": Searcher(verbose=False),
            "storage": storage_with_index,
            "embedding_gen": LocalEmbeddingGenerator(),
        }
    finally:
        LocalEmbeddingGenerator.generate = original_gen
