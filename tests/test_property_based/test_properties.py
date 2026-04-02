"""Property-based tests using hypothesis.

This module tests invariants that should hold across a wide range of inputs,
using hypothesis for automated test case generation.
"""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from secondbrain.config import Config
from secondbrain.search import MAX_QUERY_LENGTH, sanitize_query


@pytest.mark.hypothesis
class TestQuerySanitization:
    """Property tests for query sanitization."""

    @given(
        st.text(min_size=1, max_size=MAX_QUERY_LENGTH).filter(
            lambda s: (
                "\x00" not in s
                and "<script" not in s.lower()
                and "javascript:" not in s.lower()
                and "../" not in s
            )
        )
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.differing_executors])
    def test_sanitize_preserves_valid_input(self, query: str):
        """Sanitization should preserve valid queries."""
        sanitized = sanitize_query(query)
        assert len(sanitized) <= len(query)
        assert "../" not in sanitized
        assert "<script" not in sanitized.lower()
        assert "javascript:" not in sanitized.lower()

    @given(
        st.text(min_size=1, max_size=MAX_QUERY_LENGTH).filter(
            lambda s: (
                "\x00" not in s
                and "<script" not in s.lower()
                and "javascript:" not in s.lower()
                and "../" not in s
            )
        )
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.differing_executors])
    def test_sanitize_removes_control_characters(self, query: str):
        """Sanitization should remove control characters."""
        sanitized = sanitize_query(query)
        for char in sanitized:
            assert ord(char) not in range(0, 32), (
                f"Control char {ord(char)} found in: {sanitized!r}"
            )
            assert ord(char) not in range(127, 160), (
                f"Control char {ord(char)} found in: {sanitized!r}"
            )

    @given(
        st.text(min_size=1, max_size=100).filter(
            lambda s: (
                "\x00" not in s
                and "<script" not in s.lower()
                and "javascript:" not in s.lower()
                and "../" not in s
            )
        )
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.differing_executors])
    def test_sanitize_strips_whitespace(self, query: str):
        """Sanitization should strip leading/trailing whitespace."""
        sanitized = sanitize_query(query)
        assert sanitized == sanitized.strip(), f"Whitespace not stripped: {sanitized!r}"


@pytest.mark.hypothesis
class TestConfigValidation:
    """Property tests for configuration validation."""

    @given(
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=0, max_value=9999),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.differing_executors])
    def test_chunk_size_greater_than_overlap(self, chunk_size: int, chunk_overlap: int):
        """Chunk size must be greater than overlap."""
        from pydantic import ValidationError

        if chunk_overlap >= chunk_size:
            # Should raise validation error
            with pytest.raises(ValidationError):
                Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        else:
            # Should be valid
            config = Config(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
            assert config.chunk_size == chunk_size
            assert config.chunk_overlap == chunk_overlap

    @given(st.integers(min_value=1, max_value=1000))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.differing_executors])
    def test_embedding_dimensions_positive(self, dimensions: int):
        """Embedding dimensions must be positive."""
        config = Config(embedding_dimensions=dimensions)
        assert config.embedding_dimensions > 0

    @given(st.integers(min_value=1, max_value=100))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.differing_executors])
    def test_embedding_batch_size_in_range(self, batch_size: int):
        """Embedding batch size must be 1-100."""
        config = Config(embedding_batch_size=batch_size)
        assert 1 <= config.embedding_batch_size <= 100

    @given(st.integers(min_value=1, max_value=200))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.differing_executors])
    def test_streaming_batch_size_in_range(self, batch_size: int):
        """Streaming chunk batch size must be 1-200."""
        config = Config(streaming_chunk_batch_size=batch_size)
        assert 1 <= config.streaming_chunk_batch_size <= 200
