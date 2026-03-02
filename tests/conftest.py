"""Pytest fixtures for secondbrain tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

import pytest

T = TypeVar("T")


@pytest.fixture
def test_data_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for test data."""
    return tmp_path / "test_data"


@pytest.fixture
def mock_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock configuration for testing."""
    test_config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_OLLAMA_URL": "http://localhost:11434",
        "SECONDBRAIN_MODEL": "embeddinggemma:latest",
        "SECONDBRAIN_CHUNK_SIZE": 512,
        "SECONDBRAIN_CHUNK_OVERLAP": 50,
        "SECONDBRAIN_DEFAULT_TOP_K": 5,
    }
    for key, value in test_config.items():
        monkeypatch.setenv(key, str(value))
    return test_config


@pytest.fixture
def sample_text() -> str:
    """Sample text for testing."""
    return "This is a sample document. It contains multiple sentences. " * 10


@pytest.fixture
def sample_embedding() -> list[float]:
    """Sample embedding vector (384 dimensions).

    Note: Test embeddings use 384 dimensions for lightweight testing,
    but the production config defaults to 768 dimensions for the
    embeddinggemma model. Tests should not rely on a specific dimension.
    """
    import random

    random.seed(42)
    return [random.random() for _ in range(384)]


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a sample PDF file for testing.

    Creates a simple PDF with some text content for testing
    the document ingestion pipeline.
    """
    from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
    from reportlab.lib.units import mm  # type: ignore[import-untyped]
    from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

    pdf_path = tmp_path / "test_document.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    # Add title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50 * mm, height - 30 * mm, "SecondBrain Test Document")

    # Add body text
    c.setFont("Helvetica", 12)
    text_y = height - 50 * mm

    # Paragraph of text for testing chunking
    text = (
        "This is a sample PDF document created for testing the ingestion pipeline. "
        "It contains multiple sentences for testing text extraction and chunking. "
        "The document includes various content to test the full ingestion pipeline. "
        "Additional testing content includes keywords like machine learning, "
        "artificial intelligence, and natural language processing. "
        "This helps verify that the embedding generation works correctly. "
        "The storage and retrieval functions are also validated through this test."
    )

    c.drawString(50 * mm, text_y, text)

    # Add more content on second page
    c.showPage()
    c.setFont("Helvetica", 12)
    c.drawString(50 * mm, height - 30 * mm, "Page 2 - Additional Content")
    c.drawString(
        50 * mm,
        height - 50 * mm,
        "More text for testing multi-page extraction and chunking.",
    )

    c.save()

    return pdf_path


@pytest.fixture
def sample_pdf_with_multiple_pages(tmp_path: Path) -> Path:
    """Create a sample multi-page PDF for testing."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "multi_page_document.pdf"

    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    _, height = A4

    # Create 3 pages
    for page_num in range(3):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(50 * mm, height - 30 * mm, f"Page {page_num + 1} - Test Document")

        c.setFont("Helvetica", 12)
        text = (
            f"This is page {page_num + 1} of a multi-page test document. "
            "It contains enough text to test multi-page extraction and chunking functionality. "
            "The content includes various topics like data science, machine learning, "
            "deep learning, neural networks, and artificial intelligence. "
            "This helps verify that text extraction works correctly across multiple pages. "
            "The chunking logic also needs to handle page boundaries properly."
        )

        c.drawString(50 * mm, height - 50 * mm, text)
        c.showPage()

    c.save()

    return pdf_path


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Clean up test embeddings after all tests complete.

    This hook runs after all tests in the session are complete.
    It deletes all documents from the test MongoDB database.
    """
    try:
        from pymongo import MongoClient

        client: MongoClient[dict[str, Any]] = MongoClient(
            "mongodb://localhost:27017", serverSelectionTimeoutMS=2000
        )
        client.drop_database("test_secondbrain")
        client.close()
    except Exception:
        pass  # Ignore cleanup errors
