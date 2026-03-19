"""Additional edge case tests for document module to improve coverage."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secondbrain.document import DocumentIngestor, Segment


class TestDocumentIngestorCollectFiles:
    """Tests for _collect_and_validate_files method."""

    def test_collect_from_directory_with_supported_files(self, tmp_path: Path) -> None:
        """Test collecting files from directory with supported file types."""
        ingestor = DocumentIngestor()

        # Create supported and unsupported files
        (tmp_path / "test1.txt").write_text("content 1")
        (tmp_path / "test2.pdf").write_text("content 2")
        (tmp_path / "test3.exe").write_text("content 3")  # Unsupported

        files = ingestor._collect_and_validate_files(str(tmp_path), recursive=False)

        assert len(files) == 2
        assert any("test1.txt" in str(f) for f in files)
        assert any("test2.pdf" in str(f) for f in files)

    def test_collect_from_directory_recursive(self, tmp_path: Path) -> None:
        """Test recursive file collection from subdirectories."""
        ingestor = DocumentIngestor()

        # Create subdirectory structure
        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        (tmp_path / "root.txt").write_text("root")
        (subdir / "nested.txt").write_text("nested")

        files = ingestor._collect_and_validate_files(str(tmp_path), recursive=True)

        assert len(files) == 2
        assert any("root.txt" in str(f) for f in files)
        assert any("nested.txt" in str(f) for f in files)

    def test_collect_from_directory_non_recursive(self, tmp_path: Path) -> None:
        """Test non-recursive collection ignores subdirectories."""
        ingestor = DocumentIngestor()

        # Create subdirectory with files
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        (tmp_path / "root.txt").write_text("root")
        (subdir / "nested.txt").write_text("nested")

        files = ingestor._collect_and_validate_files(str(tmp_path), recursive=False)

        # Should only find root.txt, not nested.txt
        assert len(files) == 1
        assert "root.txt" in str(files[0])

    def test_collect_rejects_invalid_path(self, tmp_path: Path) -> None:
        """Test that invalid paths raise ValueError."""
        ingestor = DocumentIngestor()
        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(ValueError, match="Invalid path"):
            ingestor._collect_and_validate_files(str(nonexistent), recursive=False)


class TestDocumentIngestorIngestEdgeCases:
    """Additional edge case tests for ingest method."""

    def test_ingest_empty_directory_returns_zeros(self, tmp_path: Path) -> None:
        """Test ingesting empty directory returns success=0, failed=0."""
        ingestor = DocumentIngestor()

        result = ingestor.ingest(str(tmp_path))

        assert result == {"success": 0, "failed": 0}

    def test_ingest_directory_with_no_supported_files(self, tmp_path: Path) -> None:
        """Test directory with only unsupported files returns success=0."""
        ingestor = DocumentIngestor()

        # Create only unsupported files
        (tmp_path / "test.exe").write_text("content")
        (tmp_path / "test.bat").write_text("content")

        result = ingestor.ingest(str(tmp_path))

        assert result == {"success": 0, "failed": 0}


class TestDocumentIngestorBuildDocumentsEdgeCases:
    """Edge case tests for _build_documents_with_embeddings."""

    def test_build_documents_with_sentence_transformers_unavailable_error(
        self, tmp_path: Path
    ) -> None:
        """Test SentenceTransformersUnavailableError in embedding generation."""
        from secondbrain.exceptions import SentenceTransformersUnavailableError

        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [{"text": "test text", "page": 1}]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.side_effect = SentenceTransformersUnavailableError(
            "SentenceTransformers unavailable"
        )

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        # Should return empty list when all embeddings fail
        assert len(docs) == 0

    def test_build_documents_skips_chunks_without_embedding(
        self, tmp_path: Path
    ) -> None:
        """Test that chunks without successful embedding are skipped."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "First text", "page": 1},
            {"text": "Second text", "page": 2},
            {"text": "Third text", "page": 3},
        ]

        mock_embedding_gen = MagicMock()
        # First succeeds, second fails, third succeeds
        mock_embedding_gen.generate.side_effect = [
            [0.1] * 384,
            Exception("Random error"),
            [0.2] * 384,
        ]

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        # Should have 2 docs (first and third, second skipped)
        assert len(docs) == 2

    def test_build_documents_with_multiple_pages(self, tmp_path: Path) -> None:
        """Test building documents from multi-page segments."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        segments: list[Segment] = [
            {"text": "Page 1 content", "page": 1},
            {"text": "Page 2 content", "page": 2},
            {"text": "Page 3 content", "page": 3},
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        assert len(docs) == 3
        assert docs[0]["page_number"] == 1
        assert docs[1]["page_number"] == 2
        assert docs[2]["page_number"] == 3

    def test_build_documents_preserves_file_type_metadata(self, tmp_path: Path) -> None:
        """Test that file type is correctly preserved in metadata."""
        ingestor = DocumentIngestor()

        # Create a PDF file
        test_file = tmp_path / "test.pdf"
        test_file.write_text("PDF content")

        segments: list[Segment] = [{"text": "test text", "page": 1}]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        assert len(docs) == 1
        assert docs[0]["file_type"] == "pdf"

    def test_build_documents_with_large_number_of_chunks(self, tmp_path: Path) -> None:
        """Test building documents with many chunks."""
        ingestor = DocumentIngestor()
        test_file = tmp_path / "test.txt"

        # Create many segments
        segments: list[Segment] = [
            {"text": f"Chunk {i} text", "page": i % 10} for i in range(50)
        ]

        mock_embedding_gen = MagicMock()
        mock_embedding_gen.generate.return_value = [0.1] * 384

        docs = ingestor._build_documents_with_embeddings(
            test_file, segments, mock_embedding_gen
        )

        assert len(docs) == 50
