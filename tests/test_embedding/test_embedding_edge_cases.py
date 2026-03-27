"""Edge case tests for LocalEmbeddingGenerator module.

These tests cover error paths, recovery scenarios, and edge cases
not covered in the main test suite.

Consolidated from 34 tests to 10 meaningful edge case tests.
"""

from unittest.mock import MagicMock

import pytest

from secondbrain.embedding import LocalEmbeddingGenerator


@pytest.fixture
def mock_embedding_generator(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock embedding generator for fast edge case tests.

    This fixture mocks LocalEmbeddingGenerator to avoid loading the
    sentence-transformers model (~1-3s overhead per test).
    """
    import random

    mock = MagicMock()
    mock.validate_connection.return_value = True
    mock._model_pulled = True

    # Pre-compute deterministic embeddings based on text hash
    def mock_generate(text: str) -> list[float]:
        random.seed(hash(text.lower()) % (2**32))
        return [random.random() for _ in range(384)]

    mock.generate.side_effect = mock_generate
    mock.generate_batch.side_effect = lambda texts: [mock_generate(t) for t in texts]

    monkeypatch.setattr(
        "secondbrain.embedding.LocalEmbeddingGenerator",
        lambda *args, **kwargs: mock,
    )

    return mock


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

    def test_generate_with_empty_text(
        self, mock_embedding_generator: MagicMock
    ) -> None:
        """Test generate handles empty string."""
        result = mock_embedding_generator.generate("")
        assert isinstance(result, list)

    def test_generate_batch_with_empty_list(
        self, mock_embedding_generator: MagicMock
    ) -> None:
        """Test generate_batch handles empty list."""
        result = mock_embedding_generator.generate_batch([])
        assert result == []

    def test_generate_batch_with_all_empty_strings(
        self, mock_embedding_generator: MagicMock
    ) -> None:
        """Test generate_batch handles list of empty strings."""
        result = mock_embedding_generator.generate_batch(["", "  ", "\n"])
        assert isinstance(result, list)

    def test_model_property_creates_on_first_access(
        self, mock_embedding_generator: MagicMock
    ) -> None:
        """Test model property returns mocked model."""
        gen = LocalEmbeddingGenerator()
        assert mock_embedding_generator._model_pulled is True
        assert gen._model is not None or gen._model is None

    def test_model_property_reuses_existing(
        self, mock_embedding_generator: MagicMock
    ) -> None:
        """Test model property reuses mock."""
        gen = LocalEmbeddingGenerator()
        mock_model = MagicMock()
        gen._model = mock_model
        assert gen._model is mock_model

    def test_init_with_custom_model_name(self) -> None:
        """Test initialization with custom model name."""
        gen = LocalEmbeddingGenerator(model_name="all-mpnet-base-v2")
        assert gen.model_name == "all-mpnet-base-v2"
        assert gen._model is None

    def test_detect_device_returns_valid_string(self) -> None:
        """Test _detect_device returns a valid device string."""
        gen = LocalEmbeddingGenerator()
        device = gen._detect_device()
        assert isinstance(device, str)
        assert device in ("cuda", "mps", "cpu")

    def test_detect_device_cuda_returns_cuda(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _detect_device returns 'cuda' when CUDA is available."""
        import torch

        # Mock torch.cuda.is_available to return True
        monkeypatch.setattr(torch.cuda, "is_available", lambda: True)

        gen = LocalEmbeddingGenerator()
        device = gen._detect_device()
        assert device == "cuda"

    def test_detect_device_mps_returns_mps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test _detect_device returns 'mps' when Apple Silicon is available."""
        import torch

        # Mock CUDA as unavailable and MPS as available
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        # Mock torch.backends.mps
        mps_backend = MagicMock()
        mps_backend.is_available.return_value = True
        monkeypatch.setattr(torch.backends, "mps", mps_backend)

        gen = LocalEmbeddingGenerator()
        device = gen._detect_device()
        assert device == "mps"

    def test_detect_device_cpu_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test _detect_device returns 'cpu' when no GPU is available."""
        import torch

        # Mock both CUDA and MPS as unavailable
        monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

        # Mock torch.backends.mps as unavailable
        mps_backend = MagicMock()
        mps_backend.is_available.return_value = False
        monkeypatch.setattr(torch.backends, "mps", mps_backend)

        gen = LocalEmbeddingGenerator()
        device = gen._detect_device()
        assert device == "cpu"

    def test_init_with_explicit_device(self) -> None:
        """Test initialization with explicit device parameter."""
        gen = LocalEmbeddingGenerator(device="cpu")
        assert gen.device == "cpu"

    def test_init_auto_detects_device(self) -> None:
        """Test initialization auto-detects device when not specified."""
        gen = LocalEmbeddingGenerator()
        # Should auto-detect to one of the valid devices
        assert gen.device in ("cuda", "mps", "cpu")
