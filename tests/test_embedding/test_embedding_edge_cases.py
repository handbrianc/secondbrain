"""Edge case tests for EmbeddingGenerator module.

These tests cover error paths, recovery scenarios, and edge cases
not covered in the main test suite.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from secondbrain.embedding import EmbeddingGenerator
from secondbrain.exceptions import EmbeddingGenerationError, OllamaUnavailableError


class TestEmbeddingGeneratorClose:
    """Tests for close() and aclose() methods."""

    def test_close_with_none_client(self):
        """Test close() handles None client gracefully."""
        gen = EmbeddingGenerator()
        gen._client = None
        # Should not raise
        gen.close()

    def test_close_with_active_client(self):
        """Test close() properly closes active client."""
        gen = EmbeddingGenerator()
        mock_client = MagicMock()
        gen._client = mock_client

        gen.close()

        mock_client.close.assert_called_once()
        assert gen._client is None

    @pytest.mark.asyncio
    async def test_aclose_with_none_clients(self):
        """Test aclose() handles None clients gracefully."""
        gen = EmbeddingGenerator()
        gen._client = None
        gen._async_client = None
        # Should not raise
        await gen.aclose()

    @pytest.mark.asyncio
    async def test_aclose_with_active_clients(self):
        """Test aclose() properly closes both clients."""
        from unittest.mock import AsyncMock

        gen = EmbeddingGenerator()
        mock_client = MagicMock()
        mock_async_client = MagicMock()
        mock_async_client.aclose = AsyncMock()
        gen._client = mock_client
        gen._async_client = mock_async_client

        await gen.aclose()

        mock_client.close.assert_called_once()
        mock_async_client.aclose.assert_called_once()
        assert gen._client is None
        assert gen._async_client is None


class TestEmbeddingGeneratorContextManager:
    """Tests for context manager protocols."""

    def test_context_manager_enter(self):
        """Test __enter__ returns self."""
        with EmbeddingGenerator() as gen:
            assert gen is not None

    def test_context_manager_exit(self):
        """Test __exit__ closes the client."""
        with patch.object(EmbeddingGenerator, "close") as mock_close:
            with EmbeddingGenerator():
                pass
            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_context_manager_enter(self):
        """Test __aenter__ returns self."""
        async with EmbeddingGenerator() as gen:
            assert gen is not None

    @pytest.mark.asyncio
    async def test_async_context_manager_exit(self):
        """Test __aexit__ closes both clients."""
        with patch.object(EmbeddingGenerator, "aclose") as mock_aclose:
            async with EmbeddingGenerator():
                pass
            mock_aclose.assert_called_once()

    def test_context_manager_exception_handling(self):
        """Test context manager handles exceptions properly."""
        with patch.object(EmbeddingGenerator, "close") as mock_close:
            with pytest.raises(ValueError), EmbeddingGenerator():
                raise ValueError("test error")
            # close should still be called even with exception
            mock_close.assert_called_once()


class TestEmbeddingGeneratorModelInfo:
    """Tests for get_model_info() methods."""

    def test_get_model_info_success(self, monkeypatch):
        """Test successful model info retrieval."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {
                    "name": "embeddinggemma:latest",
                    "size": 1234567890,
                }
            ]
        }

        with patch.object(gen, "_request", return_value=mock_response):
            info = gen.get_model_info()

        assert info is not None
        assert info["name"] == "embeddinggemma:latest"
        assert info["size"] == 1234567890
        assert "embedding_dimensions" in info

    def test_get_model_info_non_200_response(self, monkeypatch):
        """Test get_model_info handles non-200 response."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch.object(gen, "_request", return_value=mock_response):
            info = gen.get_model_info()

        assert info is None

    def test_get_model_info_no_matching_model(self, monkeypatch):
        """Test get_model_info returns None when model not found."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "different-model:latest"},
            ]
        }

        with patch.object(gen, "_request", return_value=mock_response):
            info = gen.get_model_info()

        assert info is None

    def test_get_model_info_exception(self, monkeypatch):
        """Test get_model_info handles exceptions gracefully."""
        gen = EmbeddingGenerator()

        with patch.object(gen, "_request", side_effect=Exception("network error")):
            info = gen.get_model_info()

        assert info is None

    @pytest.mark.asyncio
    async def test_get_model_info_async_success(self, monkeypatch):
        """Test successful async model info retrieval."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {
                    "name": "embeddinggemma:latest",
                    "size": 1234567890,
                }
            ]
        }

        with patch.object(gen, "_request_async", return_value=mock_response):
            info = await gen.get_model_info_async()

        assert info is not None
        assert info["name"] == "embeddinggemma:latest"

    @pytest.mark.asyncio
    async def test_get_model_info_async_non_200(self, monkeypatch):
        """Test async model info handles non-200 response."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(gen, "_request_async", return_value=mock_response):
            info = await gen.get_model_info_async()

        assert info is None


