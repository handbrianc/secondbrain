"""Tests for embedding module."""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.embedding import (
    EmbeddingGenerationError,
    EmbeddingGenerator,
    OllamaUnavailableError,
)


class TestEmbeddingGenerator:
    """Tests for EmbeddingGenerator class."""

    def test_init_default(self) -> None:
        """Test initialization with defaults."""
        gen = EmbeddingGenerator()
        assert gen.model == "embeddinggemma:latest"
        assert gen.ollama_url == "http://localhost:11434"

    def test_init_custom(self) -> None:
        """Test initialization with custom values."""
        gen = EmbeddingGenerator(
            model="custom-model:latest", ollama_url="http://custom:11434"
        )
        assert gen.model == "custom-model:latest"
        assert gen.ollama_url == "http://custom:11434"

    @patch("secondbrain.embedding.httpx.Client")
    def test_validate_connection_success(self, mock_client_class: MagicMock) -> None:
        """Test connection validation when successful."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        assert gen.validate_connection() is True

    @patch("secondbrain.embedding.httpx.Client")
    def test_validate_connection_failure(self, mock_client_class: MagicMock) -> None:
        """Test connection validation when failing."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = Exception("Connection refused")
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        assert gen.validate_connection() is False

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_connection_unavailable(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test generate raises when Ollama unavailable."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=500)
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        with pytest.raises(OllamaUnavailableError):
            gen.generate("test text")

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_success(self, mock_client_class: MagicMock) -> None:
        """Test successful embedding generation."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {"embedding": [0.1, 0.2, 0.3]}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True  # Skip model pull
        result = gen.generate("test text")
        assert result == [0.1, 0.2, 0.3]

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_returns_empty_on_missing(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test generate returns empty list when embedding missing."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        result = gen.generate("test text")
        assert result == []

    @patch("secondbrain.embedding.httpx.Client")
    def test_pull_model_success(self, mock_client_class: MagicMock) -> None:
        """Test successful model pull."""
        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = MagicMock(status_code=200)
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen.pull_model()
        assert gen._model_pulled is True

    @patch("secondbrain.embedding.httpx.Client")
    def test_pull_model_already_pulled(self, mock_client_class: MagicMock) -> None:
        """Test model pull is skipped if already pulled."""
        gen = EmbeddingGenerator()
        gen._model_pulled = True
        gen.pull_model()
        mock_client_class.return_value.post.assert_not_called()

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_batch(self, mock_client_class: MagicMock) -> None:
        """Test batch embedding generation."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {"embedding": [0.1]}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        texts = ["text1", "text2", "text3"]
        results = gen.generate_batch(texts)
        assert len(results) == 3
        assert all(isinstance(r, list) for r in results)

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_non_200_response(self, mock_client_class: MagicMock) -> None:
        """Test generate raises on non-200 response."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=400, text="Bad request"
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        with pytest.raises(EmbeddingGenerationError):
            gen.generate("test text")


class TestEmbeddingSpecRequirements:
    """Tests for embedding specification requirements."""

    def test_default_embedding_model(self) -> None:
        """Test default embedding model (spec: embeddinggemma:latest)."""
        gen = EmbeddingGenerator()
        assert gen.model == "embeddinggemma:latest"

    def test_custom_model_via_constructor(self) -> None:
        """Test custom model via constructor (spec: custom model)."""
        gen = EmbeddingGenerator(model="nomic-embed-text:latest")
        assert gen.model == "nomic-embed-text:latest"

    def test_default_ollama_url(self) -> None:
        """Test default Ollama URL (spec: http://localhost:11434)."""
        gen = EmbeddingGenerator()
        assert gen.ollama_url == "http://localhost:11434"

    def test_custom_ollama_url(self) -> None:
        """Test custom Ollama URL (spec: configurable URL)."""
        gen = EmbeddingGenerator(ollama_url="http://192.168.1.100:11434")
        assert gen.ollama_url == "http://192.168.1.100:11434"

    @patch("secondbrain.embedding.httpx.Client")
    def test_model_auto_pull_if_not_available(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test model auto-pull (spec: auto pull when not available)."""
        mock_client_instance = MagicMock()
        # First call to validate passes, then pull, then generate
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(status_code=200)
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        # Should trigger pull before generate
        result = gen.generate("test text")

        # Verify pull was attempted
        assert gen._model_pulled is True
        assert result is not None

    @patch("secondbrain.embedding.httpx.Client")
    def test_ollama_unavailable_reports_clear_error(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test Ollama unavailable error (spec: clear error message)."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.side_effect = ConnectionError("Connection refused")
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        with pytest.raises(OllamaUnavailableError) as exc_info:
            gen.generate("test text")

        # Verify error message is helpful
        assert "Ollama" in str(exc_info.value)

    @patch("secondbrain.embedding.httpx.Client")
    def test_embedding_dimension(self, mock_client_class: MagicMock) -> None:
        """Test embedding dimension (spec: 384-dim vector)."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"embedding": [0.1] * 384},  # 384-dimensional
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        result = gen.generate("test text")

        assert len(result) == 384

    @patch("secondbrain.embedding.httpx.Client")
    def test_batch_generation_efficiency(self, mock_client_class: MagicMock) -> None:
        """Test batch generation efficiency (spec: processes efficiently)."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {"embedding": [0.1]}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        # Generate batch of 10 texts
        texts = [f"text number {i}" for i in range(10)]
        results = gen.generate_batch(texts)

        assert len(results) == 10
        # All results should be lists
        assert all(isinstance(r, list) for r in results)

    def test_config_model_from_env_variable(self) -> None:
        """Test model from environment variable (spec: SECONDBRAIN_MODEL)."""
        import os
        from unittest.mock import patch

        from secondbrain.config import get_config

        get_config.cache_clear()
        with patch.dict(os.environ, {"SECONDBRAIN_MODEL": "mxbai-embed-large:latest"}):
            config = get_config()
            assert config.model == "mxbai-embed-large:latest"
        get_config.cache_clear()

    @patch("secondbrain.embedding.httpx.Client")
    def test_connection_timeout_handling(self, mock_client_class: MagicMock) -> None:
        """Test connection timeout (spec: timeout handling)."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.side_effect = httpx.TimeoutException(
            "Request timed out"
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        with pytest.raises(EmbeddingGenerationError) as exc_info:
            gen.generate("test text")

        assert (
            "timed out" in str(exc_info.value).lower()
            or "timeout" in str(exc_info.value).lower()
        )

    @patch("secondbrain.embedding.httpx.Client")
    def test_validate_connection_caches_result(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test that validate_connection caches results to avoid repeated API calls."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_class.return_value = mock_client_instance
        gen = EmbeddingGenerator()

        # First call should hit the API
        result1 = gen.validate_connection()
        assert result1 is True
        assert mock_client_instance.get.call_count == 1

        # Second call should use cached result (no API call)
        result2 = gen.validate_connection()
        assert result2 is True
        # Should still be 1 because of caching
        assert mock_client_instance.get.call_count == 1

        # Third call with force=True should bypass cache
        result3 = gen.validate_connection(force=True)
        assert result3 is True
        # Should be 2 because force=True bypasses cache
        assert mock_client_instance.get.call_count == 2

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_uses_cached_connection(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test that generate() uses cached connection validation."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {"embedding": [0.1, 0.2, 0.3]}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        # First generate call
        result1 = gen.generate("test text 1")
        assert result1 == [0.1, 0.2, 0.3]
        initial_get_count = mock_client_instance.get.call_count

        # Second generate call should NOT call validate_connection again (cached)
        result2 = gen.generate("test text 2")
        assert result2 == [0.1, 0.2, 0.3]

        # get() should NOT have been called again because connection is cached
        assert mock_client_instance.get.call_count == initial_get_count

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_batch_single_connection_check(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test batch generation only checks connection once."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.return_value = MagicMock(
            status_code=200, json=lambda: {"embedding": [0.1]}
        )
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        # Generate 10 texts in batch
        texts = [f"text number {i}" for i in range(10)]
        results = gen.generate_batch(texts)

        assert len(results) == 10

        # Should only have checked connection once (not 10 times!)
        assert mock_client_instance.get.call_count == 1

    @patch("secondbrain.embedding.httpx.Client")
    def test_invalidate_connection_cache(self, mock_client_class: MagicMock) -> None:
        """Test invalidate_connection_cache clears the cached state."""
        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()

        # First validation - hits API
        gen.validate_connection()
        assert mock_client_instance.get.call_count == 1

        # Invalidate cache
        gen.invalidate_connection_cache()
        assert gen._connection_valid is None

        # Next validation should hit API again
        gen.validate_connection()
        assert mock_client_instance.get.call_count == 2
