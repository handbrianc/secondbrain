import logging
from collections.abc import Callable

import httpx

from secondbrain.config import get_config

logger = logging.getLogger(__name__)


class EmbeddingGenerationError(Exception):
    pass


class OllamaUnavailableError(Exception):
    pass


class EmbeddingGenerator:
    def __init__(self, model=None, ollama_url=None):
        config = get_config()
        self.model = model or config.model
        self.ollama_url = ollama_url or config.ollama_url
        self._client = None
        self._async_client = None
        self._model_pulled = False
        self._connection_valid = None
        self._connection_checked_at = 0.0
        self._connection_cache_ttl = 60.0

    @property
    def client(self):
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    @property
    def async_client(self):
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=60.0)
        return self._async_client

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        return self.client.request(method, url, **kwargs)

    async def _request_async(self, method: str, url: str, **kwargs) -> httpx.Response:
        return await self.async_client.request(method, url, **kwargs)

    def validate_connection(self, force=False):
        import time

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

    async def validate_connection_async(self, force=False):
        import time

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

    def invalidate_connection_cache(self):
        self._connection_valid = None
        self._connection_checked_at = 0.0

    def on_service_recovery(self):
        self.invalidate_connection_cache()

    async def on_service_recovery_async(self):
        await self.async_client.aclose()
        self._async_client = None
        self.invalidate_connection_cache()

    def pull_model(self):
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

    async def pull_model_async(self):
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

    def generate(self, text):
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
            embedding = data.get("embedding", [])
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(f"Error generating embedding: {e}") from e

    async def generate_async(self, text):
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
            embedding = data.get("embedding", [])
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(f"Error generating embedding: {e}") from e

    def generate_batch(self, texts):
        return [self.generate(text) for text in texts]

    async def generate_batch_async(self, texts):
        return [await self.generate_async(text) for text in texts]
