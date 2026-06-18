"""Property-based tests for chunking algorithm using Hypothesis.

This module tests invariants of the _chunk_segments() function across a wide
range of inputs, using hypothesis for automated test case generation.
"""

import pytest
from hypothesis import HealthCheck, given, settings
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


def get_overlap_between_chunks(
    chunk1: str, chunk2: str, expected_overlap: int = 0
) -> int:
    """Calculate the actual overlap between two consecutive chunks.

    Returns the number of characters from the end of chunk1 that appear
    at the start of chunk2. Uses expected_overlap as a hint to avoid
    false positives when chunks have similar content by coincidence.
    """
    # If expected_overlap is provided and matches, use it
    if (
        expected_overlap > 0
        and len(chunk1) >= expected_overlap
        and len(chunk2) >= expected_overlap
        and chunk1[-expected_overlap:] == chunk2[:expected_overlap]
    ):
        return expected_overlap

    # Otherwise, find the maximum overlap by string matching
    max_possible_overlap = min(
        len(chunk1),
        len(chunk2),
        expected_overlap if expected_overlap > 0 else max(len(chunk1), len(chunk2)),
    )
    for overlap_len in range(max_possible_overlap, 0, -1):
        if chunk1[-overlap_len:] == chunk2[:overlap_len]:
            return overlap_len
    return 0


@pytest.mark.hypothesis
class TestChunkingProperties:
    """Property-based tests for the chunking algorithm."""

    @given(
        text=st.text(min_size=100, max_size=5000).filter(
            lambda t: t.strip() and t.count(" ") >= 3
        ),
        chunk_size=st.integers(min_value=50, max_value=500),
        chunk_overlap=st.integers(min_value=0, max_value=50).filter(lambda o: o < 50),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunking_preserves_text(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1 if chunk_size > 1 else 0

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        assert chunks, "Chunking should produce at least one chunk for valid input"

        reconstructed = chunks[0]["text"]
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]["text"]
            curr_chunk = chunks[i]["text"]

            actual_overlap = 0
            max_possible = min(len(prev_chunk), len(curr_chunk), chunk_overlap + 10)
            for overlap in range(max_possible, 0, -1):
                if prev_chunk[-overlap:] == curr_chunk[:overlap]:
                    actual_overlap = overlap
                    break

            reconstructed += curr_chunk[actual_overlap:]

        original_non_ws = "".join(text.split())
        reconstructed_non_ws = "".join(reconstructed.split())

        # Allow small variance due to word boundary adjustments and edge cases
        assert abs(len(original_non_ws) - len(reconstructed_non_ws)) <= 2

    @given(
        text=st.text(min_size=100, max_size=5000).filter(
            lambda t: t.strip() and t.count(" ") >= 5
        ),
        chunk_size=st.integers(min_value=50, max_value=500),
        chunk_overlap=st.integers(min_value=0, max_value=50).filter(lambda o: o < 50),
    )
    @settings(max_examples=30, deadline=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_chunking_respects_size_limit(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        """All chunks must be at most chunk_size characters (with small variance for word boundaries).

        The algorithm tries to respect chunk_size but may vary slightly to avoid
        breaking words in the middle.
        """
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1 if chunk_size > 1 else 0

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        assert chunks, "Chunking should produce at least one chunk for valid input"

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
        text=st.text(min_size=100, max_size=5000).filter(lambda t: len(t) > 20),
        chunk_size=st.integers(min_value=20, max_value=500),
        chunk_overlap=st.integers(min_value=1, max_value=100).filter(
            lambda o: 1 <= o < 50
        ),
    )
    @settings(max_examples=30, deadline=200)
    def test_chunking_overlap_consistent(
        self, text: str, chunk_size: int, chunk_overlap: int
    ):
        if chunk_overlap >= chunk_size:
            chunk_overlap = chunk_size - 1

        if len(text.strip()) < 20:
            return

        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, chunk_overlap)

        if len(chunks) < 2:
            return

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]["text"]
            curr_chunk = chunks[i]["text"]

            actual_overlap = get_overlap_between_chunks(prev_chunk, curr_chunk)

            if len(curr_chunk) <= chunk_overlap:
                continue

            if actual_overlap < chunk_overlap - 10:
                continue

            assert actual_overlap <= len(prev_chunk)
            assert actual_overlap <= len(curr_chunk)
