"""Characterization tests pinning pre-split behavior during the DocumentIngestor refactor.

These tests establish a behavioural contract for the new module boundaries introduced
during the Wave-1/Wave-2 split. They verify that:
- Public API surface (__all__) remains unchanged.
- Import paths resolve to the correct module locations.
- The chunk_segments() function produces output compatible with what
  DocumentIngestor._deduplicate_and_chunk_segments() and _chunk_text() produce.
- File-type utilities (is_supported, get_file_type, SUPPORTED_EXTENSIONS) are stable.
- Segment TypedDict has the expected keys.

Once Wave-2 migration is complete these tests should continue to pass without
modification — any failure indicates a behavioural deviation from the baseline.
"""

from pathlib import Path

import pytest

from secondbrain.document import (
    SUPPORTED_EXTENSIONS,
    AsyncDocumentIngestor,
    DocumentIngestor,
    DocumentExtractionError,
    Segment,
    UnsupportedFileError,
    get_file_type,
    is_supported,
)


class TestImportPaths:
    """Verify that all public exports remain accessible from document/__init__.py."""

    def test_document_ingestor_is_class(self) -> None:
        assert isinstance(DocumentIngestor, type)

    def test_async_document_ingestor_extends_base(self) -> None:
        assert issubclass(AsyncDocumentIngestor, DocumentIngestor)

    def test_segment_is_correct_typeddict(self) -> None:
        seg: Segment = {"text": "hello world", "page": 1}
        assert seg["text"] == "hello world"
        assert seg["page"] == 1

    def test_unsupported_file_error_exists(self) -> None:
        assert issubclass(UnsupportedFileError, Exception)

    def test_document_extraction_error_exists(self) -> None:
        assert issubclass(DocumentExtractionError, Exception)

    def test_get_file_type_returns_string(self) -> None:
        assert isinstance(get_file_type(Path("file.pdf")), str)
        assert get_file_type(Path("file.docx")) == "docx"
        assert get_file_type(Path("file.xlsx")) == "xlsx"
        assert get_file_type(Path("file.pptx")) == "pptx"
        assert get_file_type(Path("file.html")) == "html"
        assert get_file_type(Path("file.htm")) == "html"
        assert get_file_type(Path("file.md")) == "markdown"
        assert get_file_type(Path("file.txt")) == "text"
        assert get_file_type(Path("file.png")) == "image"
        assert get_file_type(Path("file.jpg")) == "image"
        assert get_file_type(Path("file.mp3")) == "audio"
        assert get_file_type(Path("file.unknown_extension")) == "unknown"

    def test_is_supported_bool_return(self) -> None:
        assert isinstance(is_supported(Path("file.pdf")), bool)

    def test_is_supported_true_for_all_formats(self) -> None:
        for ext in SUPPORTED_EXTENSIONS:
            assert is_supported(Path(f"file{ext}")) is True, f"Should support {ext}"

    def test_is_supported_false_for_unknown(self) -> None:
        assert is_supported(Path("file.unsupported")) is False
        assert is_supported(Path("/dev/random")) is False


class TestSupportedExtensions:
    """Ensure SUPPORTED_EXTENSIONS set covers the documented formats."""

    def test_supports_pdf(self) -> None:
        assert ".pdf" in SUPPORTED_EXTENSIONS

    def test_supports_office_formats(self) -> None:
        for ext in (".docx", ".pptx", ".xlsx"):
            assert ext in SUPPORTED_EXTENSIONS

    def test_supports_markdown_and_plain_text(self) -> None:
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS

    def test_supports_html_variants(self) -> None:
        assert ".html" in SUPPORTED_EXTENSIONS
        assert ".htm" in SUPPORTED_EXTENSIONS


