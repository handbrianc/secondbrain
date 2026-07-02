"""Unit tests for make_embedding_vector factory function.

These tests verify that the factory correctly validates embedding vector
dimensions against config.embedding_dimensions at runtime.
"""

import pytest

from secondbrain.config import Config
from secondbrain.domain.value_objects import make_embedding_vector


@pytest.fixture
def default_config() -> Config:
    """Default config loader - uses Config from environment."""
    return Config()


@pytest.fixture
def expected_dim(default_config: Config) -> int:
    """The embedding dimensions configured in the test environment."""
    return default_config.embedding_dimensions


class TestMakeEmbeddingVectorValid:
    """Tests for make_embedding_vector with valid inputs."""

    def test_make_embedding_vector_valid(
        self, default_config: Config, expected_dim: int
    ) -> None:
        """Test that valid dimension matching config is accepted without error."""
        vector = make_embedding_vector([0.1] * expected_dim)
        assert len(vector) == expected_dim
        assert isinstance(vector, list)

    def test_make_embedding_vector_correct_every_element(
        self, default_config: Config, expected_dim: int
    ) -> None:
        """Test that all elements are preserved unchanged."""
        vals = [float(i) / expected_dim for i in range(expected_dim)]
        vector = make_embedding_vector(vals)
        assert len(vector) == expected_dim
        for i, v in enumerate(vector):
            assert abs(v - (float(i) / expected_dim)) < 1e-6


class TestMakeEmbeddingVectorInvalid:
    """Tests for make_embedding_vector with invalid dimensions."""

    def test_make_embedding_vector_wrong_dimension(self, expected_dim: int) -> None:
        """Test that wrong dimension raises ValueError with message indicating expected dim."""
        with pytest.raises(ValueError, match=f"got 999.*expected {expected_dim}"):
            make_embedding_vector([0.1] * 999)

    def test_make_embedding_vector_empty(self, expected_dim: int) -> None:
        """Test that empty list raises ValueError with cannot be empty."""
        with pytest.raises(ValueError, match="cannot be empty"):
            make_embedding_vector([])

    def test_make_embedding_vector_boundary_minus_one(self, expected_dim: int) -> None:
        """Test that (dim-1) raises ValueError."""
        with pytest.raises(
            ValueError, match=f"got {expected_dim - 1}.*expected {expected_dim}"
        ):
            make_embedding_vector([0.1] * (expected_dim - 1))

    def test_make_embedding_vector_boundary_plus_one(self, expected_dim: int) -> None:
        """Test that (dim+1) raises ValueError."""
        with pytest.raises(
            ValueError, match=f"got {expected_dim + 1}.*expected {expected_dim}"
        ):
            make_embedding_vector([0.1] * (expected_dim + 1))

    def test_make_embedding_vector_integer_raises_type_error(
        self, expected_dim: int
    ) -> None:
        """Test that integer input raises TypeError because int is not iterable.

        Passing an integer directly (not wrapped in a list) triggers TypeError
        when make_embedding_vector tries to call list() on it.
        """
        with pytest.raises(TypeError):
            make_embedding_vector(42)  # type: ignore

    def test_make_embedding_vector_none_raises_type_error(
        self, expected_dim: int
    ) -> None:
        """Test that None input raises ValueError."""
        with pytest.raises((TypeError, ValueError)):
            make_embedding_vector(None)
