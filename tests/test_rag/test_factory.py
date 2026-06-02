"""Unit tests for LLMProviderFactory module."""

from __future__ import annotations

from unittest.mock import MagicMock

from secondbrain.rag.providers.factory import LLMProviderFactory
from secondbrain.rag.providers.openai import OpenAILLMProvider
from secondbrain.rag.providers.anthropic import AnthropicLLMProvider


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory class."""

    def test_create_openai_default(self):
        """Test creating OpenAI provider with defaults."""
        provider = LLMProviderFactory.create_openai(
            api_key="test-key",
            base_url="http://localhost:8080/v1",
        )

        assert isinstance(provider, OpenAILLMProvider)
        assert provider.base_url == "http://localhost:8080/v1"
        assert provider.model == "gpt-4o-mini"
        assert provider.temperature == 0.7

    def test_create_openai_custom(self):
        """Test creating OpenAI provider with custom config."""
        provider = LLMProviderFactory.create_openai(
            api_key="custom-key",
            base_url="http://custom:8080/v1",
            model="gpt-4-turbo",
            temperature=0.8,
            timeout=60,
        )

        assert isinstance(provider, OpenAILLMProvider)
        assert provider.base_url == "http://custom:8080/v1"
        assert provider.model == "gpt-4-turbo"
        assert provider.temperature == 0.8
        assert provider.timeout == 60

    def test_create_anthropic_default(self):
        """Test creating Anthropic provider with defaults."""
        provider = LLMProviderFactory.create_anthropic(
            api_key="test-key",
        )

        assert isinstance(provider, AnthropicLLMProvider)
        assert provider.model == "claude-3-haiku-20240307"
        assert provider.temperature == 0.7

    def test_create_anthropic_custom(self):
        """Test creating Anthropic provider with custom config."""
        provider = LLMProviderFactory.create_anthropic(
            api_key="custom-key",
            model="claude-3-sonnet-20240229",
            temperature=0.8,
            timeout=60,
        )

        assert isinstance(provider, AnthropicLLMProvider)
        assert provider.model == "claude-3-sonnet-20240229"
        assert provider.temperature == 0.8
        assert provider.timeout == 60

    def test_create_from_config_openai(self):
        """Test creating OpenAI provider from config."""
        mock_config = MagicMock()
        mock_config.llm_provider = "openai"
        mock_config.openai_base_url = "http://config-host:8080/v1"
        mock_config.openai_api_key = "config-key"
        mock_config.llm_model = "config-model"
        mock_config.llm_temperature = 0.9
        mock_config.llm_timeout = 90

        provider = LLMProviderFactory.create_from_config(mock_config)

        assert isinstance(provider, OpenAILLMProvider)
        assert provider.base_url == "http://config-host:8080/v1"
        assert provider.model == "config-model"
        assert provider.temperature == 0.9
        assert provider.timeout == 90

    def test_create_from_config_anthropic(self):
        """Test creating Anthropic provider from config."""
        mock_config = MagicMock()
        mock_config.llm_provider = "anthropic"
        mock_config.anthropic_api_key = "config-key"
        mock_config.llm_model = "claude-3-opus-20240229"
        mock_config.llm_temperature = 0.5
        mock_config.llm_timeout = 120

        provider = LLMProviderFactory.create_from_config(mock_config)

        assert isinstance(provider, AnthropicLLMProvider)
        assert provider.model == "claude-3-opus-20240229"
        assert provider.temperature == 0.5
        assert provider.timeout == 120

    def test_create_from_config_default_falls_back_to_openai(self):
        """Test that default provider is OpenAI when not specified."""
        mock_config = MagicMock()
        mock_config.llm_provider = "openai"  # Default
        mock_config.openai_base_url = "http://localhost:8080/v1"
        mock_config.openai_api_key = "test-key"
        mock_config.llm_model = "gpt-4o-mini"
        mock_config.llm_temperature = 0.7
        mock_config.llm_timeout = 30

        provider = LLMProviderFactory.create_from_config(mock_config)

        assert isinstance(provider, OpenAILLMProvider)
