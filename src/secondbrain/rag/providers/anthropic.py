"""Anthropic LLM provider implementation for RAG pipeline.

Provides AnthropicLLMProvider class that implements the LocalLLMProvider protocol
for using Anthropic Claude as an LLM backend.
"""

# mypy: disable-error-code=union-attr
# mypy: disable-error-code=attr-defined

import contextlib
import os

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    AsyncAnthropic,
    Timeout,
)

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.logging import get_logger

from ..interfaces import LocalLLMProvider, StreamingCallback

logger = get_logger(__name__)


def _log_token_usage(
    operation: str,
    usage: object,
    model: str,
    *,
    extra_output: int | None = None,
) -> None:
    """Emit one structured token-usage log line when usage data is available.

    Anthropic reports ``usage.input_tokens`` / ``usage.output_tokens`` (no
    total); ``total_tokens`` is derived as their sum. Streaming responses
    report output tokens incrementally via ``message_delta`` events, so the
    accumulated output can be supplied through *extra_output* instead of
    reading ``usage.output_tokens`` directly.
    """
    if usage is None and extra_output is None:
        return
    prompt = getattr(usage, "input_tokens", None) if usage is not None else None
    # Streaming: the message_start usage reports output_tokens=0 and the real
    # count arrives via message_delta events — prefer the accumulated value.
    completion = (
        extra_output
        if extra_output is not None
        else getattr(usage, "output_tokens", None)
        if usage is not None
        else None
    )
    total = (
        prompt + completion
        if isinstance(prompt, int) and isinstance(completion, int)
        else None
    )
    logger.info(
        "%s token usage: model=%s prompt_tokens=%s completion_tokens=%s "
        "total_tokens=%s",
        operation,
        model,
        prompt,
        completion,
        total,
    )


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
        temperature: float = 1.0,
        max_tokens: int = 384000,
        timeout: int = 120,
        api_key: str | None = None,
        top_p: float = 0.95,
    ) -> None:
        """Initialize Anthropic provider with configuration.

        Args:
            model: Model name to use (default: "claude-3-sonnet-20240229").
            temperature: Default temperature for generation (default: 1.0).
            max_tokens: Default max tokens for generation (default: 384000).
            timeout: Request timeout in seconds (default: 120).
            api_key: Anthropic API key (defaults to SECONDBRAIN_ANTHROPIC_API_KEY env var).
            top_p: Nucleus-sampling top_p (0.0-1.0, default: 0.95).

        Raises:
            ValueError: If API key is not provided.
        """
        self._model = model
        self._temperature = temperature
        self._top_p = top_p
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
        self._client: Anthropic | None = Anthropic(
            api_key=self._api_key,
            timeout=Timeout(timeout),
        )
        self._async_client: AsyncAnthropic | None = AsyncAnthropic(
            api_key=self._api_key,
            timeout=Timeout(timeout),
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
        if self._client is None:
            raise RuntimeError("Anthropic provider has been closed")
        try:
            messages = [{"role": "user", "content": prompt}]

            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = self._client.messages.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
            )

            _log_token_usage(
                "completion", getattr(response, "usage", None), self._model
            )
            return response.content[0].text if response.content else ""

        except APIConnectionError as e:
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
        if self._async_client is None:
            raise RuntimeError("Anthropic provider has been closed")
        try:
            messages = [{"role": "user", "content": prompt}]

            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = await self._async_client.messages.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
            )

            _log_token_usage(
                "completion", getattr(response, "usage", None), self._model
            )
            return response.content[0].text if response.content else ""

        except APIConnectionError as e:
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
        if self._client is None:
            return False
        try:
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

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Stream chat response with thinking content support."""
        if self._client is None:
            raise RuntimeError("Anthropic provider has been closed")
        try:
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = self._client.messages.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
                stream=True,
            )

            full_content = ""
            full_reasoning = ""
            start_usage: object = None
            output_tokens: int | None = None

            for event in response:
                if event.type == "message_start":
                    start_usage = getattr(
                        getattr(event, "message", None), "usage", None
                    )
                elif event.type == "message_delta":
                    delta_usage = getattr(event, "usage", None)
                    delta_out = getattr(delta_usage, "output_tokens", None)
                    if isinstance(delta_out, int):
                        output_tokens = delta_out
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text") and event.delta.text:
                        full_content += event.delta.text
                        on_chunk(event.delta.text, None)

                    if hasattr(event.delta, "thinking") and event.delta.thinking:
                        full_reasoning += event.delta.thinking
                        on_chunk("", event.delta.thinking)

            _log_token_usage(
                "streaming completion",
                start_usage,
                self._model,
                extra_output=output_tokens,
            )
            return full_content

        except APIConnectionError as e:
            raise ServiceUnavailableError(f"Anthropic API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"Anthropic API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Streaming failed: {e}") from e

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async streaming chat response with thinking content support."""
        if self._async_client is None:
            raise RuntimeError("Anthropic provider has been closed")
        try:
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            response = await self._async_client.messages.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                top_p=self._top_p,
                max_tokens=tokens,
                stream=True,
            )

            full_content = ""
            start_usage: object = None
            output_tokens: int | None = None

            async for event in response:
                if event.type == "message_start":
                    start_usage = getattr(
                        getattr(event, "message", None), "usage", None
                    )
                elif event.type == "message_delta":
                    delta_usage = getattr(event, "usage", None)
                    delta_out = getattr(delta_usage, "output_tokens", None)
                    if isinstance(delta_out, int):
                        output_tokens = delta_out
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text") and event.delta.text:
                        full_content += event.delta.text
                        on_chunk(event.delta.text, None)

                    if hasattr(event.delta, "thinking") and event.delta.thinking:
                        on_chunk("", event.delta.thinking)

            _log_token_usage(
                "streaming completion",
                start_usage,
                self._model,
                extra_output=output_tokens,
            )
            return full_content

        except APIConnectionError as e:
            raise ServiceUnavailableError(f"Async streaming failed: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"Async streaming error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async streaming failed: {e}") from e

    def close(self) -> None:
        """Close clients and release resources.

        Note: For proper async cleanup in async context, use aclose() instead.
        This method closes the sync HTTP client but does not close the async
        client — the async client must be closed with aclose() to avoid
        RuntimeWarnings from unawaited coroutines.
        """
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None

    async def aclose(self) -> None:
        """Asynchronously close both sync and async HTTP clients.

        Releases all held resources including async connection pools to prevent
        resource leaks and RuntimeWarnings from unawaited coroutines.
        """
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()
            self._client = None
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
        self._api_key = None
