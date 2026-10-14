"""Property-based tests for chunking edge cases and config validation.

Consolidated from:
- test_edge_cases.py: Boundary-condition chunking tests
- test_config_validation_edge_cases.py: Config validation property tests
"""

import string

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from secondbrain.config import Config
from secondbrain.document import _chunk_segments

# --- Generative text strategies replacing the former degenerate st.just(X) ---
# inputs (each previously drew the same constant on every example, which made
# the tests parametrized-by-nothing rather than property-based).


def _letters(min_size: int = 1, max_size: int = 10) -> st.SearchStrategy[str]:
    """Non-empty alphabetic words."""
    return st.text(alphabet=string.ascii_letters, min_size=min_size, max_size=max_size)


def _unbroken_word() -> st.SearchStrategy[str]:
    """A single long word of arbitrary length (no whitespace)."""
    return st.integers(min_value=1, max_value=1000).map(lambda n: "A" * n)


def _short_multi_word_text() -> st.SearchStrategy[str]:
    """Whitespace-separated words, lengths crossing the chunk boundary."""
    return st.lists(_letters(max_size=12), min_size=1, max_size=40).map(" ".join)


def _repeated_pattern_text() -> st.SearchStrategy[str]:
    """Variable-length 'A...A B...B C...C' pattern text."""
    return st.integers(min_value=1, max_value=30).map(
        lambda n: "A " * n + "B " * n + "C " * n
    )


def _text_with_newline_runs() -> st.SearchStrategy[str]:
    """Words separated by runs of newlines/other whitespace."""
    separators = st.text(alphabet="\n\t\r ", min_size=1, max_size=8)
    return st.lists(
        st.tuples(_letters(min_size=2), separators), min_size=1, max_size=8
    ).map(lambda pairs: "".join(word + sep for word, sep in pairs))


def _text_with_tab_runs() -> st.SearchStrategy[str]:
    """Words separated by runs of tabs/other whitespace."""
    separators = st.text(alphabet="\t\n\r ", min_size=1, max_size=8)
    return st.lists(
        st.tuples(_letters(min_size=2), separators), min_size=1, max_size=8
    ).map(lambda pairs: "".join(word + sep for word, sep in pairs))


def _long_single_line_text() -> st.SearchStrategy[str]:
    """A long single-line text of 'Test'-repetitions with varying length."""
    return st.integers(min_value=12, max_value=400).map(lambda n: "Test " * n)


def _two_long_words_text() -> st.SearchStrategy[str]:
    """Two long unbroken words separated by exactly one space."""
    return st.tuples(
        st.integers(min_value=1, max_value=1500),
        st.integers(min_value=1, max_value=1500),
    ).map(lambda t: "A" * t[0] + " " + "B" * t[1])


@pytest.mark.hypothesis
class TestChunkingEdgeCases:
    """Boundary-condition tests for _chunk_segments."""

    @given(text=_unbroken_word())
    @settings(max_examples=100)
    def test_single_word_chunking(self, text: str):
        """A single unbroken word of any length splits into bounded chunks."""
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=50, chunk_overlap=10)
        assert chunks
        for chunk in chunks:
            assert len(chunk["text"]) <= 60

    @given(text=_short_multi_word_text())
    @settings(max_examples=100)
    def test_very_short_text(self, text: str):
        """Short multi-word text always yields at least one non-empty chunk."""
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=100, chunk_overlap=10)
        assert len(chunks) >= 1
        assert all(chunk["text"].strip() for chunk in chunks)

    @given(text=_repeated_pattern_text())
    @settings(max_examples=100)
    def test_repeated_pattern_chunking(self, text: str):
        """Chunking an overlapped pattern text loses at most one chunk_size."""
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

    @given(text=_text_with_newline_runs())
    @settings(max_examples=100)
    def test_multiple_newlines_chunking(self, text: str):
        """Any text containing newline runs still chunks non-empty pieces."""
        assume(text.strip())
        assume("\n" in text)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks
        assert all(chunk["text"].strip() for chunk in chunks)

    @given(text=_text_with_tab_runs())
    @settings(max_examples=100)
    def test_tab_characters_chunking(self, text: str):
        """Any text containing tab runs still chunks non-empty pieces."""
        assume(text.strip())
        assume("\t" in text)
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=20, chunk_overlap=5)
        assert chunks
        assert all(chunk["text"].strip() for chunk in chunks)

    @given(text=_long_single_line_text())
    @settings(max_examples=100)
    def test_very_long_single_line(self, text: str):
        """A long single-line text splits into more than one bounded chunk."""
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=50, chunk_overlap=10)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["text"]) <= 60

    @given(text=_two_long_words_text())
    @settings(max_examples=100)
    def test_very_long_words_chunking(self, text: str):
        """Two very long words chunk into pieces bounded by chunk_size."""
        segments = [{"text": text, "page": 0}]
        chunks = _chunk_segments(segments, chunk_size=100, chunk_overlap=10)
        assert chunks
        for chunk in chunks:
            assert len(chunk["text"]) <= 100

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
        with pytest.raises(ValueError, match="max_workers must be positive"):
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
    @settings(max_examples=100, deadline=None)
    def test_temperature_in_range(self, temp: float):
        assume(0.0 <= temp <= 2.0)
        config = Config(llm_temperature=temp)
        assert config.llm_temperature == temp

    @given(st.floats(min_value=-10.0, max_value=-0.1))
    @settings(max_examples=100)
    def test_invalid_temperature_rejected(self, temp: float):
        assume(temp < 0)
        with pytest.raises(ValueError, match="llm_temperature must be between"):
            Config(llm_temperature=temp)

    @given(
        st.integers(min_value=1, max_value=8192),
        st.integers(min_value=1, max_value=8192),
    )
    @settings(max_examples=100, deadline=500)
    def test_chunk_overlap_ge_chunksize_rejected(
        self, chunk_size: int, chunk_overlap: int
    ):
        assume(chunk_overlap >= chunk_size)
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
