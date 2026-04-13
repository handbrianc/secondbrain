"""OpenAI LLM provider implementation for RAG pipeline.

Provides OpenAILLMProvider class that implements the LocalLLMProvider protocol
for using OpenAI API as an LLM backend.
"""

import os

import httpx
from openai import APIError, AsyncOpenAI, OpenAI

from secondbrain.exceptions import ServiceUnavailableError

from ..interfaces import LocalLLMProvider


class OpenAILLMProvider(LocalLLMProvider):
    """OpenAI implementation of LocalLLMProvider protocol.

    Uses the official OpenAI Python library for chat API interactions.
    Provides both sync and async generation methods with proper error handling.

    Attributes:
        model: Model name to use for generation.
        temperature: Default temperature for generation.
        max_tokens: Default max tokens for generation.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        timeout: int = 120,
        api_key: str | None = None,
    ) -> None:
        """Initialize OpenAI provider with configuration.

        Args:
            model: Model name to use (default: "gpt-4o-mini").
            temperature: Default temperature for generation (default: 0.1).
            max_tokens: Default max tokens for generation (default: 2048).
            timeout: Request timeout in seconds (default: 120).
            api_key: OpenAI API key (defaults to SECONDBRAIN_OPENAI_API_KEY env var).

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

        # Get API key from parameter or environment
        self._api_key = api_key or os.getenv("SECONDBRAIN_OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set SECONDBRAIN_OPENAI_API_KEY "
                "environment variable or provide api_key parameter"
            )

        # Initialize clients
        self._client = OpenAI(
            api_key=self._api_key,
            timeout=httpx.Timeout(timeout),
        )
        self._async_client = AsyncOpenAI(
            api_key=self._api_key,
            timeout=httpx.Timeout(timeout),
        )

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response using OpenAI chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If OpenAI API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            # Convert prompt to chat format
            messages = [{"role": "user", "content": prompt}]

            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call OpenAI chat API
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                max_tokens=tokens,
            )

            return response.choices[0].message.content or ""

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Generation failed: {e}") from e

    async def generate_async(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response asynchronously using OpenAI chat API.

        Args:
            prompt: User prompt text.
            temperature: Override default temperature (0.0-2.0).
            max_tokens: Override default max tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ServiceUnavailableError: If OpenAI API is unreachable.
            RuntimeError: If generation fails.
        """
        try:
            # Convert prompt to chat format
            messages = [{"role": "user", "content": prompt}]

            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call OpenAI chat API asynchronously
            response = await self._async_client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                max_tokens=tokens,
            )

            return response.choices[0].message.content or ""

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise RuntimeError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async generation failed: {e}") from e

    def health_check(self) -> bool:
        """Check if OpenAI API is accessible.

        Returns:
            True if API is accessible, False otherwise.
        """
        try:
            # Make a minimal request to check connectivity
            self._client.models.list()
            return True
        except Exception:
            return False
