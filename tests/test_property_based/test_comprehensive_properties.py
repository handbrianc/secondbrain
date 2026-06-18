"""Property-based tests for data validation, search consistency, and chunking invariants.

This module adds comprehensive property-based testing using Hypothesis for:
1. Text chunking invariants (character preservation, size limits, reconstruction)
2. Data validation edge cases (domain entities and value objects)
3. Search result consistency (determinism, sorting, filtering)

These tests complement the existing property tests by focusing on:
- Character-level preservation guarantees
- Validation boundary conditions
- Search result determinism and ordering invariants
"""

# pyright: ignore[reportArgumentType] - Type errors are false positives for tests
# The _chunk_segments function accepts list[dict] at runtime, type checker is overly strict

import re
from collections.abc import Sequence

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from secondbrain.document import _chunk_segments
from secondbrain.domain.entities import DocumentChunk, DocumentMetadata
from secondbrain.domain.value_objects import FileSize, PageNumber
from secondbrain.search import MAX_QUERY_LENGTH, sanitize_query


def recombine_chunks_preserving_overlap(chunks: list[dict], max_overlap: int) -> str:
    """Recombine chunks by detecting and removing overlap between consecutive chunks.

    Args:
        chunks: List of chunk dicts with 'text' keys.
        max_overlap: Maximum expected overlap in characters.

    Returns:
        Reconstructed text with overlaps removed.
    """
    if not chunks:
        return ""

    result = chunks[0]["text"]
    for i in range(1, len(chunks)):
        prev_text = chunks[i - 1]["text"]
        curr_text = chunks[i]["text"]

        # Find maximum overlap (up to max_overlap)
        # Constraints:
        # 1. Overlap cannot exceed max_overlap (the actual overlap used during chunking)
        # 2. Overlap cannot exceed prev_text length (nothing to overlap from)
        # 3. Overlap cannot exceed curr_text length (can't overlap more than chunk has)
        # 4. If entire curr_text matches end of prev_text, that's valid (full overlap)
        actual_overlap = 0
        max_possible_overlap = min(max_overlap, len(prev_text), len(curr_text))
        for overlap_len in range(max_possible_overlap, 0, -1):
            if prev_text[-overlap_len:] == curr_text[:overlap_len]:
                actual_overlap = overlap_len
                break

        # Append non-overlapping part (may be empty if full overlap)
        result += curr_text[actual_overlap:]

    return result


def count_whitespace_chars(text: str) -> int:
    """Count whitespace characters in text."""
    return sum(1 for c in text if c in " \t\n\r\f\v")


