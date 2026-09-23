"""Unit tests for OpenAIEmbeddingProvider error mapping.

Verifies that openai SDK transport errors (connection failure, timeout) and
generic API errors are converted to ServiceUnavailableError after the openai
3.x HTTPX2 migration, where legacy httpx exceptions no longer surface.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, APIError, APITimeoutError

from secondbrain.embedding.providers.openai import OpenAIEmbeddingProvider
from secondbrain.exceptions import ServiceUnavailableError


def _provider() -> OpenAIEmbeddingProvider:
    with patch.dict(
        os.environ, {"SECONDBRAIN_EMBEDDING_API_KEY": "test-key"}, clear=True
    ):
        return OpenAIEmbeddingProvider()


class TestOpenAIEmbeddingProviderErrorMapping:
    """Tests for transport-error to ServiceUnavailableError conversion."""

    def test_generate_raises_service_unavailable_on_connection_error(self):
        provider = _provider()
        provider._client = MagicMock()
        provider._client.embeddings.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(ServiceUnavailableError, match="unreachable"):
            provider.generate("text")

    def test_generate_raises_service_unavailable_on_timeout_error(self):
        provider = _provider()
        provider._client = MagicMock()
        provider._client.embeddings.create.side_effect = APITimeoutError(
            request=MagicMock()
        )

        with pytest.raises(ServiceUnavailableError, match="timed out after"):
            provider.generate("text")

    def test_generate_raises_service_unavailable_on_api_error(self):
        provider = _provider()
        provider._client = MagicMock()
        provider._client.embeddings.create.side_effect = APIError(
            message="API Error", request=MagicMock(), body={}
        )

        with pytest.raises(ServiceUnavailableError, match="embeddings API error"):
            provider.generate("text")

    def test_generate_batch_raises_service_unavailable_on_connection_error(self):
        provider = _provider()
        provider._client = MagicMock()
        provider._client.embeddings.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with pytest.raises(ServiceUnavailableError, match="unreachable"):
            provider.generate_batch(["a", "b"])

    def test_generate_batch_raises_service_unavailable_on_timeout_error(self):
        provider = _provider()
        provider._client = MagicMock()
        provider._client.embeddings.create.side_effect = APITimeoutError(
            request=MagicMock()
        )

        with pytest.raises(ServiceUnavailableError, match="timed out after"):
            provider.generate_batch(["a", "b"])

    @pytest.mark.asyncio
    async def test_generate_async_raises_service_unavailable_on_connection_error(self):
        provider = _provider()
        provider._async_client = MagicMock()
        provider._async_client.embeddings.create = _async_side_effect(
            APIConnectionError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError, match="unreachable"):
            await provider.generate_async("text")

    @pytest.mark.asyncio
    async def test_generate_async_raises_service_unavailable_on_timeout_error(self):
        provider = _provider()
        provider._async_client = MagicMock()
        provider._async_client.embeddings.create = _async_side_effect(
            APITimeoutError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError, match="timed out after"):
            await provider.generate_async("text")

    @pytest.mark.asyncio
    async def test_generate_batch_async_raises_service_unavailable_on_timeout_error(
        self,
    ):
        provider = _provider()
        provider._async_client = MagicMock()
        provider._async_client.embeddings.create = _async_side_effect(
            APITimeoutError(request=MagicMock())
        )

        with pytest.raises(ServiceUnavailableError, match="timed out after"):
            await provider.generate_batch_async(["a", "b"])


def _async_side_effect(exc: Exception):
    from unittest.mock import AsyncMock

    return AsyncMock(side_effect=exc)
