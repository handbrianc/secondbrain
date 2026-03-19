"""Tests for DocumentIngestor validation and error handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentIngestor, Segment


class TestDocumentIngestorValidation:
    """Tests for DocumentIngestor parameter validation."""

    def test_init_rejects_zero_chunk_size(self) -> None:
        """Test that chunk_size=0 raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            DocumentIngestor(chunk_size=0)

    def test_init_rejects_negative_chunk_size(self) -> None:
        """Test that negative chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            DocumentIngestor(chunk_size=-1)

    def test_init_rejects_negative_chunk_overlap(self) -> None:
        """Test that negative chunk_overlap raises ValueError."""
        with pytest.raises(ValueError, match="chunk_overlap must be non-negative"):
            DocumentIngestor(chunk_size=100, chunk_overlap=-1)

    def test_init_rejects_overlap_gte_chunk_size(self) -> None:
        """Test that chunk_overlap >= chunk_size raises ValueError."""
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            DocumentIngestor(chunk_size=100, chunk_overlap=100)

    def test_init_rejects_overlap_exceeds_chunk_size(self) -> None:
        """Test that chunk_overlap > chunk_size raises ValueError."""
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            DocumentIngestor(chunk_size=100, chunk_overlap=150)


class TestDocumentIngestorPathValidation:
    """Tests for DocumentIngestor path validation."""

    def test_validate_file_path_rejects_traversal(self, tmp_path: Path) -> None:
        """Test that paths with '..' raise ValueError."""
        ingestor = DocumentIngestor()
        malicious_path = tmp_path / "subdir" / ".." / "secret.txt"

        with pytest.raises(ValueError, match="Path traversal detected"):
            ingestor._validate_file_path(malicious_path)

    def test_validate_file_path_rejects_encoded_traversal(self, tmp_path: Path) -> None:
        """Test that paths with encoded '..' raise ValueError."""
        ingestor = DocumentIngestor()
        # Create a file with encoded traversal in name
        encoded_path = tmp_path / "file%2e%2e%2fsecret.txt"
        encoded_path.write_text("test")

        with pytest.raises(ValueError, match="Encoded path traversal detected"):
            ingestor._validate_file_path(encoded_path)

    def test_validate_file_path_accepts_valid_path(self, tmp_path: Path) -> None:
        """Test that valid paths pass validation."""
        ingestor = DocumentIngestor()
        valid_path = tmp_path / "valid.txt"
        valid_path.write_text("test")

        # Should not raise
        ingestor._validate_file_path(valid_path)

    def test_validate_file_size_rejects_oversized_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that files exceeding max_size raise ValueError."""
        # Create a small test file
        test_file = tmp_path / "small.txt"
        test_file.write_text("x" * 100)

        # Mock config to have very small max size
        monkeypatch.setattr(
            "secondbrain.document.get_config",
            lambda: MagicMock(max_file_size_bytes=50),  # 50 bytes max
        )

        ingestor = DocumentIngestor()

        with pytest.raises(ValueError, match="exceeds maximum size limit"):
            ingestor._validate_file_size(test_file)

    def test_validate_file_size_accepts_valid_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that files within limit pass validation."""
        test_file = tmp_path / "small.txt"
        test_file.write_text("x" * 100)

        # Mock config to have larger max size
        monkeypatch.setattr(
            "secondbrain.document.get_config",
            lambda: MagicMock(max_file_size_bytes=1024),  # 1KB max
        )

        ingestor = DocumentIngestor()

        # Should not raise
        ingestor._validate_file_size(test_file)


class TestDocumentIngestorFileProcessing:
    """Tests for DocumentIngestor file processing error handling."""

    def test_process_file_for_storage_extraction_failure(self, tmp_path: Path) -> None:
        """Test that extraction failure returns None."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock _extract_text to raise an exception
        with patch.object(ingestor, "_extract_text", side_effect=OSError("Read error")):
            result = ingestor._process_file_for_storage(test_file, MagicMock())

        assert result is None

    def test_process_file_for_storage_unexpected_error(self, tmp_path: Path) -> None:
        """Test that unexpected errors return None."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock _extract_text to raise an unexpected exception
        with patch.object(
            ingestor, "_extract_text", side_effect=Exception("Unexpected error")
        ):
            result = ingestor._process_file_for_storage(test_file, MagicMock())

        assert result is None

    def test_build_documents_with_embeddings_success(self, tmp_path: Path) -> None:
        """Test successful document building with embeddings."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "First chunk of text", "page": 1},
            {"text": "Second chunk of text", "page": 2},
        ]

        # Mock embedding generator
        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        assert len(docs) == 2
        assert all("chunk_id" in doc for doc in docs)
        assert all("embedding" in doc for doc in docs)
        assert all("file_type" in doc for doc in docs)  # Flattened from metadata
        assert docs[0]["page_number"] == 1
        assert docs[1]["page_number"] == 2

    def test_build_documents_with_embeddings_deduplication(
        self, tmp_path: Path
    ) -> None:
        """Test that duplicate text produces single chunk."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "Duplicate text here", "page": 1},
            {"text": "Duplicate text here", "page": 2},  # Same text
            {"text": "Different text", "page": 3},
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        # Should have 2 docs, not 3 (duplicates removed)
        assert len(docs) == 2

    def test_build_documents_with_embeddings_embedding_failure(
        self, tmp_path: Path
    ) -> None:
        """Test that embedding failures skip the chunk."""
        from secondbrain.exceptions import EmbeddingGenerationError

        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "First text", "page": 1},
            {"text": "Second text", "page": 2},
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.side_effect = [
            [0.1] * 384,  # First succeeds
            EmbeddingGenerationError("Failed"),  # Second fails
        ]

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        # Should have 1 doc (second skipped due to embedding failure)
        assert len(docs) == 1

    def test_build_documents_with_embeddings_empty_text_skipped(
        self, tmp_path: Path
    ) -> None:
        """Test that empty text segments are skipped."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "", "page": 1},  # Empty
            {"text": "Valid text", "page": 2},
            {"text": "   ", "page": 3},  # Whitespace only
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        # Should have 1 doc (empty/whitespace skipped)
        assert len(docs) == 1


