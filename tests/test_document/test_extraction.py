"""Tests for document text extraction functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentExtractionError, DocumentIngestor


class TestExtractTextPdfPages:
    """Tests for multi-page PDF extraction."""

    def test_extract_text_pdf_pages_multiple_pages(self, tmp_path: Path) -> None:
        """Test multi-page PDF extraction preserves page numbers."""
        # Create a mock PDF file
        test_pdf = tmp_path / "test_multi_page.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

        ingestor = DocumentIngestor()

        # Mock docling parser to return multi-page segments
        mock_result = MagicMock()
        mock_text_items = [
            MagicMock(text="Content from page 1", prov=[MagicMock(page_no=0)]),
            MagicMock(text="Content from page 2", prov=[MagicMock(page_no=1)]),
            MagicMock(text="Content from page 3", prov=[MagicMock(page_no=2)]),
        ]
        mock_result.document.texts = mock_text_items

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_pdf)

        assert len(segments) == 3
        assert segments[0]["text"] == "Content from page 1"
        assert segments[0]["page"] == 0
        assert segments[1]["text"] == "Content from page 2"
        assert segments[1]["page"] == 1
        assert segments[2]["text"] == "Content from page 3"
        assert segments[2]["page"] == 2

    def test_extract_text_pdf_pages_no_provenance(self, tmp_path: Path) -> None:
        """Test PDF extraction defaults to page 1 when no provenance."""
        test_pdf = tmp_path / "test_no_prov.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

        ingestor = DocumentIngestor()

        # Mock docling parser with text items without provenance
        mock_result = MagicMock()
        mock_text_item = MagicMock()
        mock_text_item.text = "Content without page info"
        del mock_text_item.prov
        mock_result.document.texts = [mock_text_item]

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_pdf)

        assert len(segments) == 1
        assert segments[0]["page"] == 1

    def test_extract_text_pdf_pages_empty_provenance(self, tmp_path: Path) -> None:
        """Test PDF extraction handles empty provenance list."""
        test_pdf = tmp_path / "test_empty_prov.pdf"
        test_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

        ingestor = DocumentIngestor()

        # Mock docling parser with empty provenance
        mock_result = MagicMock()
        mock_text_item = MagicMock()
        mock_text_item.text = "Content with empty prov"
        mock_text_item.prov = []
        mock_result.document.texts = [mock_text_item]

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_pdf)

        assert len(segments) == 1
        assert segments[0]["page"] == 1


class TestExtractTextImageFallback:
    """Tests for image OCR fallback mechanism."""

    @pytest.mark.ocr
    def test_extract_text_image_fallback_ocr(self, tmp_path: Path) -> None:
        """Test image OCR fallback when docling returns no text."""
        test_image = tmp_path / "test_image.png"
        test_image.write_bytes(b"\x89PNG fake image data")

        ingestor = DocumentIngestor()

        # Mock docling parser returning no texts (image-only document)
        mock_result = MagicMock()
        mock_result.document.texts = []

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_image)

        # Should fall back to file read
        assert len(segments) >= 1
        assert "text" in segments[0]
        assert "page" in segments[0]

    def test_extract_text_image_fallback_no_texts_attr(self, tmp_path: Path) -> None:
        """Test image fallback when texts attribute is missing."""
        test_image = tmp_path / "test_image.jpg"
        test_image.write_bytes(b"\xff\xd8 fake jpeg data")

        ingestor = DocumentIngestor()

        # Mock docling parser without texts attribute
        mock_result = MagicMock()
        del mock_result.document.texts

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(test_image)

        # Should fall back to file read
        assert len(segments) >= 1
        assert "page" in segments[0]


class TestExtractTextEmptyFile:
    """Tests for empty file handling."""

    def test_extract_text_empty_file_text(self, tmp_path: Path) -> None:
        """Test empty text file handling."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")

        ingestor = DocumentIngestor()

        segments = ingestor._extract_text(empty_file)

        assert len(segments) == 1
        assert segments[0]["text"] == ""
        assert segments[0]["page"] == 1

    def test_extract_text_empty_file_pdf(self, tmp_path: Path) -> None:
        """Test empty PDF file handling falls back to file read."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")

        ingestor = DocumentIngestor()

        # Mock docling returning empty texts for empty PDF
        mock_result = MagicMock()
        mock_result.document.texts = []

        with patch.object(ingestor.converter, "convert", return_value=mock_result):
            segments = ingestor._extract_text(empty_pdf)

        assert len(segments) >= 1
        assert segments[0]["text"] == ""

    def test_extract_text_whitespace_only(self, tmp_path: Path) -> None:
        """Test file with only whitespace handling."""
        ws_file = tmp_path / "whitespace.md"
        ws_file.write_text("   \n\t\n   ")

        ingestor = DocumentIngestor()

        segments = ingestor._extract_text(ws_file)

        assert len(segments) == 1
        assert segments[0]["text"].strip() == ""


class TestExtractTextCorruptedPdf:
    """Tests for corrupted PDF error handling."""

    def test_extract_text_corrupted_pdf_magic_bytes(self, tmp_path: Path) -> None:
        """Test corrupted PDF with invalid magic bytes."""
        corrupted_pdf = tmp_path / "corrupted.pdf"
        corrupted_pdf.write_bytes(b"Not a PDF file at all")

        ingestor = DocumentIngestor()

        # Mock docling parser raising exception for corrupted PDF
        with (
            patch.object(
                ingestor.converter,
                "convert",
                side_effect=Exception("Invalid PDF format"),
            ),
            pytest.raises(DocumentExtractionError) as exc_info,
        ):
            ingestor._extract_text(corrupted_pdf)

        assert "Invalid PDF format" in str(exc_info.value)

    def test_extract_text_corrupted_pdf_truncated(self, tmp_path: Path) -> None:
        """Test truncated PDF file handling."""
        truncated_pdf = tmp_path / "truncated.pdf"
        truncated_pdf.write_bytes(b"%PDF-1.4 truncated content")

        ingestor = DocumentIngestor()

        # Mock docling parser raising parsing error
        with (
            patch.object(
                ingestor.converter, "convert", side_effect=Exception("Truncated file")
            ),
            pytest.raises(DocumentExtractionError) as exc_info,
        ):
            ingestor._extract_text(truncated_pdf)

        assert "Truncated file" in str(exc_info.value)

    def test_extract_text_corrupted_pdf_malformed(self, tmp_path: Path) -> None:
        """Test malformed PDF structure handling."""
        malformed_pdf = tmp_path / "malformed.pdf"
        malformed_pdf.write_bytes(b"%PDF-invalid structure without proper objects")

        ingestor = DocumentIngestor()

        # Mock docling parser raising format error
        with (
            patch.object(
                ingestor.converter, "convert", side_effect=Exception("Malformed PDF")
            ),
            pytest.raises(DocumentExtractionError) as exc_info,
        ):
            ingestor._extract_text(malformed_pdf)

        assert "Malformed PDF" in str(exc_info.value)

    def test_extract_text_corrupted_file_not_found(self, tmp_path: Path) -> None:
        """Test non-existent file raises DocumentExtractionError."""
        nonexistent = tmp_path / "does_not_exist.pdf"

        ingestor = DocumentIngestor()

        with pytest.raises(DocumentExtractionError) as exc_info:
            ingestor._extract_text(nonexistent)

        assert (
            "no such file" in str(exc_info.value).lower()
            or "does not exist" in str(exc_info.value).lower()
        )
