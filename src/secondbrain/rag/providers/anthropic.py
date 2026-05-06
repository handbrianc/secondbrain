"""Anthropic LLM provider implementation for RAG pipeline.

Provides AnthropicLLMProvider class that implements the LocalLLMProvider protocol
for using Anthropic Claude as an LLM backend.
"""

import os

import httpx
from anthropic import Anthropic, APIError, AsyncAnthropic

from secondbrain.exceptions import ServiceUnavailableError

from ..interfaces import LocalLLMProvider


class AnthropicLLMProvider(LocalLLMProvider):
    """Anthropic implementation of LocalLLMProvider protocol.

    Uses the official Anthropic Python library for chat API interactions.
    Provides both sync and async generation methods with proper error handling.

    Attributes:
        model: Model name to use for generation.
        temperature: Default temperature for generation.
        max_tokens: Default max tokens for generation.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: int = 120,
        api_key: str | None = None,
    ) -> None:
        """Initialize Anthropic provider with configuration.

        Args:
            model: Model name to use (default: "claude-3-sonnet-20240229").
            temperature: Default temperature for generation (default: 0.1).
            max_tokens: Default max tokens for generation (default: 2048).
            timeout: Request timeout in seconds (default: 120).
            api_key: Anthropic API key (defaults to SECONDBRAIN_ANTHROPIC_API_KEY env var).

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

        # Get API key from parameter or environment
        self._api_key = api_key or os.getenv("SECONDBRAIN_ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Anthropic API key required. Set SECONDBRAIN_ANTHROPIC_API_KEY "
                "environment variable or provide api_key parameter"
            )

        # Initialize clients
        self._client = Anthropic(
            api_key=self._api_key,
            timeout=httpx.Timeout(timeout),
        )
        self._async_client = AsyncAnthropic(
            api_key=self._api_key,
            timeout=httpx.Timeout(timeout),
        )

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response using Anthropic Claude API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If Anthropic API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            # Convert prompt to messages format
            messages = [{"role": "user", "content": prompt}]

            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call Anthropic API
            response = self._client.messages.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )

            return response.content[0].text if response.content else ""

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"Anthropic API unreachable: {e}") from e
        except APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Generation failed: {e}") from e

    async def agenerate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response asynchronously using Anthropic Claude API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If Anthropic API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            # Convert prompt to messages format
            messages = [{"role": "user", "content": prompt}]

            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call Anthropic API asynchronously
            response = await self._async_client.messages.create(
                model=self._model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
            )

            return response.content[0].text if response.content else ""

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"Anthropic API unreachable: {e}") from e
        except APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async generation failed: {e}") from e

    def health_check(self) -> bool:
        """Check if Anthropic API is accessible.

        Returns:
            True if API is accessible, False otherwise.
        """
        try:
            # Make a minimal request to check connectivity
            self._client.models.list()
            return True
        except Exception:
            return False

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
