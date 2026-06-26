"""Unit tests for make_embedding_vector factory function.

These tests verify that the factory correctly validates embedding vector
dimensions against config.embedding_dimensions at runtime.
"""

import pytest

from secondbrain.config import Config
from secondbrain.domain.value_objects import make_embedding_vector


@pytest.fixture
def default_config() -> Config:
    """Default config loader - ensures .env.test is loaded with embedding_dimensions=384."""
    # Accessing Config() triggers env loading via model_validator
    return Config()


class TestMakeEmbeddingVectorValid:
    """Tests for make_embedding_vector with valid inputs."""

    def test_make_embedding_vector_valid(self, default_config: Config) -> None:
        """Test that valid dimension (384) is accepted without error.

        Default embedding_dimensions=384. Vector of 384 floats should succeed.
        """
        vector = make_embedding_vector([0.1] * 384)
        assert len(vector) == 384
        assert isinstance(vector, list)

    def test_make_embedding_vector_correct_every_element(self, default_config: Config) -> None:
        """Test that all elements are preserved unchanged."""
        vals = [float(i) / 384 for i in range(384)]
        vector = make_embedding_vector(vals)
        assert len(vector) == 384
        for i, v in enumerate(vector):
            assert abs(v - (float(i) / 384)) < 1e-6


class TestMakeEmbeddingVectorInvalid:
    """Tests for make_embedding_vector with invalid dimensions."""

    def test_make_embedding_vector_wrong_dimension(self, default_config: Config) -> None:
        """Test that wrong dimension (999) raises ValueError with message.

        Expected message should indicate got 999, expected 384.
        """
        with pytest.raises(ValueError, match=r"got 999.*expected 384"):
            make_embedding_vector([0.1] * 999)

    def test_make_embedding_vector_empty(self, default_config: Config) -> None:
        """Test that empty list raises ValueError with cannot be empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            make_embedding_vector([])

    def test_make_embedding_vector_boundary_383(self, default_config: Config) -> None:
        """Test that 383 dims (one less than 384) raises ValueError."""
        with pytest.raises(ValueError, match=r"got 383.*expected 384"):
            make_embedding_vector([0.1] * 383)

    def test_make_embedding_vector_boundary_385(self, default_config: Config) -> None:
        """Test that 385 dims (one more than 384) raises ValueError."""
        with pytest.raises(ValueError, match=r"got 385.*expected 384"):
            make_embedding_vector([0.1] * 385)

    def test_make_embedding_vector_integer_raises_type_error(self, default_config: Config) -> None:
        """Test that integer input raises TypeError because int is not iterable.

        Passing an integer directly (not wrapped in a list) triggers TypeError
        when make_embedding_vector tries to call list() on it.
        """
        with pytest.raises(TypeError):
            make_embedding_vector(42)  # type: ignore

    def test_make_embedding_vector_none_raises_type_error(self, default_config: Config) -> None:
        """Test that None input raises ValueError."""
        with pytest.raises((TypeError, ValueError)):
            make_embedding_vector(None)