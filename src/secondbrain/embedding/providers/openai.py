"""OpenAI embedding provider implementation for API-based embeddings.

Provides OpenAIEmbeddingProvider class that implements the EmbeddingProvider
protocol for using OpenAI API or OpenAI-compatible endpoints for embedding generation.
"""

from __future__ import annotations

import asyncio
import os

import httpx
from openai import APIError, AsyncOpenAI, OpenAI

from secondbrain.exceptions import ServiceUnavailableError

from ..interfaces import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API implementation of EmbeddingProvider protocol.

    Supports OpenAI embeddings API and any OpenAI-compatible endpoint
    (e.g., Azure OpenAI, local vLLM, custom embeddings API, etc.).

    Models supported:
    - text-embedding-ada-002 (1536 dimensions)
    - text-embedding-3-small (1536 dimensions, recommended)
    - text-embedding-3-large (3072 dimensions)

    Attributes:
        model: Model name to use for embeddings.
        api_key: OpenAI API key for authentication.
        api_base: Base URL for OpenAI-compatible API endpoints.
        timeout: Request timeout in seconds.
        dimensions: Output dimensions (only for text-embedding-3-* models).
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: int = 120,
        dimensions: int | None = None,
    ) -> None:
        """Initialize OpenAI embedding provider.

        Args:
            model: Model name (default: text-embedding-3-small).
            api_key: API key (defaults to SECONDBRAIN_EMBEDDING_API_KEY env var).
            api_base: Base URL for OpenAI-compatible API (optional).
            timeout: Request timeout in seconds (default: 120).
            dimensions: Output dimensions (only for text-embedding-3-* models).

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._timeout = timeout
        self._dimensions = dimensions

        # Get API key from parameter or environment (truly optional for OpenAI-compatible APIs)
        self._api_key = api_key or os.getenv("SECONDBRAIN_EMBEDDING_API_KEY")

        # Initialize clients - api_key is optional for OpenAI-compatible endpoints
        # If no API key provided, use a placeholder (custom endpoints may ignore it)
        client_kwargs: dict[str, str | httpx.Timeout] = {
            "timeout": httpx.Timeout(timeout),
        }
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        else:
            # Use placeholder for endpoints that don't require authentication
            client_kwargs["api_key"] = "no-api-key-provided"
        if api_base:
            client_kwargs["base_url"] = api_base

        self._client = OpenAI(**client_kwargs)  # type: ignore[arg-type]
        self._async_client = AsyncOpenAI(**client_kwargs)  # type: ignore[arg-type]

    def generate(self, text: str) -> list[float]:
        """Generate embedding for single text using OpenAI API.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.

        Raises:
            ServiceUnavailableError: If API is unreachable.
            RuntimeError: If embedding generation fails.
        """
        try:
            kwargs: dict[str, str | list[str] | int] = {
                "input": text,
                "model": self._model,
            }
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = self._client.embeddings.create(**kwargs)  # type: ignore[arg-type]
            embedding: list[float] = response.data[0].embedding
            return embedding

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API unreachable. "
                f"Ensure SECONDBRAIN_EMBEDDING_API_KEY is set correctly and network is available"
            ) from e
        except httpx.TimeoutException as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts using OpenAI API.

        OpenAI API supports batch requests (up to 2048 inputs for text-embedding-3-small).

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        try:
            kwargs: dict[str, str | list[str] | int] = {
                "input": valid_texts,
                "model": self._model,
            }
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = self._client.embeddings.create(**kwargs)  # type: ignore[arg-type]

            # Sort by index to maintain input order (API may return in any order)
            embeddings_sorted = sorted(response.data, key=lambda x: x.index)
            return [emb.embedding for emb in embeddings_sorted]

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API unreachable"
            ) from e
        except httpx.TimeoutException as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Batch embedding generation failed: {e}") from e

    async def generate_async(self, text: str) -> list[float]:
        """Async version of generate.

        Args:
            text: Input text to embed.

        Returns:
            List of floats representing the embedding vector.
        """
        try:
            kwargs: dict[str, str | list[str] | int] = {
                "input": text,
                "model": self._model,
            }
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = await self._async_client.embeddings.create(**kwargs)  # type: ignore[arg-type]
            embedding: list[float] = response.data[0].embedding
            return embedding

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API unreachable"
            ) from e
        except httpx.TimeoutException as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Async embedding generation failed: {e}") from e

    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Async version of generate_batch.

        Args:
            texts: List of input texts to embed.

        Returns:
            List of embedding vectors, one for each input text.
        """
        if not texts:
            return []

        # Filter out empty strings
        valid_texts = [t for t in texts if t.strip()]
        if not valid_texts:
            return [[] for _ in texts]

        try:
            kwargs: dict[str, str | list[str] | int] = {
                "input": valid_texts,
                "model": self._model,
            }
            if self._dimensions:
                kwargs["dimensions"] = self._dimensions

            response = await self._async_client.embeddings.create(**kwargs)  # type: ignore[arg-type]
            embeddings_sorted = sorted(response.data, key=lambda x: x.index)
            return [emb.embedding for emb in embeddings_sorted]

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API unreachable"
            ) from e
        except httpx.TimeoutException as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API request timed out after {self._timeout}s"
            ) from e
        except APIError as e:
            raise ServiceUnavailableError(
                "Embedding",
                f"OpenAI embeddings API error: {e.message if hasattr(e, 'message') else e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Async batch embedding generation failed: {e}") from e

    def validate_connection(self, force: bool = False) -> bool:
        """Check if OpenAI API is accessible.

        Args:
            force: If True, bypass cache and revalidate.

        Returns:
            True if API is accessible, False otherwise.
        """
        try:
            # Make a minimal request to check connectivity
            if self._client is not None:
                self._client.models.list()
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Close clients and release resources."""
        # OpenAI clients don't have explicit close methods, but we can dereference them
        # to allow garbage collection
        self._client = None  # type: ignore[assignment]
        self._async_client = None  # type: ignore[assignment]
        self._api_key = None
