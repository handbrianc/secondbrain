"""Pytest fixtures for document tests."""

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
    """Mock PDF extraction to avoid dependency on docling.

    Patches the DocumentConverter to return mock documents.
    """
    mock_doc = MagicMock()
    mock_doc.pages = []

    mock_result = MagicMock()
    mock_result.document = mock_doc

    # Mock the DocumentConverter
    monkeypatch.setattr(
        "docling.document_converter.DocumentConverter",
        MagicMock(return_value=MagicMock(convert=MagicMock(return_value=mock_result))),
    )

    return mock_result
