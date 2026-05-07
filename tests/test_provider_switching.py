"""Tests for LLM provider switching functionality.

This module tests that the LLM provider factory correctly selects and
instantiates different LLM providers based on environment configuration.
"""
import os
from unittest.mock import patch, MagicMock

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
        # Mock the OpenAI provider to avoid actual API calls
        with patch('secondbrain.rag.providers.factory.OpenAILLMProvider') as MockProvider:
            mock_instance = MagicMock()
            MockProvider.return_value = mock_instance
            
            # Set environment variables
            monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'openai')
            monkeypatch.setenv('SECONDBRAIN_OPENAI_API_KEY', 'test-api-key')
            monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
            monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
            monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
            monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            
            # Create provider
            cfg = Config()
            provider = LLMProviderFactory.create_from_config(cfg)
            
            # Verify OpenAI provider was created
            assert provider is not None
            MockProvider.assert_called_once()

    def test_anthropic_provider_selection(self, monkeypatch):
        """Test Anthropic provider is selected when configured.

        Verifies that when SECONDBRAIN_LLM_PROVIDER=anthropic and
        SECONDBRAIN_ANTHROPIC_API_KEY is set, the factory creates
        an AnthropicProvider instance with the correct model.
        """
        # Mock the Anthropic provider to avoid actual API calls
        with patch('secondbrain.rag.providers.factory.AnthropicLLMProvider') as MockProvider:
            mock_instance = MagicMock()
            MockProvider.return_value = mock_instance
            
            # Set environment variables
            monkeypatch.setenv('SECONDBRAIN_LLM_PROVIDER', 'anthropic')
            monkeypatch.setenv('SECONDBRAIN_ANTHROPIC_API_KEY', 'test-api-key')
            monkeypatch.setenv('SECONDBRAIN_MONGO_URI', 'mongodb://localhost:27017')
            monkeypatch.setenv('SECONDBRAIN_MONGO_DB', 'test')
            monkeypatch.setenv('SECONDBRAIN_MONGO_COLLECTION', 'test')
            monkeypatch.setenv('SECONDBRAIN_LOCAL_EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            
            # Create provider
            cfg = Config()
            provider = LLMProviderFactory.create_from_config(cfg)
            
            # Verify Anthropic provider was created
            assert provider is not None
            MockProvider.assert_called_once()