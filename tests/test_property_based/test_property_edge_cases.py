"""Property-based tests for chunking edge cases and config validation.

Consolidated from:
- test_edge_cases.py: Boundary-condition chunking tests
- test_config_validation_edge_cases.py: Config validation property tests
"""

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from secondbrain.config import Config
from secondbrain.document import _chunk_segments


@pytest.mark.hypothesis
class TestChunkingEdgeCases:
    """Boundary-condition tests for _chunk_segments."""

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


@pytest.mark.hypothesis
class TestConfigValidationEdgeCases:
    """Property-based edge case tests for Config validation."""

    @given(
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100)
    def test_valid_chunk_config(self, chunk_size: int, chunk_overlap: int):
        assume(chunk_overlap < chunk_size)
        config = Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        assert config.chunk_size == chunk_size
        assert config.chunk_overlap == chunk_overlap

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_zero_overlap_is_valid(self, chunk_size: int):
        config = Config(chunk_size=chunk_size, chunk_overlap=0)
        assert config.chunk_overlap == 0

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_max_workers_positive(self, workers: int):
        config = Config(max_workers=workers)
        assert config.max_workers == workers

    @given(st.integers(min_value=-10, max_value=0))
    @settings(max_examples=100)
    def test_invalid_max_workers_rejected(self, workers: int):
        assume(workers <= 0)
        with pytest.raises(ValueError):
            Config(max_workers=workers)

    @given(
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=100, max_value=1000),
    )
    @settings(max_examples=100)
    def test_embedding_config_valid(self, batch_size: int, dimensions: int):
        config = Config(
            embedding_batch_size=batch_size, embedding_dimensions=dimensions
        )
        assert config.embedding_batch_size == batch_size
        assert config.embedding_dimensions == dimensions

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_context_window_positive(self, window: int):
        assume(window > 0)
        config = Config(rag_context_window=window)
        assert config.rag_context_window == window

    @given(st.floats(min_value=0.0, max_value=2.0))
    @settings(max_examples=100)
    def test_temperature_in_range(self, temp: float):
        assume(0.0 <= temp <= 2.0)
        config = Config(llm_temperature=temp)
        assert config.llm_temperature == temp

    @given(st.floats(min_value=-10.0, max_value=-0.1))
    @settings(max_examples=100)
    def test_invalid_temperature_rejected(self, temp: float):
        assume(temp < 0)
        with pytest.raises(ValueError):
            Config(llm_temperature=temp)
