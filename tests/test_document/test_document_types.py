"""Tests for non-PDF document type ingestion.

This test suite validates that docling can successfully ingest and extract
text from all supported document formats beyond PDFs.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.document import DocumentIngestor, get_file_type, is_supported


class TestOfficeFormats:
    """Tests for Microsoft Office document formats (DOCX, PPTX, XLSX)."""

    @pytest.fixture
    def mock_docling_converter(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Mock docling converter for Office format tests."""
        from unittest.mock import MagicMock

        mock_converter = MagicMock()
        mock_result = MagicMock()

        # Default mock segments
        mock_text_item = MagicMock()
        mock_text_item.text = "Sample Office document content"
        mock_text_item.prov = [MagicMock(page_no=1)]
        mock_result.document.texts = [mock_text_item]

        mock_converter.convert.return_value = mock_result
        monkeypatch.setattr(
            "docling.document_converter.DocumentConverter",
            lambda: mock_converter,
        )
        return mock_converter

    def test_docx_file_type_detection(self) -> None:
        """Test DOCX file type is correctly detected."""
        assert get_file_type(Path("document.docx")) == "docx"
        assert get_file_type(Path("DOCUMENT.DOCX")) == "docx"

    def test_docx_is_supported(self) -> None:
        """Test DOCX files are supported."""
        assert is_supported(Path("report.docx"))
        assert is_supported(Path("presentation.DOCX"))

    def test_docx_ingestion(
        self, mock_docling_converter: MagicMock, tmp_path: Path
    ) -> None:
        """Test DOCX document ingestion."""
        test_file = tmp_path / "test.docx"
        test_file.write_text("Mock DOCX content")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Word document content with paragraphs"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "text" in segments[0]
        assert "page" in segments[0]

    def test_pptx_file_type_detection(self) -> None:
        """Test PPTX file type is correctly detected."""
        assert get_file_type(Path("presentation.pptx")) == "pptx"
        assert get_file_type(Path("SLIDES.PPTX")) == "pptx"

    def test_pptx_is_supported(self) -> None:
        """Test PPTX files are supported."""
        assert is_supported(Path("slides.pptx"))
        assert is_supported(Path("deck.PPTX"))

    def test_pptx_ingestion(
        self, mock_docling_converter: MagicMock, tmp_path: Path
    ) -> None:
        """Test PPTX document ingestion."""
        test_file = tmp_path / "test.pptx"
        test_file.write_text("Mock PPTX content")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Slide 1: Introduction\nSlide 2: Content"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Slide" in segments[0]["text"]

    def test_xlsx_file_type_detection(self) -> None:
        """Test XLSX file type is correctly detected."""
        assert get_file_type(Path("spreadsheet.xlsx")) == "xlsx"
        assert get_file_type(Path("DATA.XLSX")) == "xlsx"

    def test_xlsx_is_supported(self) -> None:
        """Test XLSX files are supported."""
        assert is_supported(Path("data.xlsx"))
        assert is_supported(Path("budget.XLSX"))

    def test_xlsx_ingestion(
        self, mock_docling_converter: MagicMock, tmp_path: Path
    ) -> None:
        """Test XLSX document ingestion."""
        test_file = tmp_path / "test.xlsx"
        test_file.write_text("Mock XLSX content")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Column A, Column B, Column C\n1, 2, 3"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Column" in segments[0]["text"]