class TestDocumentIngestorIngestErrorHandling:
    """Tests for DocumentIngestor.ingest error handling."""

    def test_ingest_handles_file_exception(self, tmp_path: Path) -> None:
        """Test that exceptions in file processing increment failed count."""
        ingestor = DocumentIngestor()

        # Create a valid text file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock _process_file_for_storage to raise an exception
        with patch.object(
            ingestor,
            "_process_file_for_storage",
            side_effect=Exception("Processing error"),
        ):
            result = ingestor.ingest(str(tmp_path))

        assert result["failed"] == 1
        assert result["success"] == 0


class TestDocumentIngestorExtractTextPageNumbers:
    """Tests for _extract_text page number extraction."""

    def test_extract_text_with_page_numbers(self, tmp_path: Path) -> None:
        """Test that page numbers are extracted from prov objects."""
        from unittest.mock import MagicMock

        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock converter to return content with prov objects
        mock_result = MagicMock()
        mock_content = MagicMock()

        mock_text_item = MagicMock()
        mock_text_item.text = "Text with page number"

        # Mock prov object with page_no
        mock_prov = MagicMock()
        mock_prov.page_no = 7
        mock_text_item.prov = [mock_prov]

        mock_content.texts = [mock_text_item]
        mock_result.document = mock_content

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_file)

        assert len(segments) == 1
        assert segments[0]["page"] == 7

    def test_extract_text_without_prov_falls_back_to_default(
        self, tmp_path: Path
    ) -> None:
        """Test that missing prov defaults to page 1."""
        from unittest.mock import MagicMock

        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        # Mock converter to return content without prov
        mock_result = MagicMock()
        mock_content = MagicMock()

        mock_text_item = MagicMock()
        mock_text_item.text = "Text without page info"
        mock_text_item.prov = []  # Empty prov

        mock_content.texts = [mock_text_item]
        mock_result.document = mock_content

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_file)

        assert len(segments) == 1
        assert segments[0]["page"] == 1
