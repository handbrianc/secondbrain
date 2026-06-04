"""OpenAI LLM provider implementation for RAG pipeline.

Provides OpenAILLMProvider class that implements the LocalLLMProvider protocol
for using OpenAI API as an LLM backend.
"""

import logging
import os

import httpx
from openai import APIError, AsyncOpenAI, OpenAI

from secondbrain.exceptions import ServiceUnavailableError

from ..interfaces import LocalLLMProvider, StreamingCallback

logger = logging.getLogger(__name__)


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
        base_url: str | None = None,
    ) -> None:
        """Initialize OpenAI provider with configuration.

        Args:
            model: Model name to use (default: "gpt-4o-mini").
            temperature: Default temperature for generation (default: 0.1).
            max_tokens: Default max tokens for generation (default: 2048).
            timeout: Request timeout in seconds (default: 120).
            api_key: OpenAI API key (defaults to SECONDBRAIN_OPENAI_API_KEY env var).
            base_url: OpenAI API base URL (defaults to SECONDBRAIN_OPENAI_BASE_URL env var).

        Raises:
            ValueError: If API key is not provided or model format is invalid.
        """
        # Validate model name format for litellm compatibility
        if base_url and "/" not in model.split("/")[-1]:
            # Using proxy (litellm) - ensure model has provider prefix
            provider_prefixes = ("dashscope/", "ollama", "ollama_chat/", "openai/", "bedrock/", "together_ai/", "groq/")
            if not model.lower().startswith(provider_prefixes) and "/" in model:
                # Model contains "/" but no recognized prefix - likely Qwen model
                # This is common for litellm proxy setups
                logger.warning(
                    "Model '%s' may need provider prefix for litellm proxy. "
                    "Common prefixes: dashscope/, ollama/, openai/. "
                    "If using litellm proxy, ensure the model is configured on the server.",
                    model
                )

        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout

        # Get API key from parameter or environment (with backward compatibility)
        self._api_key = api_key or os.getenv("SECONDBRAIN_LLM_API_KEY") or os.getenv("SECONDBRAIN_OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set SECONDBRAIN_LLM_API_KEY (or SECONDBRAIN_OPENAI_API_KEY for backward compatibility) "
                "environment variable or provide api_key parameter"
            )

        # Get base URL from parameter or environment (for LiteLLM or other proxies)
        self._base_url = base_url or os.getenv("SECONDBRAIN_OPENAI_BASE_URL")

        # Initialize clients
        client_kwargs = {
            "api_key": self._api_key,
            "timeout": httpx.Timeout(timeout),
        }
        if self._base_url:
            client_kwargs["base_url"] = self._base_url

        self._client = OpenAI(**client_kwargs)  # type: ignore
        self._async_client = AsyncOpenAI(**client_kwargs)  # type: ignore

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

            response_content = response.choices[0].message.content or ""

            # Empty response triggers retry in pipeline.py chat() method
            if not response_content or not response_content.strip():
                finish_reason = response.choices[0].finish_reason if response.choices else "N/A"
                usage_info = response.usage.model_dump() if hasattr(response, 'usage') and response.usage else "N/A"
                model_configured = hasattr(response, 'model') and response.model

                logger.error(
                    "CRITICAL: Empty response from LLM endpoint. "
                    "Model: %s, Finish reason: %s, Usage: %s, Model returned: %s. "
                    "Common causes: (1) Model not configured in litellm proxy, "
                    "(2) Streaming-only model called without stream=True, "
                    "(3) Timeout exceeded, (4) Content filtering blocked response.",
                    self._model, finish_reason, usage_info, model_configured
                )

                # Raise explicit error for empty responses to trigger retry logic
                raise RuntimeError(
                    f"LLM endpoint returned empty response for model '{self._model}'. "
                    f"Check: (1) Model is configured in litellm proxy, "
                    f"(2) Model name format is correct (e.g., 'dashscope/qwen-...'), "
                    f"(3) Streaming requirements met for QwQ/QVQ models, "
                    f"(4) Timeout is sufficient for large models."
                )

            return response_content

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
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

            response_content = response.choices[0].message.content or ""

            if not response_content or not response_content.strip():
                finish_reason = response.choices[0].finish_reason if response.choices else "N/A"
                usage_info = response.usage.model_dump() if hasattr(response, 'usage') and response.usage else "N/A"

                logger.error(
                    "CRITICAL: Empty async response from LLM endpoint. "
                    "Model: %s, Finish reason: %s, Usage: %s. "
                    "Common causes: (1) Model not configured in litellm proxy, "
                    "(2) Streaming-only model called without stream=True, "
                    "(3) Timeout exceeded, (4) Content filtering blocked response.",
                    self._model, finish_reason, usage_info
                )

                raise RuntimeError(
                    f"LLM endpoint returned empty async response for model '{self._model}'. "
                    f"Check: (1) Model is configured in litellm proxy, "
                    f"(2) Model name format is correct (e.g., 'dashscope/qwen-...'), "
                    f"(3) Streaming requirements met for QwQ/QVQ models, "
                    f"(4) Timeout is sufficient for large models."
                )

            return response_content

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async generation failed: {e}") from e

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Stream chat response with thinking support.

        Streams response chunks incrementally, separating thinking/reasoning
        content from final answer content.

        Args:
            messages: Chat messages in format
                [{"role": "user", "content": "..."}]
            on_chunk: Callback invoked for each streaming chunk.
                Receives (content, reasoning) where:
                - content: Regular response text (empty if only reasoning)
                - reasoning: Thinking content (None if not available)
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Complete response text after streaming finishes.
        """
        try:
            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call OpenAI chat API with streaming
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                max_tokens=tokens,
                stream=True,
            )

            full_content = ""
            full_reasoning = ""
            last_content = ""

            for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # Check for reasoning content (standardized by LiteLLM)
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        full_reasoning += delta.reasoning_content
                        on_chunk("", delta.reasoning_content)

                    # Check for regular content
                    if hasattr(delta, 'content') and delta.content:
                        full_content += delta.content
                        on_chunk(delta.content, None)
                        last_content = delta.content
                    
                    # Store last message content as fallback
                    if hasattr(delta, 'message') and delta.message:
                        if hasattr(delta.message, 'content') and delta.message.content:
                            last_content = delta.message.content

            # Fallback: if no content was collected, try to get it from response
            if not full_content and last_content:
                full_content = last_content
                on_chunk(full_content, None)
            
            # Final fallback: check if response object has content
            if not full_content:
                try:
                    if hasattr(response, 'choices') and response.choices:
                        for choice in reversed(response.choices):
                            if hasattr(choice, 'message') and choice.message:
                                if hasattr(choice.message, 'content') and choice.message.content:
                                    full_content = choice.message.content
                                    on_chunk(full_content, None)
                                    break
                except (AttributeError, IndexError):
                    pass

            return full_content

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Streaming failed: {e}") from e

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async streaming chat response with thinking support.

        Args:
            messages: Chat messages in format
                [{"role": "user", "content": "..."}]
            on_chunk: Callback invoked for each streaming chunk.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Complete response text after streaming finishes.
        """
        try:
            # Use provided overrides or defaults
            temp = temperature if temperature is not None else self._temperature
            tokens = max_tokens if max_tokens is not None else self._max_tokens

            # Call OpenAI chat API asynchronously with streaming
            response = await self._async_client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore
                temperature=temp,
                max_tokens=tokens,
                stream=True,
            )

            full_content = ""
            full_reasoning = ""

            async for chunk in response:
                if chunk.choices:
                    delta = chunk.choices[0].delta

                    # Check for reasoning content
                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        full_reasoning += delta.reasoning_content
                        on_chunk("", delta.reasoning_content)

                    # Check for regular content
                    if hasattr(delta, 'content') and delta.content:
                        full_content += delta.content
                        on_chunk(delta.content, None)

            return full_content

        except httpx.ConnectError as e:
            raise ServiceUnavailableError(f"OpenAI API unreachable: {e}") from e
        except APIError as e:
            raise ServiceUnavailableError(f"OpenAI API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Async streaming failed: {e}") from e

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

    async def agenerate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate response asynchronously using OpenAI chat API."""
        return await self.generate_async(prompt, temperature, max_tokens)
