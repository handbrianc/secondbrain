"""End-to-end integration tests for document ingestion."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestEndToEndIngestion:
    """Test full document ingestion workflow."""

    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Cannot properly mock all dependencies in multiprocessing context"
    )
    @patch("docling.document_converter.DocumentConverter")
    @patch("secondbrain.embedding.LocalEmbeddingGenerator")
    @patch("secondbrain.storage.VectorStorage")
    def test_ingest_file_e2e(
        self,
        mock_storage_class: MagicMock,
        mock_gen_class: MagicMock,
        mock_converter_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test full ingestion of a single file.

        SKIPPED: The multiprocessing architecture prevents proper mocking of
        dependencies in worker processes.
        """
        # Test skipped - see docstring
        pass

    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Cannot properly mock all dependencies in multiprocessing context"
    )
    @patch("docling.document_converter.DocumentConverter")
    @patch("secondbrain.embedding.LocalEmbeddingGenerator")
    @patch("secondbrain.storage.VectorStorage")
    def test_ingest_directory_e2e(
        self,
        mock_storage_class: MagicMock,
        mock_gen_class: MagicMock,
        mock_converter_class: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test directory ingestion with multiple files.

        SKIPPED: The multiprocessing architecture prevents proper mocking.
        """
        # Test skipped - see docstring
        pass
