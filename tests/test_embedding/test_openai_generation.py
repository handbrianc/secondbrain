"""Tests for OpenAI embedding provider.

These tests verify the OpenAIEmbeddingProvider implementation including:
- API key handling (optional vs required)
- OpenAI-compatible endpoint support
- Batch and async generation
- Error handling scenarios
- Dimension parameter support
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest
from openai import APIError

from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider
from secondbrain.exceptions import ServiceUnavailableError


class TestOpenAIEmbeddingProviderInit:
    """Tests for OpenAIEmbeddingProvider initialization."""

    def test_init_with_api_key(self) -> None:
        """Test initialization with explicit API key."""
        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            api_key="test-key-123",
            dimensions=1536,
        )
        assert provider._model == "text-embedding-3-small"
        assert provider._api_key == "test-key-123"
        assert provider._dimensions == 1536

    def test_init_without_api_key_uses_env_var(self) -> None:
        """Test initialization uses environment variable when no API key provided."""
        with patch.dict(os.environ, {"SECONDBRAIN_EMBEDDING_API_KEY": "env-key"}):
            provider = OpenAIEmbeddingProvider()
            assert provider._api_key == "env-key"

    def test_init_without_api_key_is_truly_optional(self) -> None:
        """Test that API key is truly optional for OpenAI-compatible endpoints."""
        # Should NOT raise ValueError when no API key is provided
        provider = OpenAIEmbeddingProvider(
            api_key=None,
            api_base="http://localhost:8000/v1",
        )
        assert provider._api_key is None
        # Client should be created without api_key
        assert provider._client is not None

    def test_init_without_api_key_or_env_var(self) -> None:
        """Test initialization without any API key (for local endpoints)."""
        # Remove any existing env var
        with patch.dict(os.environ, {}, clear=True):
            provider = OpenAIEmbeddingProvider(
                api_base="http://localhost:8000/v1",
            )
            assert provider._api_key is None

    def test_init_with_custom_api_base(self) -> None:
        """Test initialization with custom API base URL."""
        provider = OpenAIEmbeddingProvider(
            api_key="test-key",
            api_base="http://custom-api:8000/v1",
        )
        # Verify provider was created successfully with custom base
        assert provider._client is not None

    def test_init_with_dimensions(self) -> None:
        """Test initialization with custom dimensions."""
        provider = OpenAIEmbeddingProvider(
            model="text-embedding-3-small",
            dimensions=256,
        )
        assert provider._dimensions == 256


class TestOpenAIEmbeddingProviderGenerate:
    """Tests for OpenAIEmbeddingProvider.generate method."""

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_success(self, mock_openai_class: MagicMock) -> None:
        """Test successful embedding generation."""
        # Setup mock response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3], index=0)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embedding = provider.generate("test text")

        assert embedding == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once_with(
            input="test text",
            model="text-embedding-3-small",
        )

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_with_dimensions(self, mock_openai_class: MagicMock) -> None:
        """Test embedding generation with dimensions parameter."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2], index=0)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(
            api_key="test-key",
            dimensions=256,
        )
        embedding = provider.generate("test text")

        mock_client.embeddings.create.assert_called_once_with(
            input="test text",
            model="text-embedding-3-small",
            dimensions=256,
        )

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_connect_error(self, mock_openai_class: MagicMock) -> None:
        """Test handling of connection errors."""
        # Setup mock client that raises ConnectError on embeddings.create
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = httpx.ConnectError("Connection failed")
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")

        with pytest.raises(ServiceUnavailableError, match="OpenAI embeddings API unreachable"):
            provider.generate("test text")

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_timeout_error(self, mock_openai_class: MagicMock) -> None:
        """Test handling of timeout errors."""
        # Setup mock client that raises TimeoutException on embeddings.create
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = httpx.TimeoutException("Timeout")
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")

        with pytest.raises(ServiceUnavailableError, match="timed out"):
            provider.generate("test text")

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_api_error(self, mock_openai_class: MagicMock) -> None:
        """Test handling of API errors."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = APIError(
            message="API error",
            request=MagicMock(),
            body={"error": "Invalid request"},
        )
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")

        with pytest.raises(ServiceUnavailableError, match="OpenAI embeddings API error"):
            provider.generate("test text")


class TestOpenAIEmbeddingProviderGenerateBatch:
    """Tests for OpenAIEmbeddingProvider.generate_batch method."""

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_batch_success(self, mock_openai_class: MagicMock) -> None:
        """Test successful batch embedding generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2], index=0),
            MagicMock(embedding=[0.3, 0.4], index=1),
            MagicMock(embedding=[0.5, 0.6], index=2),
        ]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embeddings = provider.generate_batch(["text1", "text2", "text3"])

        assert len(embeddings) == 3
        assert embeddings == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_client.embeddings.create.assert_called_once()
        # Verify input was passed as list
        call_args = mock_client.embeddings.create.call_args
        assert isinstance(call_args.kwargs["input"], list)
        assert len(call_args.kwargs["input"]) == 3

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_batch_empty_list(self, mock_openai_class: MagicMock) -> None:
        """Test batch generation with empty list."""
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embeddings = provider.generate_batch([])

        assert embeddings == []
        mock_openai_class.return_value.embeddings.create.assert_not_called()

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_batch_filters_empty_strings(self, mock_openai_class: MagicMock) -> None:
        """Test that empty strings are filtered from batch."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2], index=0)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embeddings = provider.generate_batch(["text1", "", "text2", "   "])

        # Should only generate embeddings for non-empty strings
        call_args = mock_client.embeddings.create.call_args
        assert len(call_args.kwargs["input"]) == 2  # Only "text1" and "text2"

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_batch_order_maintained(self, mock_openai_class: MagicMock) -> None:
        """Test that batch results maintain input order."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        # API may return in any order, so simulate that
        mock_response.data = [
            MagicMock(embedding=[0.3, 0.4], index=1),  # Second item
            MagicMock(embedding=[0.1, 0.2], index=0),  # First item
            MagicMock(embedding=[0.5, 0.6], index=2),  # Third item
        ]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embeddings = provider.generate_batch(["text1", "text2", "text3"])

        # Should be sorted by index to maintain order
        assert embeddings == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]


