"""End-to-end integration tests for document ingestion."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentIngestor


class TestEndToEndIngestion:
    """Test full document ingestion workflow."""

    @pytest.mark.integration
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
        """Test full ingestion of a single file."""
        # Setup mocks
        mock_converter = MagicMock()
        mock_result = MagicMock()
        mock_text = MagicMock()
        mock_text.text = "Test content"
        mock_text.prov = [MagicMock(page_no=1)]
        mock_result.document.texts = [mock_text]
        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        mock_gen = MagicMock()
        mock_gen.generate.return_value = [0.1] * 384
        mock_gen.validate_connection.return_value = True
        mock_gen_class.return_value = mock_gen

        # Mock storage
        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.store_batch.return_value = 1
        mock_storage_class.return_value = mock_storage

        test_file = tmp_path / "test.pdf"
        test_file.write_text("Test PDF content")

        ingestor = DocumentIngestor(chunk_size=1000, verbose=False)
        result = ingestor.ingest(str(test_file))

        assert result["success"] == 1
        assert result["failed"] == 0

    @pytest.mark.integration
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
        """Test directory ingestion with multiple files."""
        # Setup mocks
        mock_converter = MagicMock()
        mock_result = MagicMock()
        mock_text = MagicMock()
        mock_text.text = "Content"
        mock_text.prov = [MagicMock(page_no=1)]
        mock_result.document.texts = [mock_text]
        mock_converter.convert.return_value = mock_result
        mock_converter_class.return_value = mock_converter

        mock_gen = MagicMock()
        mock_gen.generate.return_value = [0.1] * 384
        mock_gen.validate_connection.return_value = True
        mock_gen_class.return_value = mock_gen

        mock_storage = MagicMock()
        mock_storage.validate_connection.return_value = True
        mock_storage.store_batch.return_value = 1
        mock_storage_class.return_value = mock_storage

        dir_path = tmp_path / "docs"
        dir_path.mkdir()
        (dir_path / "file1.txt").write_text("File 1 content")
        (dir_path / "file2.txt").write_text("File 2 content")

        ingestor = DocumentIngestor(chunk_size=1000, verbose=False)
        result = ingestor.ingest(str(dir_path))

        assert result["success"] >= 1
