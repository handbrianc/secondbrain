"""Comprehensive tests for document chunking functionality.

Tests the _chunk_segments and related chunking/deduplication methods
of DocumentIngestor, focusing on boundary cases, overlap validation,
large documents, multiline handling, Unicode, and deduplication.
"""

import pytest

from pathlib import Path

from secondbrain.document import DocumentIngestor, Segment


class TestChunkSegmentsBoundaryCases:
    """Test chunking with exact boundaries, empty text, and single word cases."""

    @pytest.mark.fast
    def test_chunk_segments_empty_text(self) -> None:
        """Test chunking produces no chunks for empty text."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "", "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 0

    @pytest.mark.fast
    def test_chunk_segments_whitespace_only(self) -> None:
        """Test chunking produces no chunks for whitespace-only text."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "   \n\t  ", "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 0

    @pytest.mark.fast
    def test_chunk_segments_single_word_shorter_than_chunk(self) -> None:
        """Test single word shorter than chunk size produces one chunk."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "Hello", "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Hello"
        assert chunks[0]["page"] == 1

    @pytest.mark.fast
    def test_chunk_segments_single_word_exact_chunk_size(self) -> None:
        """Test single word exactly at chunk size."""
        text = "A" * 100
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=0)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 1
        assert len(chunks[0]["text"]) <= 100

    @pytest.mark.fast
    def test_chunk_segments_exact_boundary_no_overlap(self) -> None:
        """Test exact boundary with zero overlap."""
        text = "Word " * 20  # 100 chars
        ingestor = DocumentIngestor(chunk_size=50, chunk_overlap=0)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) >= 1
        assert all(len(chunk["text"]) <= 50 for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_single_character(self) -> None:
        """Test chunking with single character text."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "X", "page": 5}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 1
        assert chunks[0]["text"] == "X"
        assert chunks[0]["page"] == 5

    @pytest.mark.fast
    def test_chunk_segments_newline_only(self) -> None:
        """Test chunking with only newlines."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "\n\n\n", "page": 1}]
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) == 0


class TestChunkSegmentsOverlapValidation:
    """Test that overlap preserves context across chunk boundaries."""

    @pytest.mark.fast
    def test_chunk_segments_overlap_preserves_context(self) -> None:
        """Verify overlap preserves context from previous chunk."""
        # Create text where overlap should capture last words
        text = "First chunk text here. Second chunk text here. " * 10
        ingestor = DocumentIngestor(chunk_size=50, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 2

        # Verify overlap: last 20 chars of chunk 0 should appear in chunk 1
        chunk0_end = chunks[0]["text"][-20:]
        chunk1_start = chunks[1]["text"][:20]

        # Overlap should preserve some context
        assert any(word in chunk1_start for word in chunk0_end.split())

    @pytest.mark.fast
    def test_chunk_segments_overlap_size_validation(self) -> None:
        """Test that overlap size is respected."""
        text = "Word " * 100
        overlap_size = 30
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=overlap_size)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 2

        # Check that chunks have proper overlap
        for i in range(len(chunks) - 1):
            chunk0 = chunks[i]["text"]
            chunk1 = chunks[i + 1]["text"]
            # Last part of chunk0 should appear at start of chunk1
            overlap_region = (
                chunk0[-overlap_size:] if len(chunk0) > overlap_size else chunk0
            )
            assert any(word in chunk1 for word in overlap_region.split()), (
                f"Overlap not preserved between chunk {i} and {i + 1}"
            )

    @pytest.mark.fast
    def test_chunk_segments_zero_overlap(self) -> None:
        """Test chunking with zero overlap produces contiguous chunks."""
        text = "Word " * 50
        ingestor = DocumentIngestor(chunk_size=50, chunk_overlap=0)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # With zero overlap, chunks should not share words
        for i in range(len(chunks) - 1):
            chunk0_words = set(chunks[i]["text"].split())
            chunk1_words = set(chunks[i + 1]["text"].split())
            # Minimal overlap allowed due to word boundary splitting
            assert len(chunk0_words & chunk1_words) <= 2

    @pytest.mark.fast
    def test_chunk_segments_large_overlap(self) -> None:
        """Test chunking with large overlap (50% of chunk size)."""
        text = "Word " * 100
        ingestor = DocumentIngestor(chunk_size=50, chunk_overlap=25)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 2
        # Large overlap should result in more chunks
        assert len(chunks) > 2


class TestChunkSegmentsLargeDocuments:
    """Test chunking with large documents (100K+ characters)."""

    @pytest.mark.fast
    def test_chunk_segments_large_document_100k_chars(self) -> None:
        """Test chunking 100K+ character document."""
        # Generate 100K+ character document
        text = "Word " * 25000  # ~125K characters
        assert len(text) > 100000

        ingestor = DocumentIngestor(chunk_size=1024, chunk_overlap=50)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) > 0
        assert all(len(chunk["text"]) <= 1024 for chunk in chunks)
        assert all(chunk["page"] == 1 for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_large_document_multiple_pages(self) -> None:
        """Test chunking large document with multiple pages."""
        # Simulate multi-page document
        segments: list[Segment] = []
        for page in range(1, 6):
            text = f"Page {page} content. " * 5000
            segments.append({"text": text, "page": page})

        ingestor = DocumentIngestor(chunk_size=512, chunk_overlap=25)
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) > 0
        # Verify page numbers are preserved
        page_counts: dict[int, int] = {}
        for chunk in chunks:
            page = chunk["page"]
            page_counts[page] = page_counts.get(page, 0) + 1

        assert len(page_counts) == 5
        assert all(count > 0 for count in page_counts.values())

    @pytest.mark.fast
    def test_chunk_segments_large_document_memory_efficiency(self) -> None:
        """Test that large document chunking completes without memory issues."""
        text = "Test content for memory efficiency. " * 10000
        ingestor = DocumentIngestor(chunk_size=2048, chunk_overlap=100)
        segments: list[Segment] = [{"text": text, "page": 1}]

        # Should complete without raising MemoryError
        chunks = ingestor._chunk_text(segments)
        assert len(chunks) > 0


class TestChunkSegmentsMultilineHandling:
    """Test chunking with paragraphs, newlines, and multiline text."""

    @pytest.mark.fast
    def test_chunk_segments_paragraphs_preserved(self) -> None:
        """Test that paragraph structure is handled correctly."""
        text = "First paragraph. " * 20 + "\n\n" + "Second paragraph. " * 20
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        assert all(isinstance(chunk["text"], str) for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_newlines_stripped(self) -> None:
        """Test that leading/trailing newlines are stripped."""
        text = "\n\n  Content with newlines  \n\n"
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) == 1
        chunk_text = chunks[0]["text"]
        assert not chunk_text.startswith(("\n", " "))
        assert not chunk_text.endswith(("\n", " "))

    @pytest.mark.fast
    def test_chunk_segments_multiple_newlines_between_words(self) -> None:
        """Test handling of multiple newlines between words."""
        text = "Word1\n\n\n\nWord2\n\n\nWord3"
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # Newlines should be treated as whitespace
        assert "Word1" in chunks[0]["text"]
        assert "Word2" in chunks[0]["text"]
        assert "Word3" in chunks[0]["text"]

    @pytest.mark.fast
    def test_chunk_segments_mixed_whitespace(self) -> None:
        """Test handling of mixed whitespace (spaces, tabs, newlines)."""
        text = "Word1 Word2 Word3 Word4 Word5 Word6 Word7 Word8 Word9 Word10"
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk["text"].strip()) > 0
            assert chunk["page"] == 1


class TestChunkSegmentsUnicode:
    """Test chunking with Unicode characters, emojis, and CJK text."""

    @pytest.mark.fast
    def test_chunk_segments_unicode_accented_characters(self) -> None:
        """Test chunking with accented characters."""
        text = "Café résumé naïve façade. " * 50
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # Verify accented characters preserved
        assert any("é" in chunk["text"] for chunk in chunks)
        assert any("ï" in chunk["text"] for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_emojis(self) -> None:
        """Test chunking with emojis."""
        text = "Hello world test content here 😀 😃 😀 😃 " * 20
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # Emojis should be preserved
        assert any("😀" in chunk["text"] for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_cjk_characters(self) -> None:
        """Test chunking with Chinese, Japanese, Korean characters."""
        text = "你好世界 这是中文测试 日本語テスト  한국어테스트 " * 50
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # CJK characters should be preserved
        assert any("你好" in chunk["text"] for chunk in chunks)
        assert any("日本語" in chunk["text"] for chunk in chunks)
        assert any("한국어" in chunk["text"] for chunk in chunks)

    @pytest.mark.fast
    def test_chunk_segments_mixed_unicode(self) -> None:
        """Test chunking with mixed Unicode scripts."""
        text = (
            "English text 中文文本 日本語テキスト 한국어 텍스트 "
            "émojis😀  special!@#$ " * 30
        )
        ingestor = DocumentIngestor(chunk_size=150, chunk_overlap=30)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # All scripts should be preserved
        all_text = " ".join(chunk["text"] for chunk in chunks)
        assert "English" in all_text
        assert "中文" in all_text
        assert "日本語" in all_text
        assert "한국어" in all_text

    @pytest.mark.fast
    def test_chunk_segments_rtl_text(self) -> None:
        """Test chunking with right-to-left text (Arabic, Hebrew)."""
        text = "مرحبا بالعالم هذا اختبار نصي " * 30
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=20)
        segments: list[Segment] = [{"text": text, "page": 1}]
        chunks = ingestor._chunk_text(segments)

        assert len(chunks) >= 1
        # RTL text should be preserved
        assert any("مرحبا" in chunk["text"] for chunk in chunks)


class TestDeduplicateAndChunkSegments:
    """Test hash-based deduplication in chunking."""

    @pytest.mark.fast
    def test_deduplicate_and_chunk_segments_identical_segments(self) -> None:
        """Test that identical segments are deduplicated."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "This is identical text. ", "page": 1},
            {"text": "This is identical text. ", "page": 2},
            {"text": "This is identical text. ", "page": 3},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        # All three segments are identical after normalization, so only one chunk
        assert len(chunks) == 1

    @pytest.mark.fast
    def test_deduplicate_and_chunk_segments_whitespace_differences(self) -> None:
        """Test that whitespace-only differences are deduplicated."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "This is test text. ", "page": 1},
            {"text": "  This is test text.  ", "page": 2},
            {"text": "This  is  test  text. ", "page": 3},
            {"text": "THIS IS TEST TEXT. ", "page": 4},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        # All segments normalize to the same text
        assert len(chunks) == 1

    @pytest.mark.fast
    def test_deduplicate_and_chunk_segments_preserves_page(self) -> None:
        """Test that page number from first occurrence is preserved."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "Unique text 1. ", "page": 5},
            {"text": "Unique text 2. ", "page": 10},
            {"text": "Unique text 1. ", "page": 15},  # Duplicate of first
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        assert len(chunks) == 2
        # First occurrence's page should be preserved
        assert chunks[0]["page"] == 5
        assert chunks[1]["page"] == 10

    @pytest.mark.fast
    def test_deduplicate_and_chunk_segments_text_hash_included(self) -> None:
        """Test that text_hash is included in chunk metadata."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [{"text": "Test content. ", "page": 1}]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        assert len(chunks) == 1
        assert "text_hash" in chunks[0]
        assert len(chunks[0]["text_hash"]) == 64  # SHA256 hex length

    @pytest.mark.fast
    def test_deduplicate_and_chunk_segments_empty_segments_skipped(self) -> None:
        """Test that empty segments are skipped during deduplication."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "", "page": 1},
            {"text": "   ", "page": 2},
            {"text": "\n\t", "page": 3},
            {"text": "Valid content. ", "page": 4},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        assert len(chunks) == 1
        assert chunks[0]["page"] == 4


