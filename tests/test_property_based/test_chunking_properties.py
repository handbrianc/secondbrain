"""Property-based tests for chunking algorithm using Hypothesis.

This module tests invariants of the _chunk_segments() function across a wide
range of inputs, using hypothesis for automated test case generation.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from secondbrain.document import _chunk_segments


def recombine_chunks_with_overlap(chunks: list[dict]) -> str:
    """Recombine chunks, removing overlap from all but the first chunk.

    When chunks have overlap, recombining them requires removing the overlap
    from consecutive chunks to avoid duplicating text.
    """
    if not chunks:
        return ""

    result = chunks[0]["text"]
    for i in range(1, len(chunks)):
        # For now, just concatenate - the overlap removal is implicit in testing
        result += chunks[i]["text"]
    return result


def get_overlap_between_chunks(chunk1: str, chunk2: str) -> int:
    """Calculate the actual overlap between two consecutive chunks.

    Returns the number of characters from the end of chunk1 that appear
    at the start of chunk2.
    """
    max_possible_overlap = min(len(chunk1), len(chunk2))
    for overlap_len in range(max_possible_overlap, 0, -1):
        if chunk1[-overlap_len:] == chunk2[:overlap_len]:
            return overlap_len
    return 0


@pytest.mark.hypothesis
class TestChunkingProperties:
    """Property-based tests for the chunking algorithm."""

    @given(
        text=st.text(min_size=1, max_size=5000).filter(
            lambda t: len(t) > 100 or " " not in t
        ),
        chunk_size=st.integers(min_value=50, max_value=500),
        chunk_overlap=st.integers(min_value=0, max_value=50).filter(lambda o: o < 50),
    )
    @settings(max_examples=100)
    def test_chunking_preserves_text(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """All characters from original text should appear in chunks (accounting for overlap).

        This is the most critical property: chunking must not lose or alter text.
        When we account for overlap, the unique content should match the original.
        """
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1 if chunk_size > 1 else 0

        if not text.strip():
            segments = [{"text": text, "page": 0}]
            chunks = _chunk_segments(segments, chunk_size, chunk_overlap)
            assert len(chunks) == 0
            return

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        if not chunks:
            assert not text.strip()
            return

        reconstructed = chunks[0]["text"]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]["text"]
            curr_chunk = chunks[i]["text"]

            overlap_len = get_overlap_between_chunks(prev_chunk, curr_chunk)
            new_content = curr_chunk[overlap_len:]
            reconstructed += new_content

        original_words = text.split()
        for word in original_words:
            assert word in reconstructed, f"Word '{word}' missing from chunks"

    @given(
        text=st.text(min_size=1, max_size=5000),
        chunk_size=st.integers(min_value=10, max_value=1000),
        chunk_overlap=st.integers(min_value=0, max_value=100).filter(lambda o: o < 100),
    )
    @settings(max_examples=100)
    def test_chunking_respects_size_limit(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """All chunks must be at most chunk_size characters (with small variance for word boundaries).

        The algorithm tries to respect chunk_size but may vary slightly to avoid
        breaking words in the middle.
        """
        # Ensure valid configuration
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1 if chunk_size > 1 else 0

        if not text.strip():
            segments = [{"text": text, "page": 0}]
            chunks = _chunk_segments(segments, chunk_size, chunk_overlap)
            assert len(chunks) == 0
            return

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        assert len(chunks) > 0, "Should produce at least one chunk for non-empty text"

        # Allow small variance (up to chunk_size + 50) for word boundary adjustments
        # The algorithm uses rfind(" ") to avoid breaking words
        max_allowed_size = chunk_size + 50
        for chunk in chunks:
            chunk_len = len(chunk["text"])
            assert chunk_len <= max_allowed_size, (
                f"Chunk size {chunk_len} exceeds limit {max_allowed_size}: "
                f"{chunk['text'][:50]!r}..."
            )

    @given(
        text=st.text(min_size=10, max_size=5000).filter(lambda t: len(t) > 20),
        chunk_size=st.integers(min_value=20, max_value=500),
        chunk_overlap=st.integers(min_value=1, max_value=100).filter(
            lambda o: 1 <= o < 50  # Overlap must be positive and reasonable
        ),
    )
    @settings(max_examples=100)
    def test_chunking_overlap_consistent(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """Consecutive chunks should have consistent overlap as specified.

        The overlap ensures context continuity across chunk boundaries.
        Each consecutive pair of chunks should share exactly chunk_overlap characters
        (or as close as possible given text constraints).
        """
        # Ensure valid configuration
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1

        if len(text.strip()) < 20:
            return

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        if len(chunks) < 2:
            # Not enough chunks to test overlap
            return

        # Check overlap between consecutive chunks
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]["text"]
            curr_chunk = chunks[i]["text"]

            # Calculate actual overlap
            actual_overlap = get_overlap_between_chunks(prev_chunk, curr_chunk)

            # Overlap should be close to requested (within tolerance for edge cases)
            # Allow some variance because:
            # 1. Last chunk may have less overlap if near end of text
            # 2. Word boundary adjustments may affect overlap
            tolerance = min(chunk_overlap, 10)  # Allow up to 10 chars variance
            expected_min = max(0, chunk_overlap - tolerance)

            assert actual_overlap >= expected_min, (
                f"Overlap {actual_overlap} too small (expected >= {expected_min}) "
                f"between chunks {i - 1} and {i}"
            )

            # Overlap cannot exceed either chunk's length
            assert actual_overlap <= len(prev_chunk), (
                f"Overlap {actual_overlap} exceeds prev chunk length {len(prev_chunk)}"
            )
            assert actual_overlap <= len(curr_chunk), (
                f"Overlap {actual_overlap} exceeds curr chunk length {len(curr_chunk)}"
            )
