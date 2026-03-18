"""Edge case tests for LocalEmbeddingGenerator module.

These tests cover error paths, recovery scenarios, and edge cases
not covered in the main test suite.

Consolidated from 34 tests to 10 meaningful edge case tests.
"""

from unittest.mock import MagicMock

from secondbrain.embedding import LocalEmbeddingGenerator


class TestLocalEmbeddingGeneratorEdgeCases:
    """Edge case tests for LocalEmbeddingGenerator."""

    def test_close_with_none_model(self) -> None:
        """Test close() handles None model gracefully."""
        gen = LocalEmbeddingGenerator()
        gen._model = None
        # Should not raise
        gen.close()

    def test_close_with_active_model(self) -> None:
        """Test close() properly clears model reference."""
        gen = LocalEmbeddingGenerator()
        mock_model = MagicMock()
        gen._model = mock_model

        gen.close()

        assert gen._model is None

    def test_close_idempotent(self) -> None:
        """Test close() can be called multiple times safely."""
        gen = LocalEmbeddingGenerator()
        gen.close()
        # Should not raise on second call
        gen.close()

    def test_generate_with_empty_text(self) -> None:
        """Test generate handles empty string gracefully."""
        gen = LocalEmbeddingGenerator()
        # Should not raise, may return empty or zero embedding
        result = gen.generate("")
        assert isinstance(result, list)

    def test_generate_batch_with_empty_list(self) -> None:
        """Test generate_batch handles empty list."""
        gen = LocalEmbeddingGenerator()
        result = gen.generate_batch([])
        assert result == []

    def test_generate_batch_with_all_empty_strings(self) -> None:
        """Test generate_batch handles list of empty strings."""
        gen = LocalEmbeddingGenerator()
        result = gen.generate_batch(["", "  ", "\n"])
        # Should handle gracefully, may return empty embeddings
        assert isinstance(result, list)

    def test_model_property_creates_on_first_access(self) -> None:
        """Test model property creates model on first access."""
        gen = LocalEmbeddingGenerator()
        assert gen._model is None
        # Access property should create model
        _ = gen.model
        assert gen._model is not None

    def test_model_property_reuses_existing(self) -> None:
        """Test model property reuses existing model."""
        gen = LocalEmbeddingGenerator()
        mock_model = MagicMock()
        gen._model = mock_model
        # Should return existing model without creating new one
        result = gen.model
        assert result is mock_model

    def test_init_with_custom_model_name(self) -> None:
        """Test initialization with custom model name."""
        gen = LocalEmbeddingGenerator(model_name="all-mpnet-base-v2")
        assert gen.model_name == "all-mpnet-base-v2"
        assert gen._model is None
