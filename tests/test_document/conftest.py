"""Pytest fixtures for document tests."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _cleanup_temp_path(path: Path) -> None:
    """Remove a temp file if it still exists."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


@pytest.fixture(autouse=True, scope="session")
def _stub_docling_modules() -> None:
    """Stub out docling submodules before any test imports DocumentIngestor.

    DocumentIngestor's __init__ eagerly imports:
        from docling.datamodel.accelerator_options import ...
        from docling.datamodel.base_models import ...
        from docling.datamodel.pipeline_options import ...
        from docling.document_converter import DocumentConverter, PdfFormatOption

    Without stubbing, each DocumentIngestor() instantiation pays ~1-2s of
    docling package import overhead even when converter is never used in tests.
    Stubbing at sys.modules level prevents the actual imports from executing.
    """
    stub = MagicMock()
    for mod_name in (
        "docling",
        "docling.datamodel",
        "docling.datamodel.accelerator_options",
        "docling.datamodel.base_models",
        "docling.datamodel.pipeline_options",
        "docling.document_converter",
        "docling.document_converter_PdfFormatOption",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = stub


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
def sample_pdf_path(request: pytest.FixtureRequest) -> Path:
    """Return path to a sample PDF file for testing.

    Creates a temporary PDF file with test content using fpdf.
    Skips the test if fpdf is not available.
    The file is cleaned up after the test completes.
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
        path = Path(tmp.name)
        request.addfinalizer(lambda: _cleanup_temp_path(path))
        return path


@pytest.fixture
def sample_pdf_with_multiple_pages(request: pytest.FixtureRequest) -> Path:
    """Return path to a multi-page sample PDF file for testing.

    Creates a temporary multi-page PDF file with test content using fpdf.
    Skips the test if fpdf is not available.
    The file is cleaned up after the test completes.
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
        path = Path(tmp.name)
        request.addfinalizer(lambda: _cleanup_temp_path(path))
        return path
