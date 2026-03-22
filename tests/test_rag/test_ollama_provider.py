"""Unit tests for OllamaLLMProvider module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from ollama import ResponseError

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.providers.ollama import OllamaLLMProvider


@pytest.fixture
def provider(mock_client):
    """Create OllamaLLMProvider with test configuration."""
    with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
        yield OllamaLLMProvider(
            host="http://test:11434",
            model="test-model",
            temperature=0.5,
            max_tokens=1024,
            timeout=30,
        )


@pytest.fixture
def mock_client():
    """Mock Ollama Client."""
    mock = MagicMock()
    mock.chat.return_value = {"message": {"content": "Test response"}}
    mock.list.return_value = {"models": []}
    return mock


class TestOllamaProviderInit:
    """Tests for OllamaLLMProvider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        provider = OllamaLLMProvider()

        assert provider.host == "http://localhost:11434"
        assert provider.model == "llama3.2"
        assert provider.temperature == 0.1
        assert provider.max_tokens == 2048
        assert provider.timeout == 120

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        provider = OllamaLLMProvider(
            host="http://custom:11434",
            model="custom-model",
            temperature=0.8,
            max_tokens=512,
            timeout=60,
        )

        assert provider.host == "http://custom:11434"
        assert provider.model == "custom-model"
        assert provider.temperature == 0.8
        assert provider.max_tokens == 512
        assert provider.timeout == 60


class TestOllamaProviderGenerate:
    """Tests for OllamaLLMProvider.generate method."""

    def test_generate_success(self, provider, mock_client):
        """Test successful generation."""
        response = provider.generate("Test prompt")

        assert response == "Test response"
        mock_client.chat.assert_called_once()

    def test_generate_with_custom_temperature(self, provider, mock_client):
        """Test generation with custom temperature."""
        provider.generate("Test prompt", temperature=0.9)

        call_args = mock_client.chat.call_args
        assert call_args[1]["options"]["temperature"] == 0.9

    def test_generate_with_custom_max_tokens(self, provider, mock_client):
        """Test generation with custom max tokens."""
        provider.generate("Test prompt", max_tokens=256)

        call_args = mock_client.chat.call_args
        assert call_args[1]["options"]["num_predict"] == 256

    def test_generate_server_unavailable(self):
        """Test generation when server is unavailable."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.ConnectError("Connection failed")

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            with pytest.raises(ServiceUnavailableError, match="Ollama server"):
                provider.generate("Test prompt")

    def test_generate_timeout(self):
        """Test generation timeout."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.TimeoutException("Timeout")

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            with pytest.raises(ServiceUnavailableError, match="timed out"):
                provider.generate("Test prompt")

    def test_generate_model_not_found(self):
        """Test generation when model not found."""
        mock_client = MagicMock()
        mock_client.chat.side_effect = ResponseError("Model not found", 404)

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            with pytest.raises(RuntimeError, match="not found"):
                provider.generate("Test prompt")


class TestOllamaProviderAGenerate:
    """Tests for OllamaLLMProvider.agenerate method."""

    @pytest.mark.asyncio
    async def test_agenerate_success(self, provider, mock_client):
        """Test successful async generation."""
        response = await provider.agenerate("Test prompt")

        assert response == "Test response"

    @pytest.mark.asyncio
    async def test_agenerate_with_custom_params(self, provider, mock_client):
        """Test async generation with custom parameters."""
        response = await provider.agenerate(
            "Test prompt", temperature=0.7, max_tokens=512
        )

        assert response == "Test response"


class TestOllamaProviderHealthCheck:
    """Tests for OllamaLLMProvider.health_check method."""

    def test_health_check_success(self, provider, mock_client):
        """Test successful health check."""
        result = provider.health_check()

        assert result is True
        mock_client.list.assert_called_once()

    def test_health_check_connection_error(self):
        """Test health check when connection fails."""
        mock_client = MagicMock()
        mock_client.list.side_effect = httpx.ConnectError("Failed")

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            result = provider.health_check()

            assert result is False

    def test_health_check_timeout(self):
        """Test health check timeout."""
        mock_client = MagicMock()
        mock_client.list.side_effect = httpx.TimeoutException("Timeout")

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            result = provider.health_check()

            assert result is False


class TestOllamaProviderChat:
    """Tests for OllamaLLMProvider.chat method."""

    def test_chat_success(self, provider, mock_client):
        """Test successful chat."""
        messages = [{"role": "user", "content": "Hello"}]

        response = provider.chat(messages)

        assert response == "Test response"
        mock_client.chat.assert_called_once()

    def test_chat_with_history(self, provider, mock_client):
        """Test chat with conversation history."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"},
        ]

        response = provider.chat(messages)

        assert response == "Test response"

    def test_chat_server_unavailable(self):
        """Test chat when server is unavailable."""
        messages = [{"role": "user", "content": "Test"}]
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.ConnectError("Failed")

        with patch("secondbrain.rag.providers.ollama.Client", return_value=mock_client):
            provider = OllamaLLMProvider()

            with pytest.raises(ServiceUnavailableError):
                provider.chat(messages)


class TestOllamaProviderProperties:
    """Tests for OllamaLLMProvider properties."""

    def test_host_property(self, provider):
        """Test host property returns correct value."""
        assert provider.host == "http://test:11434"

    def test_model_property(self, provider):
        """Test model property returns correct value."""
        assert provider.model == "test-model"

    def test_temperature_property(self, provider):
        """Test temperature property returns correct value."""
        assert provider.temperature == 0.5

    def test_max_tokens_property(self, provider):
        """Test max_tokens property returns correct value."""
        assert provider.max_tokens == 1024

    def test_timeout_property(self, provider):
        """Test timeout property returns correct value."""
        assert provider.timeout == 30
