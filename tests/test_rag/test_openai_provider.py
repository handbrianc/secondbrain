"""Unit tests for OpenAILLMProvider module.

Tests cover initialization, generation, error handling, and configuration
for the OpenAI LLM provider implementation.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIError

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.providers.openai import OpenAILLMProvider


class TestOpenAILLMProviderInit:
    """Tests for OpenAILLMProvider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        # Mock the API key environment variable
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            provider = OpenAILLMProvider()

            assert provider._model == "gpt-4o-mini"
            assert provider._temperature == 0.1
            assert provider._max_tokens == 2048
            assert provider._timeout == 120
            assert provider._api_key == "test-key"

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            provider = OpenAILLMProvider(
                model="gpt-4",
                temperature=0.7,
                max_tokens=1024,
                timeout=60,
            )

            assert provider._model == "gpt-4"
            assert provider._temperature == 0.7
            assert provider._max_tokens == 1024
            assert provider._timeout == 60

    def test_init_with_api_key_parameter(self):
        """Test initialization with API key as parameter."""
        provider = OpenAILLMProvider(api_key="direct-api-key")

        assert provider._api_key == "direct-api-key"

    def test_init_without_api_key_raises_error(self):
        """Test that initialization fails without API key."""
        # Ensure no API key in environment
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI API key required"):
                OpenAILLMProvider()

    def test_init_creates_clients(self):
        """Test that clients are created during initialization."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_sync:
                with patch("secondbrain.rag.providers.openai.AsyncOpenAI") as mock_async:
                    mock_sync.return_value = MagicMock()
                    mock_async.return_value = MagicMock()

                    provider = OpenAILLMProvider()

                    mock_sync.assert_called_once()
                    mock_async.assert_called_once()
                    assert hasattr(provider, "_client")
                    assert hasattr(provider, "_async_client")


class TestOpenAILLMProviderGenerate:
    """Tests for OpenAILLMProvider.generate() method."""

    def test_generate_with_default_params(self):
        """Test generation with default temperature and max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test prompt")

                assert response == "Test response"
                mock_client.chat.completions.create.assert_called_once()

    def test_generate_with_custom_temperature(self):
        """Test generation with custom temperature."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test", temperature=0.8)

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.8

    def test_generate_with_custom_max_tokens(self):
        """Test generation with custom max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test", max_tokens=512)

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["max_tokens"] == 512

    def test_generate_uses_default_temperature_when_not_specified(self):
        """Test that default temperature is used when not specified."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(temperature=0.5)
                provider.generate("Test")

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.5

    def test_generate_raises_service_unavailable_on_api_error(self):
        """Test that APIError is converted to ServiceUnavailableError."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                mock_request = MagicMock()
                mock_client.chat.completions.create.side_effect = APIError(
                    message="API Error",
                    request=mock_request,
                    body={}
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(ServiceUnavailableError):
                    provider.generate("Test prompt")


class TestOpenAILLMProviderAGenerate:
    """Tests for OpenAILLMProvider agenerate_async method."""

    @pytest.mark.asyncio
    async def test_agenerate_async_success(self):
        """Test successful async generation."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.AsyncOpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Test response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = await provider.generate_async("Test prompt")

                assert response == "Test response"

    @pytest.mark.asyncio
    async def test_agenerate_async_with_custom_params(self):
        """Test async generation with custom parameters."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.AsyncOpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=MagicMock(content="Response"))]
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = await provider.generate_async("Test", temperature=0.8, max_tokens=512)

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.8
                assert call_kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_agenerate_async_raises_service_unavailable_on_connect_error(self):
        """Test that ConnectError raises ServiceUnavailableError."""
        import httpx

        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.AsyncOpenAI") as mock_client_class:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=httpx.ConnectError("Connection failed")
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(ServiceUnavailableError, match="OpenAI API unreachable"):
                    await provider.generate_async("Test prompt")

    @pytest.mark.asyncio
    async def test_agenerate_async_raises_service_unavailable_on_api_error(self):
        """Test that APIError raises ServiceUnavailableError."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.AsyncOpenAI") as mock_client_class:
                mock_client = MagicMock()
                mock_request = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=APIError(
                        message="API Error",
                        request=mock_request,
                        body={}
                    )
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(ServiceUnavailableError, match="OpenAI API error"):
                    await provider.generate_async("Test prompt")