class TestOpenAIEmbeddingProviderAsync:
    """Tests for async methods."""

    @patch("secondbrain.embedding.providers.openai.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_async_success(self, mock_async_openai: MagicMock) -> None:
        """Test async embedding generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3], index=0)]
        
        # Mock async method
        async def mock_create(**kwargs):
            return mock_response
        
        mock_client.embeddings.create = mock_create
        mock_async_openai.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embedding = await provider.generate_async("test text")

        assert embedding == [0.1, 0.2, 0.3]

    @patch("secondbrain.embedding.providers.openai.AsyncOpenAI")
    @pytest.mark.asyncio
    async def test_generate_batch_async_success(self, mock_async_openai: MagicMock) -> None:
        """Test async batch embedding generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2], index=0),
            MagicMock(embedding=[0.3, 0.4], index=1),
        ]
        
        async def mock_create(**kwargs):
            return mock_response
        
        mock_client.embeddings.create = mock_create
        mock_async_openai.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        embeddings = await provider.generate_batch_async(["text1", "text2"])

        assert len(embeddings) == 2
        assert embeddings == [[0.1, 0.2], [0.3, 0.4]]


class TestOpenAIEmbeddingProviderValidateConnection:
    """Tests for validate_connection method."""

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_validate_connection_success(self, mock_openai_class: MagicMock) -> None:
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        result = provider.validate_connection()

        assert result is True
        mock_client.models.list.assert_called_once()

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_validate_connection_failure(self, mock_openai_class: MagicMock) -> None:
        """Test connection validation failure."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = httpx.ConnectError("Connection failed")
        mock_openai_class.return_value = mock_client

        provider = OpenAIEmbeddingProvider(api_key="test-key")
        result = provider.validate_connection()

        assert result is False


class TestOpenAIEmbeddingProviderClose:
    """Tests for close method."""

    def test_close_sets_clients_to_none(self) -> None:
        """Test that close sets clients to None."""
        provider = OpenAIEmbeddingProvider(api_key="test-key")
        
        # Verify clients exist
        assert provider._client is not None
        assert provider._async_client is not None
        
        provider.close()
        
        assert provider._client is None
        assert provider._async_client is None
        assert provider._api_key is None


class TestOpenAIEmbeddingProviderNoApiKey:
    """Tests for OpenAI provider without API key (for local endpoints)."""

    @patch("secondbrain.embedding.providers.openai.OpenAI")
    def test_generate_without_api_key(self, mock_openai_class: MagicMock) -> None:
        """Test embedding generation without API key (local endpoint)."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3], index=0)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # Create provider without API key
        provider = OpenAIEmbeddingProvider(
            api_key=None,
            api_base="http://localhost:8000/v1",
        )
        
        # Should work without API key (uses placeholder)
        embedding = provider.generate("test text")
        
        assert embedding == [0.1, 0.2, 0.3]
        # Verify placeholder api_key was passed (required by OpenAI client)
        call_kwargs = mock_openai_class.call_args.kwargs
        assert call_kwargs.get("api_key") == "no-api-key-provided"
        assert call_kwargs.get("base_url").__str__().endswith("8000/v1")
