"""Embedding generator using Ollama API."""

import asyncio
import contextlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from secondbrain.config import get_config
from secondbrain.exceptions import (
    EmbeddingGenerationError,
    OllamaUnavailableError,
)
from secondbrain.utils.circuit_breaker import CircuitBreaker, CircuitBreakerError
from secondbrain.utils.connections import (
    ValidatableService,
)
from secondbrain.utils.embedding_cache import EmbeddingCache
from secondbrain.utils.perf_monitor import async_timing, timing

from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


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
        cache_size: int | None = None,
    ) -> None:
        """Initialize the embedding generator.

        Args:
            model: Model name to use. If None, uses config default.
            ollama_url: Ollama API URL. If None, uses config default.
            rate_limiter: Optional RateLimiter instance. If None, creates new one.
            cache_size: Optional cache size. If None, uses unlimited cache.
        """
        config = get_config()
        self.model = model or config.model
        self.ollama_url = ollama_url or config.ollama_url
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._model_pulled = False
        self._rate_limiter = rate_limiter or RateLimiter(
            max_requests=config.rate_limit_max_requests,
            window_seconds=config.rate_limit_window_seconds,
        )
        self._cache = EmbeddingCache(max_size=cache_size or 10000)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout,
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

        Returns
        -------
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

        Returns
        -------
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

        Returns
        -------
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

    @timing("embedding_generate")
    def generate(self, text: str) -> list[float]:
        """Generate an embedding for the given text.

        Uses cache to avoid redundant API calls for duplicate texts.

        Args:
            text: Text to generate embedding for.

        Returns
        -------
            List of float values representing the embedding.

        Raises
        ------
            OllamaUnavailableError: If Ollama service is unavailable.
            EmbeddingGenerationError: If embedding generation fails.
        """

        def _generate(text: str) -> list[float]:
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

        try:
            return self._circuit_breaker.call(
                self._cache.get_or_create, text, _generate
            )
        except CircuitBreakerError as e:
            raise OllamaUnavailableError(
                f"Circuit breaker open: {e}. Service may be unavailable."
            ) from e

    @async_timing("embedding_generate_async")
    async def generate_async(self, text: str) -> list[float]:
        """Generate an embedding for the given text asynchronously.

        Uses cache to avoid redundant API calls for duplicate texts.

        Args:
            text: Text to generate embedding for.

        Returns
        -------
            List of float values representing the embedding.

        Raises
        ------
            OllamaUnavailableError: If Ollama service is unavailable.
            EmbeddingGenerationError: If embedding generation fails.
        """

        async def _generate_async(text: str) -> list[float]:
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

        return await self._cache.get_or_create_async(text, _generate_async)

    @timing("embedding_generate_batch")
    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts in parallel.

        Uses thread pool for concurrent embedding generation while
        respecting rate limits and leveraging cache.

        Args:
            texts: List of texts to generate embeddings for.

        Returns
        -------
            List of embedding vectors in original order.
        """
        with ThreadPoolExecutor(max_workers=min(len(texts), 10)) as executor:
            future_to_idx = {
                executor.submit(self.generate, text): i for i, text in enumerate(texts)
            }

            results: dict[int, list[float]] = {}

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()

            return [results[i] for i in range(len(texts))]

    @async_timing("embedding_generate_batch_async")
    async def generate_batch_async(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts concurrently.

        Uses asyncio.gather for concurrent embedding generation while
        respecting rate limits and leveraging cache.

        Args:
            texts: List of texts to generate embeddings for.

        Returns
        -------
            List of embedding vectors.
        """
        results = await asyncio.gather(*[self.generate_async(text) for text in texts])
        return list(results)
