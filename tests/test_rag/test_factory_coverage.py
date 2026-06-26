"""Comprehensive tests for RAG factory module.

Target: 80% coverage for src/secondbrain/rag/factory.py (currently 0%)

This module tests all factory functions for creating RAG pipeline components:
- create_llm_provider() - Create LLM provider from config
- create_query_rewriter() - Create query rewriter with LLM provider
"""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.rag.factory import create_llm_provider, create_query_rewriter
from secondbrain.rag.interfaces import LocalLLMProvider


class TestCreateLLMProvider:
    """Tests for create_llm_provider factory function."""

    @patch("secondbrain.rag.factory.config")
    @patch("secondbrain.rag.factory.LLMProviderFactory")
    def test_creates_provider_successfully(self, mock_factory, mock_config):
        """Test factory creates provider when configuration is valid."""
        # Setup
        mock_cfg = MagicMock()
        mock_config.return_value = mock_cfg

        mock_provider = MagicMock(spec=LocalLLMProvider)
        mock_factory.create_from_config.return_value = mock_provider

        # Execute
        result = create_llm_provider()

        # Assert
        mock_config.assert_called_once()
        mock_factory.create_from_config.assert_called_once_with(mock_cfg)
        assert result == mock_provider

    @patch("secondbrain.rag.factory.config")
    @patch("secondbrain.rag.factory.LLMProviderFactory")
    def test_handles_invalid_provider_type(self, mock_factory, mock_config):
        """Test factory raises ValueError for invalid provider type."""
        # Setup
        mock_cfg = MagicMock()
        mock_config.return_value = mock_cfg
        mock_factory.create_from_config.side_effect = ValueError(
            "Unsupported provider type"
        )

        # Execute & Assert
        with pytest.raises(ValueError) as exc_info:
            create_llm_provider()

        assert "Failed to create LLM provider" in str(exc_info.value)
        assert "SECONDBRAIN_LLM_PROVIDER" in str(exc_info.value)

    @patch("secondbrain.rag.factory.config")
    @patch("secondbrain.rag.factory.LLMProviderFactory")
    def test_handles_initialization_error(self, mock_factory, mock_config):
        """Test factory raises RuntimeError for initialization failures."""
        # Setup
        mock_cfg = MagicMock()
        mock_config.return_value = mock_cfg
        mock_factory.create_from_config.side_effect = Exception(
            "Initialization failed"
        )

        # Execute & Assert
        with pytest.raises(RuntimeError) as exc_info:
            create_llm_provider()

        assert "Failed to initialize LLM provider" in str(exc_info.value)


class TestCreateQueryRewriter:
    """Tests for create_query_rewriter factory function."""

    def test_creates_query_rewriter_successfully(self):
        """Test factory creates query rewriter with valid provider."""
        # Setup
        mock_provider = MagicMock(spec=LocalLLMProvider)

        with patch("secondbrain.rag.factory.QueryRewriter") as MockQR:
            mock_rewriter = MagicMock()
            MockQR.return_value = mock_rewriter

            # Execute
            result = create_query_rewriter(mock_provider)

            # Assert
            MockQR.assert_called_once_with(llm_provider=mock_provider)
            assert result == mock_rewriter

    def test_handles_rewriter_creation_error(self):
        """Test factory raises RuntimeError when rewriter creation fails."""
        # Setup
        mock_provider = MagicMock(spec=LocalLLMProvider)

        with patch("secondbrain.rag.factory.QueryRewriter") as MockQR:
            MockQR.side_effect = Exception("Rewriter creation failed")

            # Execute & Assert
            with pytest.raises(RuntimeError) as exc_info:
                create_query_rewriter(mock_provider)

            assert "Failed to create query rewriter" in str(exc_info.value)


class TestFactoryModuleExports:
    """Tests for factory module public API."""

    def test_create_llm_provider_in_all(self):
        """Test create_llm_provider is exported."""
        from secondbrain.rag import factory
        assert "create_llm_provider" in factory.__all__

    def test_create_query_rewriter_in_all(self):
        """Test create_query_rewriter is exported."""
        from secondbrain.rag import factory
        assert "create_query_rewriter" in factory.__all__