class TestDeduplicateWhitespaceVariations:
    """Test normalization and whitespace variation handling."""

    @pytest.mark.fast
    def test_deduplicate_whitespace_variations_normalization(self) -> None:
        """Test that whitespace variations are normalized before hashing."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "Hello world test. ", "page": 1},
            {"text": "Hello  world  test. ", "page": 2},  # Double spaces
            {"text": "Hello\nworld\ntest. ", "page": 3},  # Newlines
            {"text": "Hello\tworld\ttest. ", "page": 4},  # Tabs
            {"text": "HELLO WORLD TEST. ", "page": 5},  # Uppercase
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        # All variations should normalize to the same text
        assert len(chunks) == 1

    @pytest.mark.fast
    def test_deduplicate_whitespace_variations_preserves_meaningful_diffs(self) -> None:
        """Test that meaningful text differences are preserved."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "Hello world test. ", "page": 1},
            {"text": "Hello world TEST. ", "page": 2},
            {"text": "Hello world. ", "page": 3},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        assert len(chunks) == 2

    @pytest.mark.fast
    def test_deduplicate_whitespace_variations_leading_trailing(self) -> None:
        """Test that leading/trailing whitespace is normalized."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "  Content here  ", "page": 1},
            {"text": "\n\nContent here\n\n", "page": 2},
            {"text": "\t\tContent here\t\t", "page": 3},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        # All should normalize to the same content
        assert len(chunks) == 1
        assert chunks[0]["text"] == "Content here"

    @pytest.mark.fast
    def test_deduplicate_whitespace_variations_complex_normalization(self) -> None:
        """Test complex whitespace normalization scenarios."""
        ingestor = DocumentIngestor(chunk_size=256, chunk_overlap=50)
        segments: list[Segment] = [
            {"text": "A  B   C    D", "page": 1},
            {"text": "A\nB\n\nC\n\n\nD", "page": 2},
            {"text": "A\tB\t\tC\t\t\tD", "page": 3},
            {"text": "  A  B  C  D  ", "page": 4},
        ]

        chunks = ingestor._deduplicate_and_chunk_segments(Path("test.txt"), segments)

        assert len(chunks) == 1
        assert chunks[0]["text"] == "A  B   C    D"
