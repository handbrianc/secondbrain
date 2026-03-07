"""Embedding generation module for Ollama integration."""

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

import httpx
from typing_extensions import TypedDict

from secondbrain.config import get_config
from secondbrain.exceptions import (
    EmbeddingGenerationError,
    OllamaUnavailableError,
)
from secondbrain.utils.connections import (
    ServiceUnavailableError,
    ValidatableService,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API requests.

    Implements sliding window rate limiting with configurable max requests
    and time window. Provides both synchronous and asynchronous interfaces.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float | None = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window. If None, uses config.
            window_seconds: Time window in seconds. If None, uses config.
        """
        config = get_config()
        self.max_requests: int = (
            max_requests if max_requests is not None else config.rate_limit_max_requests
        )
        self.window_seconds: float = (
            window_seconds
            if window_seconds is not None
            else config.rate_limit_window_seconds
        )
        self._lock = Lock()
        self._async_lock = asyncio.Lock()
        self._requests: list[float] = []

    def acquire(self) -> None:
        """Acquire rate limit token, blocking if necessary."""
        current_time = time.time()

        with self._lock:
            self._requests[:] = [
                t for t in self._requests if current_time - t < self.window_seconds
            ]

            while len(self._requests) >= self.max_requests:
                oldest = min(self._requests)
                sleep_time = self.window_seconds - (current_time - oldest)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                current_time = time.time()
                self._requests[:] = [
                    t for t in self._requests if current_time - t < self.window_seconds
                ]

            self._requests.append(current_time)

    async def acquire_async(self) -> None:
        """Acquire rate limit token asynchronously, awaiting if necessary.

        Uses asyncio.Lock for thread-safe async operations.
        """
        current_time = time.time()

        async with self._async_lock:
            self._requests[:] = [
                t for t in self._requests if current_time - t < self.window_seconds
            ]

            while len(self._requests) >= self.max_requests:
                oldest = min(self._requests)
                sleep_time = self.window_seconds - (current_time - oldest)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                current_time = time.time()
                self._requests[:] = [
                    t for t in self._requests if current_time - t < self.window_seconds
                ]

            self._requests.append(current_time)


class EmbeddingResult(TypedDict):
    """Typed dictionary for embedding result.

    Attributes:
        embedding: List of float values representing the embedding vector.
    """

    embedding: list[float]


class EmbeddingGenerator(ValidatableService):
    """Generates embeddings using Ollama API.

    Uses ValidatableService base class for thread-safe connection validation
    with TTL caching.
    """

    def __init__(
        self,
        model: str | None = None,
        ollama_url: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the embedding generator.

        Args:
            model: Model name to use. If None, uses config default.
            ollama_url: Ollama API URL. If None, uses config default.
            rate_limiter: Optional RateLimiter instance. If None, creates new one.
        """
        config = get_config()
        self.model = model or config.model
        self.ollama_url = ollama_url or config.ollama_url
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._model_pulled = False
        config = get_config()
        self._rate_limiter = rate_limiter or RateLimiter(
            max_requests=config.rate_limit_max_requests,
            window_seconds=config.rate_limit_window_seconds,
        )
        super().__init__(cache_ttl=config.connection_cache_ttl)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    async def aclose(self) -> None:
        """Close both sync and async HTTP clients.

        Closes the synchronous httpx.Client and asynchronous httpx.AsyncClient
        instances to release resources.
        """
        if self._client is not None:
            self._client.close()
            self._client = None
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __del__(self) -> None:
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None

    def __enter__(self) -> "EmbeddingGenerator":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.close()

    async def __aenter__(self) -> "EmbeddingGenerator":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self.aclose()

    @property
    def client(self) -> httpx.Client:
        """Get or create the HTTPX client instance."""
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    @property
    def async_client(self) -> httpx.AsyncClient:
        """Get or create the HTTPX async client instance."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=60.0)
        return self._async_client

    def _check_rate_limit(self) -> None:
        self._rate_limiter.acquire()

    async def _check_rate_limit_async(self) -> None:
        await self._rate_limiter.acquire_async()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make a synchronous HTTP request."""
        return self.client.request(method, url, **kwargs)

    async def _request_async(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Make an asynchronous HTTP request."""
        return await self.async_client.request(method, url, **kwargs)

    def _do_validate(self) -> bool:
        """Validate Ollama connection by checking /api/tags endpoint."""
        try:
            response = self._request("GET", f"{self.ollama_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama connection validation failed: {e}")
            return False

    async def validate_connection_async(self, force: bool = False) -> bool:
        """Check if Ollama service is available asynchronously.

        Args:
            force: If True, bypass cache and check connection.

        Returns:
            True if connection is valid, False otherwise.
        """
        current_time = time.monotonic()

        if (
            not force
            and self._connection_valid is not None
            and current_time - self._connection_checked_at < self._connection_cache_ttl
        ):
            return self._connection_valid

        try:
            response = await self._request_async("GET", f"{self.ollama_url}/api/tags")
            self._connection_valid = response.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama async connection validation failed: {e}")
            self._connection_valid = False

        self._connection_checked_at = current_time
        return self._connection_valid

    def on_service_recovery(self) -> None:
        """Handle service recovery - clear cached connection state."""
        super().on_service_recovery()

    async def on_service_recovery_async(self) -> None:
        """Handle service recovery asynchronously."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        self.invalidate_connection_cache()

    def get_model_info(self) -> dict[str, Any] | None:
        """Get information about the embedding model from Ollama.

        Returns:
            Dictionary with model info including embedding dimensions, or None if unavailable.
        """
        try:
            response = self._request("GET", f"{self.ollama_url}/api/tags")
            if response.status_code != 200:
                return None

            data = response.json()
            config = get_config()
            for model in data.get("models", []):
                if model.get("name", "").startswith(self.model.split(":")[0]):
                    return {
                        "name": model.get("name"),
                        "size": model.get("size"),
                        "embedding_dimensions": config.embedding_dimensions,
                    }
            return None
        except Exception as e:
            logger.debug(f"Failed to get model info: {e}")
            return None

    async def get_model_info_async(self) -> dict[str, Any] | None:
        """Get information about the embedding model from Ollama asynchronously.

        Returns:
            Dictionary with model info including embedding dimensions, or None if unavailable.
        """
        try:
            response = await self._request_async("GET", f"{self.ollama_url}/api/tags")
            if response.status_code != 200:
                return None

            data = response.json()
            config = get_config()
            for model in data.get("models", []):
                if model.get("name", "").startswith(self.model.split(":")[0]):
                    return {
                        "name": model.get("name"),
                        "size": model.get("size"),
                        "embedding_dimensions": config.embedding_dimensions,
                    }
            return None
        except Exception as e:
            logger.debug(f"Failed to get model info async: {e}")
            return None

    def pull_model(self) -> None:
        """Pull the embedding model from Ollama if not already pulled."""
        if self._model_pulled:
            return

        try:
            response = self._request(
                "POST",
                f"{self.ollama_url}/api/pull",
                json={"name": self.model},
                timeout=300.0,
            )
            if response.status_code == 200:
                self._model_pulled = True
                logger.info(f"Pulled embedding model: {self.model}")
            else:
                logger.warning(f"Failed to pull model: {response.text}")
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
            raise OllamaUnavailableError(f"Failed to pull model: {e}") from e

    async def pull_model_async(self) -> None:
        """Pull the embedding model from Ollama asynchronously."""
        if self._model_pulled:
            return

        try:
            response = await self._request_async(
                "POST",
                f"{self.ollama_url}/api/pull",
                json={"name": self.model},
                timeout=300.0,
            )
            if response.status_code == 200:
                self._model_pulled = True
                logger.info(f"Pulled embedding model: {self.model}")
            else:
                logger.warning(f"Failed to pull model: {response.text}")
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
            raise OllamaUnavailableError(f"Failed to pull model: {e}") from e

    def generate(self, text: str) -> list[float]:
        """Generate an embedding for the given text.

        Args:
            text: Text to generate embedding for.

        Returns:
            List of float values representing the embedding.

        Raises:
            OllamaUnavailableError: If Ollama service is unavailable.
            EmbeddingGenerationError: If embedding generation fails.
        """
        self._check_rate_limit()

        if not self.validate_connection():
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama service at {self.ollama_url} "
                f"(model: {self.model}). Check that Ollama is running and accessible."
            )

        if not self._model_pulled:
            self.pull_model()

        try:
            response = self._request(
                "POST",
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise EmbeddingGenerationError(
                    f"Failed to generate embedding for model '{self.model}': "
                    f"HTTP {response.status_code} - {response.text} "
                    f"(text length: {len(text)} chars)"
                )

            data = response.json()
            embedding = list(data.get("embedding", []))
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise EmbeddingGenerationError(
                f"Timeout generating embedding: model={self.model}, "
                f"text_length={len(text)} chars, timeout=30s: {e}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(
                f"Failed to generate embedding: model={self.model}, "
                f"text_length={len(text)} chars, error={type(e).__name__}: {e}"
            ) from e

    async def generate_async(self, text: str) -> list[float]:
        await self._check_rate_limit_async()

        if not await self.validate_connection_async():
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            )

        if not self._model_pulled:
            await self.pull_model_async()

        try:
            response = await self._request_async(
                "POST",
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=30.0,
            )

            if response.status_code != 200:
                raise EmbeddingGenerationError(
                    f"Failed to generate embedding for model '{self.model}': "
                    f"HTTP {response.status_code} - {response.text} "
                    f"(text length: {len(text)} chars)"
                )

            data = response.json()
            embedding = list(data.get("embedding", []))
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise EmbeddingGenerationError(
                f"Timeout generating embedding: model={self.model}, "
                f"text_length={len(text)} chars, timeout=30s: {e}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(
                f"Failed to generate embedding: model={self.model}, "
                f"text_length={len(text)} chars, error={type(e).__name__}: {e}"
            ) from e

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to generate embeddings for.

        Returns:
            List of embedding vectors.
        """
        return [self.generate(text) for text in texts]

    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts asynchronously.

        Args:
            texts: List of texts to generate embeddings for.

        Returns:
            List of embedding vectors.
        """
        return [await self._generate_async_with_rate_limit(text) for text in texts]

    async def _generate_async_with_rate_limit(self, text: str) -> list[float]:
        await self._check_rate_limit_async()
        return await self.generate_async(text)
