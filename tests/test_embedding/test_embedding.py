"""Tests for embedding module."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

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
        mock_client_instance.request.return_value = mock_response
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
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=200, json=lambda: {"embedding": [0.1, 0.2, 0.3]}),
        ]
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        result = gen.generate("test text")
        assert result == [0.1, 0.2, 0.3]

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_returns_empty_on_missing(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test generate returns empty list when embedding missing."""
        mock_client_instance = MagicMock()
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=200, json=lambda: {}),
        ]
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        result = gen.generate("test text")
        assert result == []

    @patch("secondbrain.embedding.httpx.Client")
    def test_pull_model_success(self, mock_client_class: MagicMock) -> None:
        """Test successful model pull."""
        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = MagicMock(status_code=200)
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
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1]}
        mock_client_instance.request.return_value = mock_response
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
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=400, text="Bad request"),
        ]
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
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=200),
            MagicMock(status_code=200, json=lambda: {"embedding": [0.1, 0.2]}),
        ]
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        result = gen.generate("test text")

        assert gen._model_pulled is True
        assert result is not None

    @patch("secondbrain.embedding.httpx.Client")
    def test_ollama_unavailable_reports_clear_error(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test Ollama unavailable error (spec: clear error message)."""
        mock_client_instance = MagicMock()
        mock_client_instance.request.side_effect = ConnectionError("Connection refused")
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        with pytest.raises(OllamaUnavailableError) as exc_info:
            gen.generate("test text")

        assert "Ollama" in str(exc_info.value)

    @patch("secondbrain.embedding.httpx.Client")
    def test_embedding_dimension(self, mock_client_class: MagicMock) -> None:
        """Test embedding dimension (spec: 384-dim vector)."""
        mock_client_instance = MagicMock()
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            MagicMock(status_code=200, json=lambda: {"embedding": [0.1] * 384}),
        ]
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True
        result = gen.generate("test text")

        assert len(result) == 384

    @patch("secondbrain.embedding.httpx.Client")
    def test_batch_generation_efficiency(self, mock_client_class: MagicMock) -> None:
        """Test batch generation efficiency (spec: processes efficiently)."""
        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1]}
        mock_client_instance.request.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        texts = [f"text number {i}" for i in range(10)]
        results = gen.generate_batch(texts)

        assert len(results) == 10
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
        mock_client_instance.request.side_effect = [
            MagicMock(status_code=200),
            httpx.TimeoutException("Request timed out"),
        ]
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
        mock_client_instance.request.return_value = mock_response
        mock_client_class.return_value = mock_client_instance
        gen = EmbeddingGenerator()

        result1 = gen.validate_connection()
        assert result1 is True
        assert mock_client_instance.request.call_count == 1

        result2 = gen.validate_connection()
        assert result2 is True
        assert mock_client_instance.request.call_count == 1

        result3 = gen.validate_connection(force=True)
        assert result3 is True
        assert mock_client_instance.request.call_count == 2

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_uses_cached_connection(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test that generate() uses cached connection validation."""
        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_client_instance.request.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        result1 = gen.generate("test text 1")
        assert result1 == [0.1, 0.2, 0.3]
        # First generate: 1 validation request + 1 embedding request = 2
        assert mock_client_instance.request.call_count == 2

        result2 = gen.generate("test text 2")
        assert result2 == [0.1, 0.2, 0.3]
        # Second generate: validation is cached (0) + 1 embedding request = 1 more
        # Total should be 3, not 2
        assert mock_client_instance.request.call_count == 3

        # Verify validation was cached (only 1 validation call total)
        # The 2nd embedding request uses the same client but cached validation
        validation_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET" and "api/tags" in call[0][1]
        ]
        assert len(validation_calls) == 1

    @patch("secondbrain.embedding.httpx.Client")
    def test_generate_batch_single_connection_check(
        self, mock_client_class: MagicMock
    ) -> None:
        """Test batch generation reuses cached connection for all texts."""
        mock_client_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1]}
        mock_client_instance.request.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()
        gen._model_pulled = True

        texts = [f"text number {i}" for i in range(10)]
        results = gen.generate_batch(texts)

        assert len(results) == 10
        assert all(isinstance(r, list) for r in results)

        # Batch generation calls generate() for each text
        # First generate: 1 validation GET + 1 embedding POST = 2
        # Remaining generates: 0 validation (cached) + 1 embedding POST each = 1 each
        # Total for 10 texts: 2 + 9 = 11
        assert mock_client_instance.request.call_count == 11

        # Verify only 1 validation call (cached for remaining 9)
        validation_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if call[0][0] == "GET" and "api/tags" in call[0][1]
        ]
        assert len(validation_calls) == 1

    @patch("secondbrain.embedding.httpx.Client")
    def test_invalidate_connection_cache(self, mock_client_class: MagicMock) -> None:
        """Test invalidate_connection_cache clears the cached state."""
        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = MagicMock(status_code=200)
        mock_client_class.return_value = mock_client_instance

        gen = EmbeddingGenerator()

        gen.validate_connection()
        assert mock_client_instance.request.call_count == 1

        gen.invalidate_connection_cache()
        assert gen._connection_valid is None

        gen.validate_connection()
        assert mock_client_instance.request.call_count == 2


