"""Tests for LLM provider switching functionality.

This module tests that the LLM provider factory correctly selects and
instantiates different LLM providers based on environment configuration.
"""
from unittest.mock import patch, MagicMock, Mock

import pytest

from secondbrain.rag.providers.factory import LLMProviderFactory
from secondbrain.config import Config


class TestProviderSwitching:
    """Test LLM provider selection based on configuration."""

    def test_openai_provider_selection(self, monkeypatch):
        """Test OpenAI provider is selected when configured.

        Verifies that when SECONDBRAIN_LLM_PROVIDER=openai and
        SECONDBRAIN_OPENAI_API_KEY is set, the factory creates
        an OpenAIProvider instance with the correct model.
        """
        # Mock the OpenAI provider class before import happens
        mock_openai_class = Mock(return_value=Mock())
        
        with patch.dict('sys.modules', {'secondbrain.rag.providers.openai': MagicMock()}):
            with patch('secondbrain.rag.providers.openai.OpenAILLMProvider', mock_openai_class):
                monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'openai')
                monkeypatch.setenv('SECONDBRAIN_OPENAI_API_KEY', 'test-api-key')
                monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
                monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
                monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
                monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
                
                cfg = Config()
                provider = LLMProviderFactory.create_from_config(cfg)
                assert provider is not None
                mock_openai_class.assert_called_once()

    def test_anthropic_provider_selection(self, monkeypatch):
        """Test Anthropic provider is selected when configured.

        Verifies that when SECONDBRAIN_LLM_PROVIDER=anthropic and
        SECONDBRAIN_ANTHROPIC_API_KEY is set, the factory creates
        an AnthropicProvider instance with the correct model.
        """
        mock_anthropic_class = Mock(return_value=Mock())
        
        with patch.dict('sys.modules', {'secondbrain.rag.providers.anthropic': MagicMock()}):
            with patch('secondbrain.rag.providers.anthropic.AnthropicLLMProvider', mock_anthropic_class):
                monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'anthropic')
                monkeypatch.setenv('SECONDBRAIN_ANTHROPIC_API_KEY', 'test-api-key')
                monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
                monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
                monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
                monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
                
                cfg = Config()
                provider = LLMProviderFactory.create_from_config(cfg)
                assert provider is not None
                mock_anthropic_class.assert_called_once()

    def test_ollama_provider_selection(self, monkeypatch):
        """Test Ollama provider is selected when configured.

        Verifies that when SECONDBRAIN_LLM_PROVIDER=ollama,
        the factory creates an OllamaProvider instance.
        """
        monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'ollama')
        monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
        monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
        monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        
        cfg = Config()
        provider = LLMProviderFactory.create_from_config(cfg)
        assert provider is not None
        assert provider.__class__.__name__ == 'OllamaLLMProvider'

    def test_invalid_provider_raises_error(self, monkeypatch):
        """Test that invalid provider type raises ValueError.

        Verifies that when SECONDBRAIN_LLM_PROVIDER is set to an
        unsupported value, a ValueError is raised.
        """
        monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'invalid-provider')
        monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
        monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
        monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
        monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        
        # Create provider
        cfg = Config()
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMProviderFactory.create_from_config(cfg)