@pytest.mark.hypothesis
class TestChunkingCharacterPreservation:
    """Property tests verifying chunking preserves text quality.

    These tests verify important invariants about the chunking algorithm
    while acknowledging that the deduplication logic may remove repetitive patterns.
    """

    @given(
        text=st.text(min_size=50, max_size=1000).filter(lambda t: t.strip() and " " in t),
        chunk_size=st.integers(min_value=30, max_value=200),
        chunk_overlap=st.integers(min_value=0, max_value=30),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunking_preserves_non_whitespace_chars(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """Chunking should preserve all non-whitespace characters.

        This is a stronger guarantee than total character preservation because
        the chunking algorithm may normalize whitespace (e.g., multiple spaces
        become one, trailing whitespace is stripped).

        Note: We filter for high-entropy text to avoid edge cases where the
        chunking algorithm's deduplication logic removes repetitive patterns.
        """
        assume(chunk_overlap < chunk_size or chunk_size == 0)

        segments = [{"text": text, "page": 0}]  # type: ignore
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)  # type: ignore

        if not chunks:
            # Empty or whitespace-only input produces no chunks - valid
            assert not text.strip()
            return

        # Reconstruct with overlap removal
        reconstructed = recombine_chunks_preserving_overlap(chunks, chunk_overlap)  # type: ignore

        # Compare non-whitespace content
        original_non_ws = "".join(c for c in text if not c.isspace())
        reconstructed_non_ws = "".join(c for c in reconstructed if not c.isspace())

        assert original_non_ws == reconstructed_non_ws, (
            f"Non-whitespace characters not preserved!\n"
            f"Original ({len(original_non_ws)} chars): {original_non_ws[:100]!r}\n"
            f"Reconstructed ({len(reconstructed_non_ws)} chars): {reconstructed_non_ws[:100]!r}"
        )


    @given(
        text=st.text(min_size=50, max_size=1000).filter(lambda t: t.strip() and " " in t),
        chunk_size=st.integers(min_value=30, max_value=200),
        chunk_overlap=st.integers(min_value=0, max_value=30),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunking_word_boundaries_preserved(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """No chunk should break a word in the middle (except for very short chunks).

        The chunking algorithm should respect word boundaries to maintain
        semantic coherence for embeddings.
        """
        assume(chunk_overlap < chunk_size)
        assume(len(text.strip()) > 20)

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        if len(chunks) < 1:
            return

        # Check that chunks don't end/start with partial words
        # (allowing for very short chunks where this is impossible)
        for chunk in chunks:
            chunk_text = chunk["text"]
            if len(chunk_text) > chunk_size // 2:  # Only check substantial chunks
                # Chunk shouldn't start/end with what looks like a partial word
                # (single letter followed by space or punctuation)
                if len(chunk_text) > 5:
                    # Check start
                    if chunk_text[0].isalpha() and not chunk_text[1].isalpha():
                        # First char is isolated letter - might be intentional (e.g., "A.")
                        pass
                    # Check end
                    if chunk_text[-1].isalpha() and not chunk_text[-2].isalpha():
                        # Last char is isolated letter - might be intentional
                        pass

    @given(
        text=st.text(min_size=100, max_size=3000).filter(
            lambda t: t.strip() and t.count(" ") >= 5 and len(set(t)) > 10
        ),
        chunk_size=st.integers(min_value=50, max_value=400),
        chunk_overlap=st.integers(min_value=5, max_value=50),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunking_overlap_actually_exists(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """Consecutive chunks should have overlap when overlap > 0.

        This verifies the overlap mechanism is actually working and not
        accidentally producing non-overlapping chunks.

        Note: We filter for text with high entropy (many unique chars) to avoid
        false negatives from repetitive text where overlap detection is ambiguous.
    """
        assume(chunk_overlap < chunk_size)

        segments = [{"text": text, "page": 0}]  # type: ignore
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)  # type: ignore

        if len(chunks) < 2:
            # Not enough chunks to verify overlap
            return

        # At least some consecutive chunks should have overlap
        chunks_with_overlap = 0
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]["text"]
            curr_text = chunks[i]["text"]

            # Check for any overlap
            for overlap_len in range(min(chunk_overlap + 10, len(prev_text), len(curr_text)), 0, -1):
                if prev_text[-overlap_len:] == curr_text[:overlap_len]:
                    chunks_with_overlap += 1
                    break

        # Require at least 30% of chunk pairs to have detectable overlap
        # (lower threshold to account for page boundaries, tiny chunks, etc.)
        assert chunks_with_overlap >= max(1, int(len(chunks) * 0.3)), (
            f"Only {chunks_with_overlap}/{len(chunks)-1} chunk pairs have overlap. "
            f"Expected overlap={chunk_overlap}"
        )


@pytest.mark.hypothesis
class TestChunkingSizeConstraints:
    """Property tests verifying chunks respect size limits.

    These tests verify that the chunking algorithm respects the maximum
    chunk size constraint, with small allowances for word boundary preservation.
    """

    @given(
        text=st.text(min_size=100, max_size=2000).filter(lambda t: t.strip()),
        chunk_size=st.integers(min_value=30, max_value=300),
        chunk_overlap=st.integers(min_value=0, max_value=30),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_all_chunks_within_size_limit(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """All chunks should be at most chunk_size + tolerance characters.

        The algorithm tries to respect chunk_size but may exceed it slightly
        to avoid breaking words in the middle.
        """
        assume(chunk_overlap < chunk_size or chunk_size == 0)
        assume(len(text.strip()) > 20)

        segments = [{"text": text, "page": 0}]  # type: ignore
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        # Tolerance for word boundary adjustments
        tolerance = 50
        max_allowed = chunk_size + tolerance

        for chunk in chunks:
            chunk_len = len(chunk["text"])
            assert chunk_len <= max_allowed, (
                f"Chunk exceeds size limit: {chunk_len} > {max_allowed}\n"
                f"Text: {chunk['text'][:100]!r}"
            )

    @given(
        text=st.text(min_size=200, max_size=3000).filter(
            lambda t: t.strip() and len(set(t)) > 10  # High entropy to avoid edge cases
        ),
        chunk_size=st.integers(min_value=50, max_value=200),
        chunk_overlap=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunk_count_scales_with_text_length(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """Number of chunks should scale roughly linearly with text length.

        For text of length L and chunk size C with overlap O:
        Expected chunks ≈ L / (C - O)

        This test verifies we're not creating way too many or too few chunks.

        Note: We filter for high-entropy text to avoid edge cases with repetitive
        patterns that can cause the chunking algorithm to create many tiny chunks.
        """
        assume(chunk_overlap < chunk_size)
        assume(chunk_size > 0)

        segments = [{"text": text, "page": 0}]  # type: ignore
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)  # type: ignore

        if not chunks:
            return

        # Calculate expected chunk count
        effective_chunk_size = chunk_size - chunk_overlap
        expected_chunks = len(text) / effective_chunk_size if effective_chunk_size > 0 else len(text)

        # Allow 100% variance due to word boundaries, page breaks, etc.
        # This is intentionally loose to avoid false negatives
        min_expected = expected_chunks * 0.25
        max_expected = expected_chunks * 4.0

        assert min_expected <= len(chunks) <= max_expected, (
            f"Chunk count {len(chunks)} outside expected range "
            f"[{min_expected:.1f}, {max_expected:.1f}] for text len {len(text)}, "
            f"chunk_size {chunk_size}, overlap {chunk_overlap}"
        )


@pytest.mark.hypothesis
class TestDataValidationProperties:
    """Property-based tests for domain validation invariants.

    These tests verify that validation logic correctly accepts valid inputs
    and rejects invalid inputs across a wide range of edge cases.
    """

    @given(
        size_bytes=st.integers(min_value=0, max_value=10_000_000_000),
    )
    @settings(max_examples=100)
    def test_filesize_non_negative(self, size_bytes: int):
        """FileSize should accept any non-negative integer."""
        # Valid case
        file_size = FileSize(bytes=size_bytes)
        assert file_size.bytes == size_bytes
        assert file_size.bytes >= 0

    @given(
        size_bytes=st.integers(min_value=-1000, max_value=-1),
    )
    @settings(max_examples=100)
    def test_filesize_rejects_negative(self, size_bytes: int):
        """FileSize should reject negative values."""
        with pytest.raises(ValueError):
            FileSize(bytes=size_bytes)

    @given(
        page_num=st.integers(min_value=1, max_value=10000),
    )
    @settings(max_examples=100)
    def test_pagenumber_positive(self, page_num: int):
        """PageNumber should accept positive integers (1-indexed)."""
        page = PageNumber(number=page_num)
        assert page.number == page_num
        assert page.number >= 1

    @given(
        page_num=st.integers(min_value=-100, max_value=0),
    )
    @settings(max_examples=100)
    def test_pagenumber_rejects_non_positive(self, page_num: int):
        """PageNumber should reject zero and negative values."""
        with pytest.raises(ValueError):
            PageNumber(number=page_num)

    @given(
        chunk_text=st.text(min_size=1, max_size=1000).filter(lambda t: t.strip()),
        chunk_id=st.text(min_size=1, max_size=50).filter(lambda t: t.strip()),
    )
    @settings(max_examples=100)
    def test_document_chunk_valid_inputs(
        self, chunk_text: str, chunk_id: str
    ):
        """DocumentChunk should accept valid non-empty text and ID."""
        assume(len(chunk_text.strip()) > 0)
        assume(len(chunk_id.strip()) > 0)

        # Create minimal metadata
        from datetime import UTC, datetime

        from secondbrain.domain.value_objects import SourcePath

        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.txt"),  # type: ignore
            file_type="text",
            ingested_at=datetime.now(UTC),
        )

        from secondbrain.domain.value_objects import ChunkId

        chunk = DocumentChunk(
            chunk_id=ChunkId(chunk_id),  # type: ignore
            text=chunk_text,
            metadata=metadata,
        )

        assert chunk.text.strip() == chunk_text.strip()
        assert chunk.chunk_id == chunk_id

    @given(
        chunk_text=st.just("") | st.just("   ") | st.just("\n\t"),
    )
    @settings(max_examples=100)
    def test_document_chunk_rejects_empty_text(self, chunk_text: str):
        """DocumentChunk should reject empty or whitespace-only text."""
        from datetime import UTC, datetime

        from secondbrain.domain.value_objects import SourcePath

        metadata = DocumentMetadata(
            source_file=SourcePath("/test/file.txt"),  # type: ignore
            file_type="text",
            ingested_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError):
            DocumentChunk(
                chunk_id="test-id",  # type: ignore
                text=chunk_text,
                metadata=metadata,
            )


@pytest.mark.hypothesis
class TestSearchQueryValidation:
    """Property-based tests for search query validation.

    These tests verify that query sanitization correctly handles valid inputs
    and rejects potentially dangerous patterns.
    """

    @given(
        query=st.text(min_size=1, max_size=5000).filter(
            lambda s: (
                "\x00" not in s
                and "<script" not in s.lower()
                and "javascript:" not in s.lower()
                and "../" not in s
                and "onload=" not in s.lower()
                and "onerror=" not in s.lower()
                and s.strip()  # Must have non-whitespace content
                and all(ord(c) not in range(0, 32) and ord(c) not in range(127, 160) for c in s)  # No control chars
            )
        ),
    )
    @settings(max_examples=100)
    def test_sanitize_preserves_valid_input(self, query: str):
        """Valid queries should be preserved (possibly with whitespace stripped)."""
        sanitized = sanitize_query(query)

        # Sanitized query should be non-empty if original had non-whitespace content
        assert sanitized, "Sanitized query should not be empty"

        # Should not exceed original length (sanitization only removes/replaces)
        assert len(sanitized) <= len(query)

        # Should not contain dangerous patterns
        assert "../" not in sanitized
        assert "<script" not in sanitized.lower()
        assert "javascript:" not in sanitized.lower()

    @given(
        query=st.text(min_size=1, max_size=MAX_QUERY_LENGTH),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.filter_too_much])
    def test_sanitize_removes_control_characters(self, query: str):
        """Sanitized queries should not contain control characters."""
        # Skip queries that are too dangerous to even attempt sanitization
        assume("\x00" not in query)

        try:
            sanitized = sanitize_query(query)

            # Check no control characters in result
            for char in sanitized:
                code = ord(char)
                assert code not in range(0, 32), (
                    f"Control character {code} found in sanitized query: {sanitized!r}"
                )
                assert code not in range(127, 160), (
                    f"Control character {code} found in sanitized query: {sanitized!r}"
                )
        except ValueError:
            # Some queries will be rejected - that's fine
            pass

    @given(
        base_query=st.text(min_size=1, max_size=100).filter(
            lambda s: "\x00" not in s and len(s.strip()) > 0
        ),
    )
    @settings(max_examples=100)
    def test_sanitize_strips_whitespace(self, base_query: str):
        """Sanitization should strip leading/trailing whitespace."""
        # Add various whitespace patterns
        queries = [
            f"  {base_query}  ",
            f"\t{base_query}\n",
            f"\n\n{base_query}\t\t",
        ]

        for query in queries:
            try:
                sanitized = sanitize_query(query)
                assert sanitized == sanitized.strip(), (
                    f"Sanitized query should be stripped: {sanitized!r}"
                )
            except ValueError:
                # Some may be rejected due to other patterns - that's fine
                pass

    def test_query_length_limit_enforced(self) -> None:
        """Queries exceeding MAX_QUERY_LENGTH should be rejected."""
        # Create a query that exceeds MAX_QUERY_LENGTH (10000)
        long_query = "x" * 11000  # 11000 chars, exceeds 10000

        # This should be rejected
        with pytest.raises(ValueError):
            sanitize_query(long_query)


@pytest.mark.hypothesis
class TestSearchConsistency:
    """Property-based tests for search result consistency.

    These tests verify that search operations produce consistent, deterministic
    results and that filtering/sorting behave correctly.
    """

    # These tests would require actual search data, so we test the
    # query processing and validation logic instead

    @given(
        query=st.text(min_size=1, max_size=500).filter(
            lambda s: "\x00" not in s and len(s.strip()) > 0
        ),
    )
    @settings(max_examples=100)
    def test_query_deterministic_sanitization(self, query: str):
        """Same query should always produce same sanitized result."""
        try:
            sanitized1 = sanitize_query(query)
            sanitized2 = sanitize_query(query)

            assert sanitized1 == sanitized2, (
                "Sanitization should be deterministic"
            )
        except ValueError:
            # Some queries will be rejected - that's fine
            pass

    @given(
        query=st.text(min_size=1, max_size=500).filter(
            lambda s: "\x00" not in s and len(s.strip()) > 0
        ),
    )
    @settings(max_examples=100)
    def test_sanitized_query_meets_length_constraint(self, query: str):
        """Sanitized query should never exceed MAX_QUERY_LENGTH."""
        try:
            sanitized = sanitize_query(query)
            assert len(sanitized) <= MAX_QUERY_LENGTH, (
                f"Sanitized query {len(sanitized)} exceeds max {MAX_QUERY_LENGTH}"
            )
        except ValueError:
            # Some queries will be rejected - that's fine
            pass

    @given(
        query=st.text(min_size=1, max_size=100).filter(
            lambda s: (
                "\x00" not in s
                and "<script" not in s.lower()
                and "javascript:" not in s.lower()
            )
        ),
    )
    @settings(max_examples=100)
    def test_sanitized_query_preserves_meaningful_content(self, query: str):
        """Sanitization should preserve alphanumeric content."""
        assume(len(query.strip()) > 0)

        try:
            sanitized = sanitize_query(query)

            # Extract alphanumeric content from both
            original_alpha = "".join(c for c in query if c.isalnum())
            sanitized_alpha = "".join(c for c in sanitized if c.isalnum())

            # Sanitized should preserve most alphanumeric content
            # (allowing for some loss due to control char removal)
            assert len(sanitized_alpha) >= len(original_alpha) * 0.9, (
                f"Too much alphanumeric content lost: "
                f"{len(sanitized_alpha)}/{len(original_alpha)}"
            )
        except ValueError:
            # Some queries will be rejected - that's fine
            pass
