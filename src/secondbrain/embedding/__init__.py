"""Embedding module for Ollama integration."""

import logging

import httpx

from secondbrain.config import get_config

logger = logging.getLogger(__name__)


class EmbeddingGenerationError(Exception):
    """Error during embedding generation."""


class OllamaUnavailableError(Exception):
    """Ollama service is not available."""


class EmbeddingGenerator:
    """Handles embedding generation via Ollama."""

    def __init__(self, model: str | None = None, ollama_url: str | None = None) -> None:
        config = get_config()
        self.model = model or config.model
        self.ollama_url = ollama_url or config.ollama_url
        self._client: httpx.Client | None = None
        self._model_pulled = False

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def validate_connection(self) -> bool:
        try:
            response = self.client.get(f"{self.ollama_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def pull_model(self) -> None:
        if self._model_pulled:
            return

        try:
            response = self.client.post(
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
        if not self.validate_connection():
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            )

        if not self._model_pulled:
            self.pull_model()

        try:
            response = self.client.post(
                f"{self.ollama_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )

            if response.status_code != 200:
                raise EmbeddingGenerationError(
                    f"Failed to generate embedding: {response.text}"
                )

            data = response.json()
            embedding: list[float] = data.get("embedding", [])
            return embedding

        except httpx.ConnectError as e:
            raise OllamaUnavailableError(
                f"Cannot connect to Ollama at {self.ollama_url}"
            ) from e
        except Exception as e:
            raise EmbeddingGenerationError(f"Error generating embedding: {e}") from e

    def generate_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.generate(text) for text in texts]