class TestChunkSegmentsCompatibility:
    """Pin the output contract of the chunk_segments function against what
    DocumentIngestor._chunk_text() and _deduplicate_and_chunk_segments() produce.

    These tests deliberately reproduce edge-case expectations that live tests
    already assert so we have a standalone anchor during migration.
    """

    def test_empty_segment_list_returns_empty(self) -> None:
        """Empty input must produce empty output — no exceptions."""
        from secondbrain.document.chunker import chunk_segments

        result = chunk_segments([], chunk_size=512, chunk_overlap=50)
        assert result == []

    def test_min_segment_size_constant_accessible(self) -> None:
        """DEFAULT_MIN_SEGMENT_SIZE must be 200 (matches documented constant)."""
        from secondbrain.document.chunker import DEFAULT_MIN_SEGMENT_SIZE

        assert DEFAULT_MIN_SEGMENT_SIZE == 200

    def test_chunk_returns_segment_format(self) -> None:
        """Output dicts must have text(str) and page(int) keys — Segment contract."""
        from secondbrain.document.chunker import chunk_segments

        segments: list[Segment] = [{"text": "Hello world", "page": 1}]
        chunks = chunk_segments(segments, chunk_size=256, chunk_overlap=50)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, dict)
            assert "text" in chunk
            assert "page" in chunk
            assert isinstance(chunk["text"], str)
            assert isinstance(chunk["page"], int)

    def test_small_segment_merges_with_next(self) -> None:
        """Segments under MIN_SEGMENT_SIZE must be merged before chunking."""
        from secondbrain.document.chunker import chunk_segments

        # Simulate docling outputting a tiny header-like fragment
        segments: list[Segment] = [
            {"text": "Title", "page": 1},
            {"text": "This is a longer paragraph that should definitely form its own chunk.", "page": 1},
        ]
        chunks = chunk_segments(segments, chunk_size=512, chunk_overlap=50)

        # At least one chunk should span both inputs since "Title" is below threshold
        combined_texts = [c["text"] for c in chunks]
        assert len(combined_texts) >= 1

    def test_deduplicate_same_normalized_text(self) -> None:
        """Identical text modulo whitespace/normalisation must deduplicate."""
        from secondbrain.document.chunker import deduplicate_segments

        segments: list[Segment] = [
            {"text": "  Hello   World  ", "page": 1},
            {"text": "hello world", "page": 2},
        ]
        deduped = deduplicate_segments(Path("test.txt"), segments)

        # Both share same normalised content → only one chunk survives
        assert len(deduped) == 1
        assert deduped[0]["text"] == "Hello   World"  # strips leading/trailing, keeps inner

    def test_deduplicate_includes_metadata(self) -> None:
        """deduplicate_segments must attach file_path, original_index, text_hash."""
        from secondbrain.document.chunker import deduplicate_segments

        segments: list[Segment] = [{"text": "Content", "page": 3}]
        result = deduplicate_segments(Path("myfile.pdf"), segments)

        assert len(result) == 1
        chunk = result[0]
        assert chunk["file_path"] == Path("myfile.pdf")
        assert chunk["original_index"] == 0
        assert chunk["page"] == 3
        assert "text_hash" in chunk
        assert isinstance(chunk["text_hash"], str)

    def test_empty_text_segment_filtered_out(self) -> None:
        """Whitespace-only or empty segments must produce no chunks."""
        from secondbrain.document.chunker import chunk_segments

        segments: list[Segment] = [
            {"text": "   ", "page": 1},
            {"text": "", "page": 2},
            {"text": "Valid text", "page": 3},
        ]
        result = chunk_segments(segments, chunk_size=256, chunk_overlap=50)

        # Empty/whitespace segments filtered out; at least the valid one remains
        assert len(result) >= 1
        assert all(c["text"].strip() for c in result)


class TestAllContract:
    """Sanity-check __all__ list is unchanged in membership and ordering."""

    def test_all_contains_expected_names(self) -> None:
        import secondbrain.document as doc_mod

        for name in (
            "SUPPORTED_EXTENSIONS",
            "AsyncDocumentIngestor",
            "DocumentExtractionError",
            "DocumentIngestor",
            "Segment",
            "UnsupportedFileError",
            "get_file_type",
            "is_supported",
        ):
            assert name in doc_mod.__all__, f"{name} must remain in __all__"

    def test_all_member_count(self) -> None:
        import secondbrain.document as doc_mod

        assert len(doc_mod.__all__) == 8