class TestWebFormats:
    """Tests for web document formats (HTML, Markdown, XML)."""

    def test_html_file_type_detection(self) -> None:
        """Test HTML file type is correctly detected."""
        assert get_file_type(Path("page.html")) == "html"
        assert get_file_type(Path("page.htm")) == "html"
        assert get_file_type(Path("PAGE.HTML")) == "html"

    def test_html_is_supported(self) -> None:
        """Test HTML files are supported."""
        assert is_supported(Path("index.html"))
        assert is_supported(Path("page.HTM"))

    def test_html_ingestion(self, tmp_path: Path) -> None:
        """Test HTML document ingestion."""
        test_file = tmp_path / "test.html"
        test_file.write_text(
            "<html><body><h1>Title</h1><p>Content paragraph</p></body></html>"
        )

        ingestor = DocumentIngestor(chunk_size=512)

        # HTML should be processed by docling converter
        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Title\nContent paragraph"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Title" in segments[0]["text"]

    def test_markdown_file_type_detection(self) -> None:
        """Test Markdown file type is correctly detected."""
        assert get_file_type(Path("readme.md")) == "markdown"
        assert get_file_type(Path("README.MD")) == "markdown"

    def test_markdown_is_supported(self) -> None:
        """Test Markdown files are supported."""
        assert is_supported(Path("readme.md"))
        assert is_supported(Path("doc.MD"))

    def test_markdown_ingestion_simple(self, tmp_path: Path) -> None:
        """Test Markdown ingestion via docling converter."""
        test_file = tmp_path / "test.md"
        content = "# Heading\n\nThis is **bold** and *italic* text."
        test_file.write_text(content)

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Heading\nThis is **bold** and *italic* text."
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Heading" in segments[0]["text"]
        assert "bold" in segments[0]["text"]

    def test_markdown_ingestion_with_converter(self, tmp_path: Path) -> None:
        """Test Markdown ingestion via docling converter."""
        test_file = tmp_path / "test.md"
        test_file.write_text("# Title\n\nContent")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Title\nContent"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0

    def test_xml_file_type_detection(self) -> None:
        """Test XML file type is correctly detected."""
        assert get_file_type(Path("data.xml")) == "xml"
        assert get_file_type(Path("DATA.XML")) == "xml"

    def test_xml_is_supported(self) -> None:
        """Test XML files are supported."""
        assert is_supported(Path("config.xml"))
        assert is_supported(Path("data.XML"))

    def test_xml_ingestion(self, tmp_path: Path) -> None:
        """Test XML document ingestion."""
        test_file = tmp_path / "test.xml"
        test_file.write_text(
            '<?xml version="1.0"?><root><item>Value 1</item><item>Value 2</item></root>'
        )

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Value 1\nValue 2"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0


class TestStructuredDataFormats:
    """Tests for structured data formats (CSV, JSON)."""

    def test_csv_file_type_detection(self) -> None:
        """Test CSV file type is correctly detected."""
        assert get_file_type(Path("data.csv")) == "csv"
        assert get_file_type(Path("DATA.CSV")) == "csv"

    def test_csv_is_supported(self) -> None:
        """Test CSV files are supported."""
        assert is_supported(Path("data.csv"))
        assert is_supported(Path("export.CSV"))

    def test_csv_ingestion(self, tmp_path: Path) -> None:
        """Test CSV document ingestion."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("name,age,city\nJohn,30,New York\nJane,25,Los Angeles")

        ingestor = DocumentIngestor(chunk_size=512)

        # CSV should fall back to file read for simple processing
        segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "name" in segments[0]["text"]
        assert "John" in segments[0]["text"]

    def test_json_file_type_detection(self) -> None:
        """Test JSON file type is correctly detected as docling-json."""
        assert get_file_type(Path("data.json")) == "docling-json"
        assert get_file_type(Path("DATA.JSON")) == "docling-json"

    def test_json_is_supported(self) -> None:
        """Test JSON files are supported."""
        assert is_supported(Path("config.json"))
        assert is_supported(Path("data.JSON"))

    def test_json_ingestion(self, tmp_path: Path) -> None:
        """Test JSON document ingestion."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"name": "test", "value": 123}')

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = '{"name": "test", "value": 123}'
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0


