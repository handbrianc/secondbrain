import logging
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

import httpx
from typing_extensions import TypedDict

from secondbrain.config import get_config
from secondbrain.utils.connections import ServiceUnavailableError, ServiceValidator

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 1.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = Lock()
        self._requests: list[float] = []

    def acquire(self) -> None:
        """Acquire rate limit token, blocking if necessary."""
        current_time = time.time()

        with self._lock:
            self._requests[:] = [
                t for t in self._requests if current_time - t < self.window_seconds
            ]

            if len(self._requests) >= self.max_requests:
                oldest = min(self._requests)
                sleep_time = self.window_seconds - (current_time - oldest)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    self.acquire()
                    return

            self._requests.append(current_time)


_RATE_LIMITER = RateLimiter(max_requests=10, window_seconds=1.0)


def _check_rate_limit() -> None:
    _RATE_LIMITER.acquire()


class EmbeddingGenerationError(Exception):
    pass


class OllamaUnavailableError(Exception):
    pass


class EmbeddingResult(TypedDict):
    embedding: list[float]


class EmbeddingGenerator:
    """Generates embeddings using Ollama API."""

    def __init__(self, model: str | None = None, ollama_url: str | None = None) -> None:
        """Initialize the embedding generator.

        Args:
            model: Model name to use. If None, uses config default.
            ollama_url: Ollama API URL. If None, uses config default.
        """
        config = get_config()
        self.model = model or config.model
        self.ollama_url = ollama_url or config.ollama_url
        self._client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None
        self._model_pulled = False
        self._connection_valid: bool | None = None
        self._connection_checked_at = 0.0
        self._connection_cache_ttl = 60.0

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

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Make a synchronous HTTP request."""
        return self.client.request(method, url, **kwargs)

    async def _request_async(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Make an asynchronous HTTP request."""
        return await self.async_client.request(method, url, **kwargs)

    def validate_connection(self, force: bool = False) -> bool:
        """Check if Ollama service is available.

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
            response = self._request("GET", f"{self.ollama_url}/api/tags")
            self._connection_valid = response.status_code == 200
        except Exception:
            self._connection_valid = False

        self._connection_checked_at = current_time
        return self._connection_valid

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
        except Exception:
            self._connection_valid = False

        self._connection_checked_at = current_time
        return self._connection_valid

    def invalidate_connection_cache(self) -> None:
        """Clear cached connection state."""
        self._connection_valid = None
        self._connection_checked_at = 0.0

    def on_service_recovery(self) -> None:
        """Handle service recovery - clear cached connection state."""
        self.invalidate_connection_cache()

    async def on_service_recovery_async(self) -> None:
        """Handle service recovery asynchronously."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        self.invalidate_connection_cache()

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
        _check_rate_limit()

        if not self.validate_connection():
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            )

        if not self._model_pulled:
            self.pull_model()

        try:
            response = self._request(
                "POST",
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )

            if response.status_code != 200:
                raise EmbeddingGenerationError(
                    f"Failed to generate embedding: {response.text}"
                )

            data = response.json()
            embedding = list(data.get("embedding", []))
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(f"Error generating embedding: {e}") from e

    async def generate_async(self, text: str) -> list[float]:
        """Generate an embedding for the given text asynchronously.

        Args:
            text: Text to generate embedding for.

        Returns:
            List of float values representing the embedding.

        Raises:
            OllamaUnavailableError: If Ollama service is unavailable.
            EmbeddingGenerationError: If embedding generation fails.
        """
        _check_rate_limit()

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
            )

            if response.status_code != 200:
                raise EmbeddingGenerationError(
                    f"Failed to generate embedding: {response.text}"
                )

            data = response.json()
            embedding = list(data.get("embedding", []))
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(f"Error generating embedding: {e}") from e

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
        return [await self.generate_async(text) for text in texts]