class TestEmbeddingGeneratorModelPulling:
    """Tests for pull_model() methods."""

    def test_pull_model_already_pulled(self, monkeypatch):
        """Test pull_model skips if already pulled."""
        gen = EmbeddingGenerator()
        gen._model_pulled = True

        with patch.object(gen, "_request") as mock_request:
            gen.pull_model()

        mock_request.assert_not_called()

    def test_pull_model_success(self, monkeypatch):
        """Test successful model pulling."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(gen, "_request", return_value=mock_response):
            gen.pull_model()

        assert gen._model_pulled is True

    def test_pull_model_failed_status(self, monkeypatch, caplog):
        """Test pull_model handles failed status code."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch.object(gen, "_request", return_value=mock_response):
            gen.pull_model()

        # Should log warning but not raise
        assert gen._model_pulled is False

    def test_pull_model_exception(self, monkeypatch, caplog):
        """Test pull_model handles exceptions."""
        gen = EmbeddingGenerator()

        with (
            patch.object(gen, "_request", side_effect=Exception("network error")),
            pytest.raises(OllamaUnavailableError),
        ):
            gen.pull_model()

    def test_pull_model_async_already_pulled(self, monkeypatch):
        """Test async pull_model skips if already pulled."""
        gen = EmbeddingGenerator()
        gen._model_pulled = True

        with patch.object(gen, "_request_async") as mock_request:
            import asyncio

            asyncio.run(gen.pull_model_async())

        mock_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_pull_model_async_success(self, monkeypatch):
        """Test successful async model pulling."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(gen, "_request_async", return_value=mock_response):
            await gen.pull_model_async()

        assert gen._model_pulled is True

    @pytest.mark.asyncio
    async def test_pull_model_async_failed_status(self, monkeypatch, caplog):
        """Test async pull_model handles failed status code."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"

        with patch.object(gen, "_request_async", return_value=mock_response):
            await gen.pull_model_async()

        assert gen._model_pulled is False

    @pytest.mark.asyncio
    async def test_pull_model_async_exception(self, monkeypatch):
        """Test async pull_model handles exceptions."""
        gen = EmbeddingGenerator()

        with (
            patch.object(gen, "_request_async", side_effect=Exception("network error")),
            pytest.raises(OllamaUnavailableError),
        ):
            await gen.pull_model_async()


class TestEmbeddingGeneratorServiceRecovery:
    """Tests for service recovery methods."""

    def test_on_service_recovery(self, monkeypatch):
        """Test service recovery clears cache."""
        gen = EmbeddingGenerator()
        gen._connection_valid = True
        gen._connection_checked_at = 1000.0

        with patch.object(gen, "invalidate_connection_cache") as mock_invalidate:
            gen.on_service_recovery()

            # Parent class recovery should be called
            mock_invalidate.assert_called()

    @pytest.mark.asyncio
    async def test_on_service_recovery_async_with_client(self, monkeypatch):
        """Test async service recovery closes async client."""
        from unittest.mock import AsyncMock

        gen = EmbeddingGenerator()
        mock_async_client = MagicMock()
        mock_async_client.aclose = AsyncMock()
        gen._async_client = mock_async_client

        with patch.object(gen, "invalidate_connection_cache") as mock_invalidate:
            await gen.on_service_recovery_async()

            mock_async_client.aclose.assert_called_once()
            assert gen._async_client is None
            mock_invalidate.assert_called()

    @pytest.mark.asyncio
    async def test_on_service_recovery_async_without_client(self, monkeypatch):
        """Test async service recovery handles None client."""
        gen = EmbeddingGenerator()
        gen._async_client = None

        # Should not raise
        await gen.on_service_recovery_async()


