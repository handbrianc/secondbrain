"""Property-based tests for config validation edge cases.

This module tests edge cases in configuration validation using real Hypothesis
strategies to generate diverse inputs.
"""
import pytest
from hypothesis import given, settings, strategies as st, assume

from secondbrain.config import Config


@pytest.mark.hypothesis
class TestConfigValidationEdgeCases:
    """Property-based edge case tests for config validation."""

    @given(
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100)
    def test_valid_chunk_config(self, chunk_size: int, chunk_overlap: int):
        """Valid chunk configs should be accepted."""
        assume(chunk_overlap < chunk_size)
        config = Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        assert config.chunk_size == chunk_size
        assert config.chunk_overlap == chunk_overlap

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_zero_overlap_is_valid(self, chunk_size: int):
        """Zero overlap should be valid."""
        config = Config(chunk_size=chunk_size, chunk_overlap=0)
        assert config.chunk_overlap == 0

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_max_workers_positive(self, workers: int):
        """Positive max_workers should be valid."""
        config = Config(max_workers=workers)
        assert config.max_workers == workers

    @given(st.integers(min_value=-10, max_value=0))
    @settings(max_examples=100)
    def test_invalid_max_workers_rejected(self, workers: int):
        """Non-positive max_workers should be rejected."""
        assume(workers <= 0)
        with pytest.raises(ValueError):
            Config(max_workers=workers)

    @given(
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=100, max_value=1000),
    )
    @settings(max_examples=100)
    def test_embedding_config_valid(self, batch_size: int, dimensions: int):
        """Valid embedding configs should be accepted."""
        config = Config(embedding_batch_size=batch_size, embedding_dimensions=dimensions)
        assert config.embedding_batch_size == batch_size
        assert config.embedding_dimensions == dimensions

    @given(st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_context_window_positive(self, window: int):
        """Positive context window should be valid."""
        assume(window > 0)
        config = Config(rag_context_window=window)
        assert config.rag_context_window == window

    @given(st.floats(min_value=0.0, max_value=2.0))
    @settings(max_examples=100)
    def test_temperature_in_range(self, temp: float):
        """Temperature in valid range should be accepted."""
        assume(0.0 <= temp <= 2.0)
        config = Config(llm_temperature=temp)
        assert config.llm_temperature == temp

    @given(st.floats(min_value=-10.0, max_value=-0.1))
    @settings(max_examples=100)
    def test_invalid_temperature_rejected(self, temp: float):
        """Negative temperature should be rejected."""
        assume(temp < 0)
        with pytest.raises(ValueError):
            Config(llm_temperature=temp)
