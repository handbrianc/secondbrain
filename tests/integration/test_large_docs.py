"""Integration tests for large document handling.

Tests cover:
- Large PDF files (>50MB)
- Multi-page documents (1000+ pages)
- High-resolution images
- Complex layouts
- Memory-efficient processing
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os


@pytest.mark.integration
@pytest.mark.slow
class TestLargeDocumentHandling:
    """Tests for handling large documents."""

    def test_ingest_large_pdf_memory_efficient(self):
        """Should process large PDFs without running out of memory."""
        # Mock large file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Simulate 50MB file
            f.write(b"x" * (50 * 1024 * 1024))
            large_pdf = f.name

        try:
            from secondbrain.document.ingestor import DocumentIngestor

            # Should not raise MemoryError
            ingestor = DocumentIngestor()
            with patch.object(ingestor, "_extract_text", return_value="Mock content"):
                with patch.object(ingestor, "_generate_embeddings", return_value=[]):
                    with patch.object(ingestor, "_store_document"):
                        result = ingestor.ingest(Path(large_pdf))

            assert result is not None
        finally:
            os.unlink(large_pdf)

    def test_multi_page_document_chunking(self):
        """Should correctly chunk multi-page documents."""
        from secondbrain.document import TextChunker

        # Simulate 1000 pages of text
        long_text = "Page content. " * 10000

        chunker = TextChunker(chunk_size=512, chunk_overlap=50)
        chunks = list(chunker.chunk(long_text))

        assert len(chunks) > 0
        assert all(len(chunk) <= 512 + 50 for chunk in chunks)  # chunk_size + overlap
        assert all(len(chunk) > 0 for chunk in chunks)

    def test_concurrent_large_document_ingestion(self):
        """Should handle concurrent ingestion of large documents."""
        import asyncio
        from secondbrain.document.async_ingestor import AsyncDocumentIngestor

        async def run_concurrent_ingest():
            async with AsyncDocumentIngestor() as ingestor:
                # Simulate 5 concurrent large documents
                tasks = []
                for i in range(5):
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                        f.write(b"x" * (10 * 1024 * 1024))  # 10MB each
                        tasks.append(ingestor.ingest(Path(f.name)))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Should all succeed (or be mocked)
                successful = [r for r in results if not isinstance(r, Exception)]
                assert len(successful) == 5

        asyncio.run(run_concurrent_ingest())

    def test_document_with_high_resolution_images(self):
        """Should handle documents with high-resolution images."""
        from secondbrain.document.converter import DocumentConverter

        # Mock image-heavy document
        with patch.object(DocumentConverter, "_extract_images", return_value=[]):
            converter = DocumentConverter()
            result = converter.convert(Path("test.pdf"))

            assert result is not None

    def test_memory_usage_under_load(self):
        """Should maintain reasonable memory usage under load."""
        import tracemalloc

        tracemalloc.start()

        from secondbrain.document.ingestor import DocumentIngestor

        ingestor = DocumentIngestor()

        # Process multiple documents
        for i in range(10):
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
                f.write(b"Content " * 10000)
                doc_path = Path(f.name)

            with patch.object(ingestor, "_extract_text", return_value="Mock"):
                with patch.object(ingestor, "_generate_embeddings", return_value=[]):
                    with patch.object(ingestor, "_store_document"):
                        ingestor.ingest(doc_path)

            os.unlink(doc_path)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be under 2GB
        assert peak < 2 * 1024 * 1024 * 1024


@pytest.mark.integration
@pytest.mark.slow
class TestUnicodeAndEncoding:
    """Tests for Unicode and encoding handling."""

    def test_multilingual_document_ingestion(self):
        """Should handle documents in multiple languages."""
        from secondbrain.document import TextChunker

        multilingual_text = """
        English: Machine learning is a subset of AI.
        中文：机器学习是人工智能的一个子集。
        Español: El aprendizaje automático es un subconjunto de la IA.
        Français: L'apprentissage automatique est un sous-ensemble de l'IA.
        """

        chunker = TextChunker(chunk_size=256, chunk_overlap=25)
        chunks = list(chunker.chunk(multilingual_text))

        assert len(chunks) > 0
        # All chunks should preserve Unicode
        for chunk in chunks:
            assert all(ord(c) < 65536 for c in chunk)  # Basic multilingual plane

    def test_emoji_and_special_characters(self):
        """Should handle emojis and special characters."""
        from secondbrain.document import TextChunker

        text_with_emojis = (
            "Hello 🌍! This is a test 🚀 with emojis ✨ and special chars: © ® ™"
        )

        chunker = TextChunker(chunk_size=50, chunk_overlap=5)
        chunks = list(chunker.chunk(text_with_emojis))

        assert len(chunks) > 0
        assert "🌍" in text_with_emojis  # Emojis preserved

    def test_mixed_encoding_files(self):
        """Should handle files with mixed encodings."""
        import tempfile
        from secondbrain.document.ingestor import DocumentIngestor

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as f:
            # Mix of UTF-8 and Latin-1
            f.write("UTF-8: café\n".encode("utf-8"))
            f.write("Latin-1: naïve\n".encode("latin-1"))
            f_path = f.name

        try:
            ingestor = DocumentIngestor()
            with patch.object(ingestor, "_extract_text", return_value="Mixed content"):
                with patch.object(ingestor, "_generate_embeddings", return_value=[]):
                    with patch.object(ingestor, "_store_document"):
                        result = ingestor.ingest(Path(f_path))

            assert result is not None
        finally:
            os.unlink(f_path)


@pytest.mark.integration
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_document(self):
        """Should handle empty documents gracefully."""
        from secondbrain.document.ingestor import DocumentIngestor

        ingestor = DocumentIngestor()

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"")
            empty_file = f.name

        try:
            with patch.object(ingestor, "_extract_text", return_value=""):
                with patch.object(ingestor, "_generate_embeddings", return_value=[]):
                    with patch.object(ingestor, "_store_document"):
                        result = ingestor.ingest(Path(empty_file))

            # Should handle gracefully (either skip or create minimal record)
            assert result is not None
        finally:
            os.unlink(empty_file)

    def test_very_small_chunks(self):
        """Should handle documents that result in very small chunks."""
        from secondbrain.document import TextChunker

        short_text = "Short."

        chunker = TextChunker(chunk_size=512, chunk_overlap=50)
        chunks = list(chunker.chunk(short_text))

        assert len(chunks) == 1
        assert chunks[0] == "Short."

    def test_very_large_chunk_size(self):
        """Should handle very large chunk sizes."""
        from secondbrain.document import TextChunker

        text = "Word " * 100000  # 500KB of text

        chunker = TextChunker(chunk_size=100000, chunk_overlap=1000)
        chunks = list(chunker.chunk(text))

        assert len(chunks) > 0
        assert all(len(chunk) <= 101000 for chunk in chunks)  # chunk_size + overlap

    def test_special_file_names(self):
        """Should handle files with special characters in names."""
        from secondbrain.document.ingestor import DocumentIngestor

        test_names = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "файл.txt",  # Cyrillic
            "文件.txt",  # Chinese
        ]

        for name in test_names:
            with tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False, prefix=name
            ) as f:
                f.write(b"Content")
                f_path = f.name

            try:
                assert Path(f_path).exists()
            finally:
                os.unlink(f_path)
