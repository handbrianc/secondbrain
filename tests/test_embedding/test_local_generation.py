"""Comprehensive tests for embedding generation in LocalEmbeddingGenerator.

These tests cover the core embedding generation functionality including
model loading, single/batch generation, dimension validation, and edge cases.

Target coverage: 90%+ for secondbrain.embedding.local module.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from secondbrain.embedding import LocalEmbeddingGenerator
from secondbrain.embedding.local import TARGET_EMBEDDING_DIMENSIONS


class TestEmbeddingModelLoading:
    """Test model initialization and loading."""

    def test_embedding_model_loading(self) -> None:
        """Test model initialization and loading."""
        # Test default model name
        gen = LocalEmbeddingGenerator()
        assert gen.model_name == "all-MiniLM-L6-v2"
        assert gen._model is None

        # Test custom model name
        gen_custom = LocalEmbeddingGenerator(model_name="all-mpnet-base-v2")
        assert gen_custom.model_name == "all-mpnet-base-v2"

    def test_model_property_loads_sentence_transformers(self) -> None:
        """Test that model property loads SentenceTransformer."""
        gen = LocalEmbeddingGenerator()

        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            # Access model property
            model = gen.model

            # Verify SentenceTransformer was called with correct model name
            mock_st.assert_called_once_with("all-MiniLM-L6-v2")
            assert model is mock_model

    def test_model_property_reuses_loaded_model(self) -> None:
        """Test that model property reuses already loaded model."""
        gen = LocalEmbeddingGenerator()

        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            # Access model property twice
            _ = gen.model
            _ = gen.model

            # Verify SentenceTransformer was only called once
            mock_st.assert_called_once()


class TestEmbeddingGenerate:
    """Test embedding generation functionality."""

    def test_embedding_generate_single(self) -> None:
        """Test single text embedding."""
        gen = LocalEmbeddingGenerator()

        # Mock the model and its encode method
        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [0.1] * 512  # Model returns 512 dims
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Generate embedding
        embedding = gen.generate("test text")

        # Verify encode was called correctly
        mock_model.encode.assert_called_once_with("test text", convert_to_numpy=True)

        # Verify result is truncated to target dimensions
        assert len(embedding) == TARGET_EMBEDDING_DIMENSIONS
        assert embedding == [0.1] * TARGET_EMBEDDING_DIMENSIONS

    def test_embedding_generate_batch(self) -> None:
        """Test batch embedding generation."""
        gen = LocalEmbeddingGenerator()

        # Mock the model and its encode method
        mock_model = MagicMock()
        # Return embeddings with more dimensions than target
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [
            [0.1 * (i + 1)] * 512 for i in range(5)
        ]
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        texts = ["text1", "text2", "text3", "text4", "text5"]

        # Generate batch embeddings
        embeddings = gen.generate_batch(texts)

        # Verify encode was called with all texts
        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert call_args is not None
        assert call_args[0][0] == texts  # First positional arg is texts list

        # Verify all embeddings are truncated to target dimensions
        assert len(embeddings) == 5
        for emb in embeddings:
            assert len(emb) == TARGET_EMBEDDING_DIMENSIONS

    def test_embedding_generate_batch_empty_list(self) -> None:
        """Test batch embedding generation with empty list."""
        gen = LocalEmbeddingGenerator()

        embeddings = gen.generate_batch([])

        assert embeddings == []

    def test_embedding_generate_batch_filters_empty_strings(self) -> None:
        """Test that batch generation filters out empty strings."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [[0.1] * 384]
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Include empty strings in input
        texts = ["valid text", "", "  ", "\n", "another valid"]

        _ = gen.generate_batch(texts)

        # Verify encode was called only with non-empty strings
        call_args = mock_model.encode.call_args
        assert call_args is not None
        filtered_texts = call_args[0][0]
        assert "" not in filtered_texts
        assert "  " not in filtered_texts
        assert "\n" not in filtered_texts


