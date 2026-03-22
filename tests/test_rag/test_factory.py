"""Unit tests for LLMProviderFactory module."""

from __future__ import annotations

from unittest.mock import MagicMock

from secondbrain.rag.providers.factory import LLMProviderFactory
from secondbrain.rag.providers.ollama import OllamaLLMProvider


class TestLLMProviderFactory:
    """Tests for LLMProviderFactory class."""

    def test_create_ollama_default(self):
        """Test creating Ollama provider with defaults."""
        provider = LLMProviderFactory.create_ollama()

        assert isinstance(provider, OllamaLLMProvider)
        assert provider.host == "http://localhost:11434"
        assert provider.model == "llama2"
        assert provider.temperature == 0.7

    def test_create_ollama_custom(self):
        """Test creating Ollama provider with custom config."""
        provider = LLMProviderFactory.create_ollama(
            host="http://custom:11434",
            model="custom-model",
            temperature=0.8,
            timeout=60,
        )

        assert isinstance(provider, OllamaLLMProvider)
        assert provider.host == "http://custom:11434"
        assert provider.model == "custom-model"
        assert provider.temperature == 0.8
        assert provider.timeout == 60

    def test_create_from_config(self):
        """Test creating provider from config."""
        mock_config = MagicMock()
        mock_config.ollama_host = "http://config-host:11434"
        mock_config.llm_model = "config-model"
        mock_config.llm_temperature = 0.9
        mock_config.llm_timeout = 90

        provider = LLMProviderFactory.create_from_config(mock_config)

        assert isinstance(provider, OllamaLLMProvider)
        assert provider.host == "http://config-host:11434"
        assert provider.model == "config-model"
        assert provider.temperature == 0.9
        assert provider.timeout == 90
