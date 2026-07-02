"""Unit tests for rag.factory module.

This module tests the factory functions in src/secondbrain/rag/factory.py
which currently has 0% test coverage.
"""

from unittest.mock import MagicMock, patch

import pytest

from secondbrain.conversation import QueryRewriter
from secondbrain.rag.factory import create_llm_provider, create_query_rewriter
from secondbrain.rag.interfaces import LocalLLMProvider


class TestCreateLLMProvider:
    """Tests for create_llm_provider() function."""

    def test_create_llm_provider_success(self):
        """Test successful LLM provider creation from config."""
        # Mock the config and factory
        mock_config = MagicMock()
        mock_provider = MagicMock(spec=LocalLLMProvider)

        with patch("secondbrain.rag.factory.config", return_value=mock_config):
            with patch("secondbrain.rag.factory.LLMProviderFactory") as mock_factory:
                mock_factory.create_from_config.return_value = mock_provider

                # Call the function
                result = create_llm_provider()

                # Verify
                assert result is mock_provider
                mock_factory.create_from_config.assert_called_once_with(mock_config)

    def test_create_llm_provider_raises_value_error_on_invalid_provider(self):
        """Test that ValueError is raised when provider type is invalid."""
        mock_config = MagicMock()

        with patch("secondbrain.rag.factory.config", return_value=mock_config):
            with patch("secondbrain.rag.factory.LLMProviderFactory") as mock_factory:
                mock_factory.create_from_config.side_effect = ValueError(
                    "Invalid provider type"
                )

                # Verify ValueError is raised with helpful message
                with pytest.raises(ValueError, match="Failed to create LLM provider"):
                    create_llm_provider()

    def test_create_llm_provider_raises_runtime_error_on_initialization_failure(self):
        """Test that RuntimeError is raised when provider initialization fails."""
        mock_config = MagicMock()

        with patch("secondbrain.rag.factory.config", return_value=mock_config):
            with patch("secondbrain.rag.factory.LLMProviderFactory") as mock_factory:
                mock_factory.create_from_config.side_effect = Exception(
                    "Initialization failed"
                )

                # Verify RuntimeError is raised with helpful message
                with pytest.raises(
                    RuntimeError, match="Failed to initialize LLM provider"
                ):
                    create_llm_provider()

    def test_create_llm_provider_wraps_exceptions_properly(self):
        """Test that original exceptions are properly chained."""
        mock_config = MagicMock()
        original_error = ValueError("Original error")

        with patch("secondbrain.rag.factory.config", return_value=mock_config):
            with patch("secondbrain.rag.factory.LLMProviderFactory") as mock_factory:
                mock_factory.create_from_config.side_effect = original_error

                with pytest.raises(ValueError) as exc_info:
                    create_llm_provider()

                # Verify exception chaining
                assert exc_info.value.__cause__ is original_error


class TestCreateQueryRewriter:
    """Tests for create_query_rewriter() function."""

    def test_create_query_rewriter_success(self):
        """Test successful QueryRewriter creation."""
        mock_provider = MagicMock(spec=LocalLLMProvider)

        with patch("secondbrain.rag.factory.QueryRewriter") as mock_rewriter_class:
            mock_rewriter = MagicMock(spec=QueryRewriter)
            mock_rewriter_class.return_value = mock_rewriter

            # Call the function
            result = create_query_rewriter(mock_provider)

            # Verify
            assert result is mock_rewriter
            mock_rewriter_class.assert_called_once_with(llm_provider=mock_provider)

    def test_create_query_rewriter_raises_runtime_error_on_failure(self):
        """Test that RuntimeError is raised when rewriter creation fails."""
        mock_provider = MagicMock(spec=LocalLLMProvider)

        with patch("secondbrain.rag.factory.QueryRewriter") as mock_rewriter_class:
            mock_rewriter_class.side_effect = Exception("Rewriter creation failed")

            # Verify RuntimeError is raised with helpful message
            with pytest.raises(RuntimeError, match="Failed to create query rewriter"):
                create_query_rewriter(mock_provider)

    def test_create_query_rewriter_wraps_exceptions_properly(self):
        """Test that original exceptions are properly chained."""
        mock_provider = MagicMock(spec=LocalLLMProvider)
        original_error = ValueError("Original error")

        with patch("secondbrain.rag.factory.QueryRewriter") as mock_rewriter_class:
            mock_rewriter_class.side_effect = original_error

            with pytest.raises(RuntimeError) as exc_info:
                create_query_rewriter(mock_provider)

            # Verify exception chaining
            assert exc_info.value.__cause__ is original_error


class TestFactoryIntegration:
    """Integration tests for factory functions."""

    def test_create_full_pipeline(self):
        """Test creating both provider and rewriter together."""
        mock_config = MagicMock()
        mock_provider = MagicMock(spec=LocalLLMProvider)
        mock_rewriter = MagicMock(spec=QueryRewriter)

        with patch("secondbrain.rag.factory.config", return_value=mock_config):
            with patch("secondbrain.rag.factory.LLMProviderFactory") as mock_factory:
                with patch(
                    "secondbrain.rag.factory.QueryRewriter"
                ) as mock_rewriter_class:
                    mock_factory.create_from_config.return_value = mock_provider
                    mock_rewriter_class.return_value = mock_rewriter

                    # Create both components
                    provider = create_llm_provider()
                    rewriter = create_query_rewriter(provider)

                    # Verify both were created successfully
                    assert provider is mock_provider
                    assert rewriter is mock_rewriter