@pytest.mark.asyncio
class TestAsyncEmbeddingGenerator:
    """Tests for async embedding generator."""

    @patch("secondbrain.embedding.httpx.AsyncClient")
    async def test_generate_batch_async_respects_rate_limit(
        self, mock_async_client_class: MagicMock
    ) -> None:
        """Test async batch generation applies rate limiting."""
        from secondbrain.embedding import EmbeddingGenerator, RateLimiter

        # Track rate limiting calls
        rate_limit_calls = []

        class TrackingRateLimiter(RateLimiter):
            def acquire(self) -> None:
                rate_limit_calls.append(time.monotonic())
                super().acquire()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"embedding": [0.1, 0.2, 0.3]}

        mock_async_client_instance = MagicMock()
        mock_async_client_instance.request = AsyncMock(return_value=mock_response)
        mock_async_client_class.return_value = mock_async_client_instance

        rate_limiter = TrackingRateLimiter(max_requests=2, window_seconds=1.0)
        gen = EmbeddingGenerator(rate_limiter=rate_limiter)

        # Mock the connection validation to return True
        gen._connection_valid = True
        gen._connection_checked_at = time.monotonic()
        gen._model_pulled = True

        texts = ["text1", "text2", "text3"]
        await gen.generate_batch_async(texts)

        # Verify rate limiting was applied
        assert len(rate_limit_calls) >= 3

    @patch("secondbrain.embedding.httpx.AsyncClient")
    async def test_generate_async_success(
        self, mock_async_client_class: MagicMock
    ) -> None:
        """Test successful async embedding generation."""

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = lambda: {"embedding": [0.1, 0.2, 0.3]}

        mock_async_client_instance = MagicMock()
        mock_async_client_instance.request = AsyncMock(return_value=mock_response)
        mock_async_client_class.return_value = mock_async_client_instance

        gen = EmbeddingGenerator()
        gen._connection_valid = True
        gen._connection_checked_at = time.monotonic()
        gen._model_pulled = True

        result = await gen.generate_async("test text")
        assert result == [0.1, 0.2, 0.3]

    @patch("secondbrain.embedding.httpx.AsyncClient")
    async def test_generate_async_connection_unavailable(
        self, mock_async_client_class: MagicMock
    ) -> None:
        """Test async generate raises when Ollama unavailable."""

        mock_async_client_instance = MagicMock()
        mock_async_client_instance.request = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        mock_async_client_class.return_value = mock_async_client_instance

        gen = EmbeddingGenerator()
        gen._connection_valid = False

        with pytest.raises(OllamaUnavailableError):
            await gen.generate_async("test text")
