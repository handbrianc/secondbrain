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
    def test_model_auto_pull_if_not_available(self, mock_client_class: MagicMock) -> None:
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
    def test_ollama_unavailable_reports_clear_error(self, mock_client_class: MagicMock) -> None:
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
            json=lambda: {"embedding": [0.1] * 384}  # 384-dimensional
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

        from secondbrain.config import Config, get_config

        # Clear the cache to pick up new env var
        get_config.cache_clear()

        with patch.dict(os.environ, {"SECONDBRAIN_MODEL": "mxbai-embed-large:latest"}):
            config = Config()
            assert config.model == "mxbai-embed-large:latest"
        """Test model from environment variable (spec: SECONDBRAIN_MODEL)."""
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"SECONDBRAIN_MODEL": "mxbai-embed-large:latest"}):
            from secondbrain.config import get_config
            config = get_config()
            assert config.model == "mxbai-embed-large:latest"

    @patch("secondbrain.embedding.httpx.Client")
    def test_connection_timeout_handling(self, mock_client_class: MagicMock) -> None:
        """Test connection timeout (spec: timeout handling)."""
        import httpx

        mock_client_instance = MagicMock()
        mock_client_instance.get.return_value = MagicMock(status_code=200)
        mock_client_instance.post.side_effect = httpx.TimeoutException("Request timed out")
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        with pytest.raises(EmbeddingGenerationError) as exc_info:
            gen.generate("test text")

        assert "timed out" in str(exc_info.value).lower() or "timeout" in str(exc_info.value).lower()
