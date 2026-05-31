"""Unit tests for AnthropicLLMProvider module.

Tests cover initialization, generation, error handling, and configuration
for the Anthropic LLM provider implementation.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIError

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.providers.anthropic import AnthropicLLMProvider


class TestAnthropicLLMProviderInit:
    """Tests for AnthropicLLMProvider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            provider = AnthropicLLMProvider()

            assert provider._model == "claude-3-sonnet-20240229"
            assert provider._temperature == 0.1
            assert provider._max_tokens == 2048
            assert provider._timeout == 120
            assert provider._api_key == "test-key"

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            provider = AnthropicLLMProvider(
                model="claude-3-opus-20240229",
                temperature=0.7,
                max_tokens=1024,
                timeout=60,
            )

            assert provider._model == "claude-3-opus-20240229"
            assert provider._temperature == 0.7
            assert provider._max_tokens == 1024
            assert provider._timeout == 60

    def test_init_with_api_key_parameter(self):
        """Test initialization with API key as parameter."""
        provider = AnthropicLLMProvider(api_key="direct-api-key")

        assert provider._api_key == "direct-api-key"

    def test_init_without_api_key_raises_error(self):
        """Test that initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Anthropic API key required"):
                AnthropicLLMProvider()

    def test_init_creates_clients(self):
        """Test that clients are created during initialization."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_sync:
                with patch("secondbrain.rag.providers.anthropic.AsyncAnthropic") as mock_async:
                    mock_sync.return_value = MagicMock()
                    mock_async.return_value = MagicMock()

                    provider = AnthropicLLMProvider()

                    mock_sync.assert_called_once()
                    mock_async.assert_called_once()
                    assert hasattr(provider, "_client")
                    assert hasattr(provider, "_async_client")


class TestAnthropicLLMProviderGenerate:
    """Tests for AnthropicLLMProvider.generate() method."""

    def test_generate_with_default_params(self):
        """Test generation with default temperature and max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Test response")]
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                response = provider.generate("Test prompt")

                assert response == "Test response"
                mock_client.messages.create.assert_called_once()

    def test_generate_with_custom_temperature(self):
        """Test generation with custom temperature."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Response")]
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                response = provider.generate("Test", temperature=0.8)

                call_kwargs = mock_client.messages.create.call_args[1]
                assert call_kwargs["temperature"] == 0.8

    def test_generate_with_custom_max_tokens(self):
        """Test generation with custom max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Response")]
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                response = provider.generate("Test", max_tokens=512)

                call_kwargs = mock_client.messages.create.call_args[1]
                assert call_kwargs["max_tokens"] == 512

    def test_generate_uses_default_temperature_when_not_specified(self):
        """Test that default temperature is used when not specified."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Response")]
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider(temperature=0.5)
                provider.generate("Test")

                call_kwargs = mock_client.messages.create.call_args[1]
                assert call_kwargs["temperature"] == 0.5

    def test_generate_raises_service_unavailable_on_api_error(self):
        """Test that APIError is converted to RuntimeError."""
        with patch.dict(os.environ, {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.anthropic.Anthropic") as mock_client_class:
                mock_client = MagicMock()
                mock_request = MagicMock()
                mock_client.messages.create.side_effect = APIError(
                    message="API Error",
                    request=mock_request,
                    body={}
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

