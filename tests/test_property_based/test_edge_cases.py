"""Property-based tests for edge cases in chunking algorithm.

This module adds edge case coverage to the existing chunking property tests,
testing boundary conditions and unusual inputs.
"""
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from secondbrain.document import _chunk_segments


@pytest.mark.hypothesis
class TestChunkingEdgeCases:

    @given(st.just("A" * 100))
    @settings(max_examples=100)
    def test_single_word_chunking(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=50, chunk_overlap=10)
        assert chunks
        for chunk in chunks:
            assert len(chunk["text"]) <= 60

    @given(st.just("A B C D E"))
    @settings(max_examples=100)
    def test_very_short_text(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=100, chunk_overlap=10)
        assert len(chunks) >= 1

    @given(st.just("A " * 10 + "B " * 10 + "C " * 10))
    @settings(max_examples=100)
    def test_repeated_pattern_chunking(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks
        total_chars = sum(len(c["text"]) for c in chunks)
        assert total_chars >= len(text) - 20

    @given(st.integers(min_value=1, max_value=10).map(lambda n: "Word " * n))
    @settings(max_examples=100)
    def test_variable_length_text(self, text: str):
        assume(len(text.strip()) > 0)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks

    @given(
        st.text(min_size=50, max_size=200).map(lambda s: s + " " + s),
        st.integers(min_value=10, max_value=50),
    )
    @settings(max_examples=100)
    def test_overlap_adjustment(self, text: str, chunk_size: int):
        overlap = min(chunk_size - 1, 10)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, overlap)
        assert chunks

    @given(st.just("Test\n\n\n\nTest"))
    @settings(max_examples=100)
    def test_multiple_newlines_chunking(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks

    @given(st.just("\t\t\tTest\t\t\t"))
    @settings(max_examples=100)
    def test_tab_characters_chunking(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks

    @given(st.just("Test " * 100))
    @settings(max_examples=100)
    def test_very_long_single_line(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=50, chunk_overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["text"]) <= 60

    @given(
        st.integers(min_value=5, max_value=20).map(lambda n: "Word " * n),
        st.integers(min_value=5, max_value=15),
    )
    @settings(max_examples=100)
    def test_small_chunk_size(self, text: str, chunk_size: int):
        assume(len(text.split()) > 0)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, 0)
        assert chunks

    @given(st.just("A" * 1000 + " " + "B" * 1000))
    @settings(max_examples=100)
    def test_very_long_words_chunking(self, text: str):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=100, chunk_overlap=10)
        assert chunks

    @given(
        st.text(min_size=100, max_size=1000).filter(lambda t: " " in t),
        st.integers(min_value=20, max_value=100),
    )
    @settings(max_examples=100)
    def test_zero_overlap_chunking(self, text: str, chunk_size: int):
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, 0)
        assert chunks
        for i in range(1, len(chunks)):
            prev_text = chunks[i - 1]["text"]
            curr_text = chunks[i]["text"]
            assert len(prev_text) > 0 and len(curr_text) > 0

    @given(
        st.text(min_size=100, max_size=1000).filter(lambda t: " " in t),
        st.integers(min_value=50, max_value=100),
        st.integers(min_value=40, max_value=90),
    )
    @settings(max_examples=100)
    def test_large_overlap_chunking(self, text: str, chunk_size: int, overlap: int):
        assume(overlap < chunk_size)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size, overlap)
        assert chunks
        for chunk in chunks:
            assert len(chunk["text"]) <= chunk_size + 20
