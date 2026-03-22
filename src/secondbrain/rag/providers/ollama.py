"""Ollama LLM provider implementation for RAG pipeline.

Provides OllamaLLMProvider class that implements the LocalLLMProvider protocol
for using Ollama as a local LLM backend.
"""

import asyncio

import httpx
from ollama import Client, ResponseError

from secondbrain.exceptions import ServiceUnavailableError

# Use relative import to avoid triggering rag/__init__.py
from ..interfaces import LocalLLMProvider


class OllamaLLMProvider(LocalLLMProvider):
    """Ollama implementation of LocalLLMProvider protocol.

    Uses the official ollama Python library for chat API interactions.
    Provides both sync and async generation methods with proper error handling.

    Attributes:
        host: Ollama server host URL.
        model: Model name to use for generation.
        temperature: Default temperature for generation.
        max_tokens: Default max tokens for generation.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.2",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: int = 120,
    ) -> None:
        """Initialize Ollama provider with configuration.

        Args:
            host: Ollama server URL (default: "http://localhost:11434").
            model: Model name to use (default: "llama3.2").
            temperature: Default temperature for generation (default: 0.1).
            max_tokens: Default max tokens for generation (default: 2048).
            timeout: Request timeout in seconds (default: 120).
        """
        self._host = host
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

        # Initialize sync client
        self._client = Client(host=host, timeout=timeout)

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response using Ollama chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If Ollama server is unreachable.
            RuntimeError: If model not found or generation fails.
        """
        try:
            # Convert prompt to chat format
            messages = [{"role": "user", "content": prompt}]

            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call Ollama chat API
            response = self._client.chat(
                model=self._model,
                messages=messages,
                options={
                    "temperature": temp,
                    "num_predict": tokens,
                },
                stream=False,
            )

            return response["message"]["content"]  # type: ignore[no-any-return]

        except httpx.ConnectError as e:
            # Server unreachable
            raise ServiceUnavailableError("Ollama server unavailable") from e
        except httpx.TimeoutException as e:
            # Timeout
            raise ServiceUnavailableError("Ollama request timed out") from e
        except ResponseError as e:
            # Handle response errors
            if e.status_code == 404:
                raise RuntimeError(f"Model '{self._model}' not found") from e
            raise RuntimeError(f"Generation failed: {e.error}") from e

    async def agenerate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async version of generate.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If Ollama server is unreachable.
            RuntimeError: If model not found or generation fails.
        """
        # Run sync generate in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, temperature, max_tokens),
        )

    def health_check(self) -> bool:
        """Check if Ollama server is available.

        Calls the list() method to verify server responsiveness.

        Returns:
            True if the server is responsive, False otherwise.
        """
        try:
            # Try calling client.list() to list available models
            self._client.list()
            return True
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send chat messages and get response.

        Args:
            messages: List of {role, content} dicts for conversation history.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Assistant response text.

        Raises:
            ServiceUnavailableError: If Ollama server is unreachable.
            RuntimeError: If model not found or generation fails.
        """
        try:
            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call Ollama chat API with provided messages
            response = self._client.chat(
                model=self._model,
                messages=messages,
                options={
                    "temperature": temp,
                    "num_predict": tokens,
                },
                stream=False,
            )

            return response["message"]["content"]  # type: ignore[no-any-return]

        except httpx.ConnectError as e:
            # Server unreachable
            raise ServiceUnavailableError("Ollama server unavailable") from e
        except httpx.TimeoutException as e:
            # Timeout
            raise ServiceUnavailableError("Ollama request timed out") from e
        except ResponseError as e:
            # Handle response errors
            if e.status_code == 404:
                raise RuntimeError(f"Model '{self._model}' not found") from e
            raise RuntimeError(f"Generation failed: {e.error}") from e

    @property
    def host(self) -> str:
        """Get the Ollama server host URL."""
        return self._host

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._model

    @property
    def temperature(self) -> float:
        """Get the default temperature."""
        return self._temperature

    @property
    def max_tokens(self) -> int:
        """Get the default max tokens."""
        return self._max_tokens

    @property
    def timeout(self) -> int:
        """Get the request timeout."""
        return self._timeout
