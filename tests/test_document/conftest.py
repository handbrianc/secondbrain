"""Pytest fixtures for document tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def cached_embedding_generator() -> MagicMock:
    """Mock cached embedding generator for testing.

    Returns a MagicMock that simulates the CachedEmbeddingGenerator.
    """
    mock = MagicMock()
    mock.generate = MagicMock(return_value=[0.1] * 384)
    mock.generate_batch = MagicMock(return_value=[[0.1] * 384 for _ in range(5)])
    return mock


@pytest.fixture
def mocked_pdf_extraction(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock PDF extraction to avoid dependency on docling."""
    from unittest.mock import MagicMock

    mock_text_item = MagicMock()
    mock_text_item.text = (
        "SecondBrain test document\n\n"
        "This is sample content for testing PDF ingestion with "
        "machine learning and artificial intelligence topics."
    )
    mock_prov = MagicMock()
    mock_prov.page_no = 1
    mock_text_item.prov = [mock_prov]

    mock_doc = MagicMock()
    mock_doc.pages = []
    mock_doc.texts = [mock_text_item]

    mock_result = MagicMock()
    mock_result.document = mock_doc

    monkeypatch.setattr(
        "docling.document_converter.DocumentConverter",
        MagicMock(return_value=MagicMock(convert=MagicMock(return_value=mock_result))),
    )

    return mock_result


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return path to a sample PDF file for testing.

    Creates a temporary PDF file with test content using fpdf.
    Skips the test if fpdf is not available.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf not installed for PDF creation")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(
            0,
            10,
            "SecondBrain test document\n\n"
            "This is sample content for testing PDF ingestion with "
            "machine learning and artificial intelligence topics.",
        )
        pdf.output(tmp.name)
        return Path(tmp.name)


@pytest.fixture
def sample_pdf_with_multiple_pages() -> Path:
    """Return path to a multi-page sample PDF file for testing.

    Creates a temporary multi-page PDF file with test content using fpdf.
    Skips the test if fpdf is not available.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf not installed for PDF creation")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf = FPDF()
        for page_num in range(1, 4):
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, f"Page {page_num} of SecondBrain test document\n\n")
            pdf.multi_cell(
                0,
                10,
                f"This is unique content for page {page_num} covering "
                "machine learning, deep learning, and neural networks.",
            )
        pdf.output(tmp.name)
        return Path(tmp.name)