class TestEmbeddingGeneratorEdgeCases:
    """Additional edge case tests."""

    def test_generate_with_unavailable_service(self, monkeypatch):
        """Test generate raises when service unavailable."""
        gen = EmbeddingGenerator()

        with (
            patch.object(gen, "validate_connection", return_value=False),
            pytest.raises(OllamaUnavailableError),
        ):
            gen.generate("test text")

    def test_generate_with_timeout(self, monkeypatch):
        """Test generate handles timeout exceptions."""
        gen = EmbeddingGenerator()

        with (
            patch.object(gen, "validate_connection", return_value=True),
            patch.object(gen, "_model_pulled", True),
            patch.object(
                gen, "_request", side_effect=httpx.TimeoutException("timeout")
            ),
            pytest.raises(EmbeddingGenerationError),
        ):
            gen.generate("test text")

    @pytest.mark.asyncio
    async def test_generate_async_with_unavailable_service(self, monkeypatch):
        """Test async generate raises when service unavailable."""
        gen = EmbeddingGenerator()

        with (
            patch.object(gen, "validate_connection_async", return_value=False),
            pytest.raises(OllamaUnavailableError),
        ):
            await gen.generate_async("test text")

    async def test_validate_connection_async_cache_hit(self, monkeypatch):
        """Test async validate_connection uses cache when valid."""
        import time

        gen = EmbeddingGenerator()
        gen._connection_valid = True
        gen._connection_checked_at = time.monotonic() - 10  # 10 seconds ago
        gen._connection_cache_ttl = 60.0  # 60 second cache

        # Cache should be used, no request made
        with patch.object(gen, "_request_async") as mock_request:
            result = await gen.validate_connection_async(force=False)

        mock_request.assert_not_called()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_model_info_async_exception(self, monkeypatch):
        """Test async get_model_info handles exceptions."""
        gen = EmbeddingGenerator()

        with patch.object(
            gen, "_request_async", side_effect=Exception("network error")
        ):
            info = await gen.get_model_info_async()

        assert info is None

    @pytest.mark.asyncio
    async def test_generate_async_with_model_pull(self, monkeypatch):
        """Test async generate pulls model if not pulled."""
        gen = EmbeddingGenerator()
        gen._model_pulled = False

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"embedding": [0.1] * 768}

        with (
            patch.object(gen, "validate_connection_async", return_value=True),
            patch.object(gen, "_request_async", return_value=mock_response),
            patch.object(gen, "pull_model_async") as mock_pull,
        ):
            result = await gen.generate_async("test")

            mock_pull.assert_called_once()
            assert result == [0.1] * 768

    @pytest.mark.asyncio
    async def test_validate_connection_async_forces_check(self, monkeypatch):
        """Test async validate_connection with force=True bypasses cache."""
        import time

        gen = EmbeddingGenerator()
        gen._connection_valid = True
        gen._connection_checked_at = time.monotonic()

        mock_response = MagicMock()
        mock_response.status_code = 200

        # force=True should make a request even with valid cache
        with patch.object(gen, "_request_async", return_value=mock_response):
            result = await gen.validate_connection_async(force=True)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_model_info_async_no_matching_model(self, monkeypatch):
        """Test async get_model_info when no model matches."""
        gen = EmbeddingGenerator()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "different-model:latest"}]
        }

        with patch.object(gen, "_request_async", return_value=mock_response):
            info = await gen.get_model_info_async()

        assert info is None