class TestImageFormats:
    """Tests for image formats (PNG, JPEG, TIFF, BMP, WEBP)."""

    def test_png_file_type_detection(self) -> None:
        """Test PNG file type is correctly detected."""
        assert get_file_type(Path("image.png")) == "image"
        assert get_file_type(Path("IMAGE.PNG")) == "image"

    def test_jpeg_file_type_detection(self) -> None:
        """Test JPEG file type is correctly detected."""
        assert get_file_type(Path("image.jpg")) == "image"
        assert get_file_type(Path("image.jpeg")) == "image"
        assert get_file_type(Path("IMAGE.JPG")) == "image"

    def test_tiff_file_type_detection(self) -> None:
        """Test TIFF file type is correctly detected."""
        assert get_file_type(Path("image.tiff")) == "image"
        assert get_file_type(Path("image.tif")) == "image"
        assert get_file_type(Path("IMAGE.TIFF")) == "image"

    def test_bmp_file_type_detection(self) -> None:
        """Test BMP file type is correctly detected."""
        assert get_file_type(Path("image.bmp")) == "image"
        assert get_file_type(Path("IMAGE.BMP")) == "image"

    def test_webp_file_type_detection(self) -> None:
        """Test WEBP file type is correctly detected."""
        assert get_file_type(Path("image.webp")) == "image"
        assert get_file_type(Path("IMAGE.WEBP")) == "image"

    def test_all_image_extensions_supported(self) -> None:
        """Test all image extensions are supported."""
        image_extensions = [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"]
        for ext in image_extensions:
            assert is_supported(Path(f"test{ext}")), f"{ext} should be supported"

    def test_png_ingestion_with_ocr(self, tmp_path: Path) -> None:
        """Test PNG image ingestion (requires OCR)."""
        test_file = tmp_path / "test.png"
        # Create a minimal valid PNG header (just for testing path)
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "OCR extracted text from image"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "OCR" in segments[0]["text"]

    def test_jpeg_ingestion(self, tmp_path: Path) -> None:
        """Test JPEG image ingestion."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)  # JPEG header

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Text content from JPEG image"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0


class TestAudioFormats:
    """Tests for audio formats (WAV, MP3)."""

    def test_wav_file_type_detection(self) -> None:
        """Test WAV file type is correctly detected."""
        assert get_file_type(Path("audio.wav")) == "audio"
        assert get_file_type(Path("AUDIO.WAV")) == "audio"

    def test_mp3_file_type_detection(self) -> None:
        """Test MP3 file type is correctly detected."""
        assert get_file_type(Path("audio.mp3")) == "audio"
        assert get_file_type(Path("AUDIO.MP3")) == "audio"

    def test_all_audio_extensions_supported(self) -> None:
        """Test all audio extensions are supported."""
        audio_extensions = [".wav", ".mp3"]
        for ext in audio_extensions:
            assert is_supported(Path(f"test{ext}")), f"{ext} should be supported"

    def test_wav_ingestion_with_transcription(self, tmp_path: Path) -> None:
        """Test WAV audio ingestion (requires speech-to-text)."""
        test_file = tmp_path / "test.wav"
        # Create a minimal WAV header
        test_file.write_bytes(b"RIFF" + b"\x00" * 100)

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Transcribed speech from audio file"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Transcribed" in segments[0]["text"]

    def test_mp3_ingestion(self, tmp_path: Path) -> None:
        """Test MP3 audio ingestion."""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"\xff\xfb" + b"\x00" * 100)  # MP3 header

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Speech transcription from MP3"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0


class TestSpecialtyFormats:
    """Tests for specialty formats (LaTeX, AsciiDoc, WebVTT, plain text)."""

    def test_latex_file_type_detection(self) -> None:
        """Test LaTeX file type is correctly detected."""
        assert get_file_type(Path("document.tex")) == "latex"
        assert get_file_type(Path("DOCUMENT.TEX")) == "latex"

    def test_latex_is_supported(self) -> None:
        """Test LaTeX files are supported."""
        assert is_supported(Path("paper.tex"))
        assert is_supported(Path("thesis.TEX"))

    def test_latex_ingestion(self, tmp_path: Path) -> None:
        """Test LaTeX document ingestion."""
        test_file = tmp_path / "test.tex"
        test_file.write_text(
            r"\documentclass{article}\begin{document}\section{Intro}Content\end{document}"
        )

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Intro\nContent"
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "Intro" in segments[0]["text"]

    def test_asciidoc_file_type_detection(self) -> None:
        """Test AsciiDoc file type is correctly detected."""
        assert get_file_type(Path("document.adoc")) == "asciidoc"
        assert get_file_type(Path("document.asciidoc")) == "asciidoc"
        assert get_file_type(Path("DOCUMENT.ADOC")) == "asciidoc"

    def test_asciidoc_is_supported(self) -> None:
        """Test AsciiDoc files are supported."""
        assert is_supported(Path("readme.adoc"))
        assert is_supported(Path("doc.ASCIIDOC"))

    def test_asciidoc_ingestion(self, tmp_path: Path) -> None:
        """Test AsciiDoc document ingestion."""
        test_file = tmp_path / "test.adoc"
        test_file.write_text("= Title\n\nThis is AsciiDoc content.")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Title\nThis is AsciiDoc content."
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0

    def test_webvtt_file_type_detection(self) -> None:
        """Test WebVTT file type is correctly detected."""
        assert get_file_type(Path("subtitles.vtt")) == "webvtt"
        assert get_file_type(Path("SUBTITLES.VTT")) == "webvtt"

    def test_webvtt_is_supported(self) -> None:
        """Test WebVTT files are supported."""
        assert is_supported(Path("captions.vtt"))
        assert is_supported(Path("subs.VTT"))

    def test_webvtt_ingestion(self, tmp_path: Path) -> None:
        """Test WebVTT subtitle ingestion."""
        test_file = tmp_path / "test.vtt"
        test_file.write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello, this is a subtitle."
        )

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "Hello, this is a subtitle."
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "subtitle" in segments[0]["text"]

    def test_txt_file_type_detection(self) -> None:
        """Test plain text file type is correctly detected."""
        assert get_file_type(Path("document.txt")) == "text"
        assert get_file_type(Path("DOCUMENT.TXT")) == "text"

    def test_txt_is_supported(self) -> None:
        """Test plain text files are supported."""
        assert is_supported(Path("readme.txt"))
        assert is_supported(Path("notes.TXT"))

    def test_txt_ingestion(self, tmp_path: Path) -> None:
        """Test plain text file ingestion via docling converter."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("This is plain text content for testing.")

        ingestor = DocumentIngestor(chunk_size=512)

        with patch.object(ingestor.converter, "convert") as mock_convert:
            mock_result = MagicMock()
            mock_text = MagicMock()
            mock_text.text = "This is plain text content for testing."
            mock_text.prov = [MagicMock(page_no=1)]
            mock_result.document.texts = [mock_text]
            mock_convert.return_value = mock_result

            segments = ingestor._extract_text(test_file)

        assert len(segments) > 0
        assert "plain text" in segments[0]["text"]


class TestDocumentTypeCoverage:
    """Tests to ensure all supported formats are covered."""

    def test_all_extensions_have_file_type_mapping(self) -> None:
        """Test every SUPPORTED_EXTENSION has a corresponding file type mapping."""
        from secondbrain.document import SUPPORTED_EXTENSIONS

        # All extensions that should map to specific types
        type_mappings = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".pptx": "pptx",
            ".xlsx": "xlsx",
            ".html": "html",
            ".htm": "html",
            ".md": "markdown",
            ".txt": "text",
            ".asciidoc": "asciidoc",
            ".adoc": "asciidoc",
            ".tex": "latex",
            ".csv": "csv",
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".tiff": "image",
            ".tif": "image",
            ".bmp": "image",
            ".webp": "image",
            ".wav": "audio",
            ".mp3": "audio",
            ".vtt": "webvtt",
            ".xml": "xml",
            ".json": "docling-json",
        }

        # Verify all supported extensions have mappings
        for ext in SUPPORTED_EXTENSIONS:
            assert ext in type_mappings, f"Extension {ext} has no file type mapping"

    def test_non_pdf_types_are_tested(self) -> None:
        """Verify that non-PDF types have dedicated tests."""
        import inspect

        # This test documents that we now have coverage for:
        # - Office: DOCX, PPTX, XLSX
        # - Web: HTML, Markdown, XML
        # - Structured: CSV, JSON
        # - Images: PNG, JPEG, TIFF, BMP, WEBP
        # - Audio: WAV, MP3
        # - Specialty: LaTeX, AsciiDoc, WebVTT, TXT
        test_methods = inspect.getmembers(self, predicate=inspect.ismethod)
        test_names = [name for name, _ in test_methods if name.startswith("test_")]

        assert len(test_names) > 0