class TestEmbeddingDimensions:
    """Test embedding dimension validation."""

    def test_embedding_dimensions_correct(self) -> None:
        """Verify output dimensions match config."""
        gen = LocalEmbeddingGenerator()

        # Mock model to return embeddings of various sizes
        mock_model = MagicMock()

        # Test case 1: Model returns exactly target dimensions
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [0.1] * TARGET_EMBEDDING_DIMENSIONS
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        embedding = gen.generate("test")
        assert len(embedding) == TARGET_EMBEDDING_DIMENSIONS

        # Test case 2: Model returns more dimensions (should truncate)
        mock_encode_result.tolist.return_value = [0.1] * 1024
        embedding = gen.generate("test")
        assert len(embedding) == TARGET_EMBEDDING_DIMENSIONS

        # Test case 3: Model returns fewer dimensions (should preserve)
        mock_encode_result.tolist.return_value = [0.1] * 256
        embedding = gen.generate("test")
        assert len(embedding) == 256  # No truncation needed

    def test_embedding_batch_dimensions_consistent(self) -> None:
        """Test that all embeddings in batch have consistent dimensions."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        # Return embeddings with varying sizes
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [
            [0.1] * 512,  # Will be truncated
            [0.1] * 384,  # Already correct
            [0.1] * 768,  # Will be truncated
        ]
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        embeddings = gen.generate_batch(["text1", "text2", "text3"])

        # All embeddings should have exactly TARGET_EMBEDDING_DIMENSIONS
        for emb in embeddings:
            assert len(emb) == TARGET_EMBEDDING_DIMENSIONS


class TestEmbeddingConsistency:
    """Test embedding consistency and reproducibility."""

    def test_embedding_consistency(self) -> None:
        """Same text produces same embedding."""
        gen = LocalEmbeddingGenerator()

        # Mock model to return deterministic embeddings
        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        expected_embedding = [0.123456] * TARGET_EMBEDDING_DIMENSIONS
        mock_encode_result.tolist.return_value = expected_embedding
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Generate embedding multiple times for same text
        embedding1 = gen.generate("consistent text")
        embedding2 = gen.generate("consistent text")
        embedding3 = gen.generate("consistent text")

        # All should be identical
        assert embedding1 == embedding2 == embedding3
        assert embedding1 == expected_embedding


class TestEmbeddingEmptyText:
    """Test handling of empty text inputs."""

    def test_embedding_empty_text(self) -> None:
        """Test handling of empty strings."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [0.0] * TARGET_EMBEDDING_DIMENSIONS
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Generate embedding for empty string
        embedding = gen.generate("")

        # Should still return a valid embedding
        assert isinstance(embedding, list)
        assert len(embedding) == TARGET_EMBEDDING_DIMENSIONS

    def test_embedding_whitespace_only(self) -> None:
        """Test handling of whitespace-only strings."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [0.0] * TARGET_EMBEDDING_DIMENSIONS
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Generate embedding for whitespace
        embedding = gen.generate("   \n\t   ")

        assert isinstance(embedding, list)
        assert len(embedding) == TARGET_EMBEDDING_DIMENSIONS


class TestEmbeddingLargeBatch:
    """Test large batch processing."""

    def test_embedding_large_batch(self) -> None:
        """Test with 100+ texts."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        # Generate 100 embeddings
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [
            [float(i)] * TARGET_EMBEDDING_DIMENSIONS for i in range(100)
        ]
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        # Create 100 test texts
        texts = [f"text_{i}" for i in range(100)]

        # Generate batch
        embeddings = gen.generate_batch(texts)

        # Verify all embeddings generated
        assert len(embeddings) == 100

        # Verify each has correct dimensions
        for emb in embeddings:
            assert len(emb) == TARGET_EMBEDDING_DIMENSIONS

    def test_embedding_very_large_batch(self) -> None:
        """Test with 500+ texts for stress testing."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [
            [0.5] * TARGET_EMBEDDING_DIMENSIONS for _ in range(500)
        ]
        mock_model.encode.return_value = mock_encode_result
        gen._model = mock_model

        texts = [f"stress_test_{i}" for i in range(500)]

        embeddings = gen.generate_batch(texts)

        assert len(embeddings) == 500
        for emb in embeddings:
            assert len(emb) == TARGET_EMBEDDING_DIMENSIONS


class TestEmbeddingCuda:
    """Test GPU/CUDA detection and usage."""

    def test_embedding_cuda_available(self) -> None:
        """Test GPU detection when available."""
        gen = LocalEmbeddingGenerator()

        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            with patch.object(mock_model, "device", new=MagicMock(return_value="cuda")):
                # Access model
                _ = gen.model

                # Verify model was created
                mock_st.assert_called_once()

    def test_embedding_cuda_not_available(self) -> None:
        """Test CPU fallback when CUDA not available."""
        gen = LocalEmbeddingGenerator()

        with patch("sentence_transformers.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            with patch.object(mock_model, "device", new=MagicMock(return_value="cpu")):
                # Access model
                _ = gen.model

                # Verify model was created (no error on CPU)
                mock_st.assert_called_once()


class TestValidateConnection:
    """Test connection validation functionality."""

    def test_validate_connection_success(self) -> None:
        """Test successful connection validation."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock()
        gen._model = mock_model

        result = gen.validate_connection()

        assert result is True
        assert gen._connection_valid is True

    def test_validate_connection_failure(self) -> None:
        """Test connection validation failure."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_model.encode.side_effect = RuntimeError("Model not available")
        gen._model = mock_model

        result = gen.validate_connection()

        assert result is False
        assert gen._connection_valid is False

    def test_validate_connection_caching(self) -> None:
        """Test that validation results are cached."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock()
        gen._model = mock_model
        gen._connection_valid = True
        gen._connection_checked_at = 1000.0  # Set a past timestamp

        # First call
        result1 = gen.validate_connection()
        assert result1 is True

        # Second call should use cache
        result2 = gen.validate_connection()
        assert result2 is True

        # Verify encode was only called once (during first validation)
        assert mock_model.encode.call_count == 1

    def test_validate_connection_force_revalidate(self) -> None:
        """Test force revalidation bypasses cache."""
        gen = LocalEmbeddingGenerator()

        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock()
        gen._model = mock_model
        gen._connection_valid = False  # Previously failed

        # Force revalidation
        result = gen.validate_connection(force=True)

        assert result is True
        assert gen._connection_valid is True
        # Verify encode was called despite cached failure
        assert mock_model.encode.call_count == 1


class TestEmbeddingClose:
    """Test resource cleanup functionality."""

    def test_close_with_active_model(self) -> None:
        """Test close() properly clears model reference."""
        gen = LocalEmbeddingGenerator()
        mock_model = MagicMock()
        gen._model = mock_model
        gen._connection_valid = True
        gen._connection_checked_at = 1000.0

        gen.close()

        assert gen._model is None
        assert gen._connection_valid is None
        assert gen._connection_checked_at == 0.0

    def test_close_with_none_model(self) -> None:
        """Test close() handles None model gracefully."""
        gen = LocalEmbeddingGenerator()
        gen._model = None

        # Should not raise
        gen.close()

        assert gen._model is None

    def test_close_idempotent(self) -> None:
        """Test close() can be called multiple times safely."""
        gen = LocalEmbeddingGenerator()
        gen._model = MagicMock()
        gen.close()

        # Second call should not raise
        gen.close()

        assert gen._model is None
