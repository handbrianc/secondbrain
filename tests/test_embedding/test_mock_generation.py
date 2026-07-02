"""Comprehensive tests for MockEmbeddingGenerator.

These tests cover the mock embedding generator used for fast unit tests,
ensuring deterministic behavior and proper edge case handling.

Target coverage: 100% for secondbrain.embedding.mock module.
"""

from __future__ import annotations

import numpy as np

from secondbrain.embedding.mock import MockEmbeddingGenerator


class TestMockEmbeddingGeneratorInit:
    """Test MockEmbeddingGenerator initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        gen = MockEmbeddingGenerator()

        assert gen.model_name == "mock-embedding"
        assert gen.dimension == 384

    def test_init_with_custom_parameters(self) -> None:
        """Test initialization with custom model name and dimension."""
        gen = MockEmbeddingGenerator(model_name="custom-mock", dimension=768)

        assert gen.model_name == "custom-mock"
        assert gen.dimension == 768

    def test_init_various_dimensions(self) -> None:
        """Test initialization with various embedding dimensions."""
        dimensions = [128, 256, 384, 512, 768, 1024]

        for dim in dimensions:
            gen = MockEmbeddingGenerator(dimension=dim)
            assert gen.dimension == dim


class TestMockEmbeddingGenerate:
    """Test single text embedding generation."""

    def test_generate_returns_list(self) -> None:
        """Test that generate returns a list."""
        gen = MockEmbeddingGenerator()

        result = gen.generate("test text")

        assert isinstance(result, list)

    def test_generate_returns_correct_dimension(self) -> None:
        """Test that generated embedding has correct dimension."""
        gen = MockEmbeddingGenerator(dimension=384)

        result = gen.generate("test text")

        assert len(result) == 384

    def test_generate_deterministic(self) -> None:
        """Test that same input produces same output."""
        gen = MockEmbeddingGenerator(dimension=384)

        result1 = gen.generate("test text")
        result2 = gen.generate("test text")

        assert result1 == result2

    def test_generate_different_inputs_different_outputs(self) -> None:
        """Test that different inputs produce different outputs."""
        gen = MockEmbeddingGenerator(dimension=384)

        result1 = gen.generate("text one")
        result2 = gen.generate("text two")

        assert result1 != result2

    def test_generate_empty_string(self) -> None:
        """Test embedding generation for empty string."""
        gen = MockEmbeddingGenerator(dimension=384)

        result = gen.generate("")

        assert isinstance(result, list)
        assert len(result) == 384

    def test_generate_whitespace_only(self) -> None:
        """Test embedding generation for whitespace-only string."""
        gen = MockEmbeddingGenerator(dimension=384)

        result = gen.generate("   \n\t  ")

        assert isinstance(result, list)
        assert len(result) == 384

    def test_generate_very_long_text(self) -> None:
        """Test embedding generation for very long text."""
        gen = MockEmbeddingGenerator(dimension=384)

        long_text = "word " * 10000
        result = gen.generate(long_text)

        assert isinstance(result, list)
        assert len(result) == 384

    def test_generate_unicode_text(self) -> None:
        """Test embedding generation for unicode text."""
        gen = MockEmbeddingGenerator(dimension=384)

        unicode_text = "Hello 世界 مرحبا שלום"
        result = gen.generate(unicode_text)

        assert isinstance(result, list)
        assert len(result) == 384

    def test_generate_normalized_vector(self) -> None:
        """Test that generated vectors are normalized (unit length)."""
        gen = MockEmbeddingGenerator(dimension=384)

        result = gen.generate("test text")

        # Convert to numpy and check norm
        vector = np.array(result)
        norm = np.linalg.norm(vector)

        # Should be close to 1.0 (unit vector)
        assert abs(norm - 1.0) < 1e-5


class TestMockEmbeddingGenerateBatch:
    """Test batch embedding generation."""

    def test_generate_batch_returns_list_of_lists(self) -> None:
        """Test that generate_batch returns list of lists."""
        gen = MockEmbeddingGenerator()

        result = gen.generate_batch(["text1", "text2", "text3"])

        assert isinstance(result, list)
        assert all(isinstance(emb, list) for emb in result)

    def test_generate_batch_correct_count(self) -> None:
        """Test that batch returns correct number of embeddings."""
        gen = MockEmbeddingGenerator()

        texts = ["text1", "text2", "text3", "text4", "text5"]
        result = gen.generate_batch(texts)

        assert len(result) == 5

    def test_generate_batch_correct_dimensions(self) -> None:
        """Test that all batch embeddings have correct dimension."""
        gen = MockEmbeddingGenerator(dimension=512)

        result = gen.generate_batch(["text1", "text2", "text3"])

        for emb in result:
            assert len(emb) == 512

    def test_generate_batch_deterministic(self) -> None:
        """Test that batch generation is deterministic."""
        gen = MockEmbeddingGenerator(dimension=384)

        texts = ["text1", "text2", "text3"]
        result1 = gen.generate_batch(texts)
        result2 = gen.generate_batch(texts)

        assert result1 == result2

    def test_generate_batch_empty_list(self) -> None:
        """Test batch generation with empty list."""
        gen = MockEmbeddingGenerator()

        result = gen.generate_batch([])

        assert result == []

    def test_generate_batch_single_text(self) -> None:
        """Test batch generation with single text."""
        gen = MockEmbeddingGenerator(dimension=384)

        result = gen.generate_batch(["single text"])

        assert len(result) == 1
        assert len(result[0]) == 384

    def test_generate_batch_mixed_content(self) -> None:
        """Test batch generation with mixed content types."""
        gen = MockEmbeddingGenerator(dimension=384)

        texts = ["simple text", "", "   ", "unicode 世界", "very long text " * 100]

        result = gen.generate_batch(texts)

        assert len(result) == 5
        for emb in result:
            assert len(emb) == 384


class TestMockEmbeddingClose:
    """Test close method."""

    def test_close_returns_none(self) -> None:
        """Test that close returns None."""
        gen = MockEmbeddingGenerator()

        result = gen.close()

        assert result is None

    def test_close_idempotent(self) -> None:
        """Test that close can be called multiple times."""
        gen = MockEmbeddingGenerator()

        gen.close()
        gen.close()
        gen.close()

        # Should not raise any errors


class TestMockEmbeddingRepr:
    """Test __repr__ method."""

    def test_repr_default(self) -> None:
        """Test repr with default parameters."""
        gen = MockEmbeddingGenerator()

        result = repr(gen)

        assert "MockEmbeddingGenerator" in result
        assert "model=mock-embedding" in result
        assert "dimension=384" in result

    def test_repr_custom_parameters(self) -> None:
        """Test repr with custom parameters."""
        gen = MockEmbeddingGenerator(model_name="custom", dimension=768)

        result = repr(gen)

        assert "MockEmbeddingGenerator" in result
        assert "model=custom" in result
        assert "dimension=768" in result
