"""Local LLM provider interface for RAG pipeline.

Defines the protocol that all local LLM providers must implement.
"""

from typing import Callable, Protocol

# Type alias for streaming callbacks
# Callback receives (content_chunk, reasoning_chunk) where reasoning_chunk can be None
StreamingCallback = Callable[[str, str | None], None]
"""Callback type for streaming responses.

Args:
    content: Regular response content (can be empty if only reasoning)
    reasoning: Thinking/reasoning content (None if not available)

Example:
    >>> def my_callback(content: str, reasoning: str | None) -> None:
    ...     if reasoning:
    ...         print(f"[Thinking] {reasoning}", end="")
    ...     if content:
    ...         print(f"{content}", end="")
"""


class LocalLLMProvider(Protocol):
    """Protocol for local LLM providers.

    All local LLM backends (OpenAI, Anthropic, vLLM, llama.cpp, etc.) must implement
    this interface to be used with the RAG pipeline.
    """

    @property
    def model(self) -> str:
        """Get the model name."""
        ...  # pragma: no cover

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The prompt to send to the LLM.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Generated response text.

        Raises:
            ConnectionError: If the LLM server is unreachable.
            TimeoutError: If the request times out.
            RuntimeError: If the LLM returns an error.
        """
        ...  # pragma: no cover

    async def agenerate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async version of generate.

        Args:
            prompt: The prompt to send to the LLM.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Generated response text.
        """
        ...  # pragma: no cover

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
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

        Example:
            >>> def handler(content: str, reasoning: str | None) -> None:
            ...     if reasoning:
            ...         print(f"[Thinking] {reasoning}", end="")
            ...     elif content:
            ...         print(f"{content}", end="")
            >>> result = provider.stream_chat(messages, handler)

        Note:
            - Not all models/providers support reasoning content
            - Use hasattr() checks in implementations for compatibility
            - Callback may be invoked with empty content if only reasoning present
        """
        ...  # pragma: no cover

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async version of stream_chat.

        Args:
            messages: Chat messages in format
                [{"role": "user", "content": "..."}]
            on_chunk: Callback invoked for each streaming chunk.
            temperature: Controls randomness (0.0 = deterministic, 2.0 = creative).
            max_tokens: Maximum number of tokens to generate.

        Returns:
            Complete response text after streaming finishes.
        """
        ...  # pragma: no cover

    def health_check(self) -> bool:
        """Check if the LLM server is available.

        Returns:
            True if the server is responsive, False otherwise.
        """
        ...  # pragma: no cover
