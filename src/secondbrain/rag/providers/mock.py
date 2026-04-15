"""Mock LLM provider for testing when Ollama is unavailable.

Provides MockLLMProvider class that implements the LocalLLMProvider protocol
with deterministic, predictable responses for testing.
"""

import asyncio
import hashlib

from secondbrain.rag.interfaces import LocalLLMProvider


class MockLLMProvider(LocalLLMProvider):
    """Mock LLM provider for testing without Ollama.

    Provides deterministic, predictable responses based on input prompts.
    Useful for testing when Ollama server is unavailable.

    Attributes:
        default_response: Default response text for any prompt.
        response_map: Optional mapping of prompt patterns to responses.
    """

    def __init__(
        self,
        default_response: str | None = None,
        response_map: dict[str, str] | None = None,
    ) -> None:
        """Initialize mock provider with configuration.

        Args:
            default_response: Default response for any prompt. If None, uses
                a generic deterministic response based on prompt hash.
            response_map: Optional dict mapping prompt substrings to responses.
                First matching key wins.
        """
        self._default_response = (
            default_response
            if default_response is not None
            else "This is a mock response generated for testing purposes."
        )
        self._response_map = response_map or {}

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a deterministic mock response.

        Args:
            prompt: User prompt text (ignored, returns deterministic response).
            temperature: Ignored in mock mode.
            max_tokens: Ignored in mock mode.

        Returns:
            Deterministic mock response text.
        """
        # Check response map first
        for pattern, response in self._response_map.items():
            if pattern in prompt:
                return response

        # Generate deterministic response based on prompt hash
        # This ensures same prompt always gets same response
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        return (
            f"[MOCK] {self._default_response} "
            f"(prompt_hash: {prompt_hash}, temperature: {temperature}, max_tokens: {max_tokens})"
        )

    async def agenerate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async version of generate.

        Args:
            prompt: User prompt text.
            temperature: Ignored in mock mode.
            max_tokens: Ignored in mock mode.

        Returns:
            Deterministic mock response text.
        """
        # Run sync generate in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, temperature, max_tokens),
        )

    def health_check(self) -> bool:
        """Mock health check always returns True.

        Returns:
            True (mock is always available).
        """
        return True

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Mock chat method.

        Args:
            messages: List of message dicts (ignored in mock mode).
            temperature: Ignored in mock mode.
            max_tokens: Ignored in mock mode.

        Returns:
            Deterministic mock response text.
        """
        # Extract last user message if available
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        return self.generate(last_user_message, temperature, max_tokens)


class MockLLMProviderWithContext(MockLLMProvider):
    """Enhanced mock provider that generates context-aware responses.

    Provides more realistic mock responses based on prompt content,
    useful for testing RAG pipeline behavior.
    """

    def __init__(self) -> None:
        """Initialize enhanced mock provider with context-aware responses."""
        # Build response map based on common query patterns
        response_map = {
            "chunk size": "The default chunk size is 4096 tokens. This is configured via SECONDBRAIN_CHUNK_SIZE environment variable.",
            "MongoDB": "MongoDB connection is configured using SECONDBRAIN_MONGO_URI environment variable. Default is mongodb://localhost:27017.",
            "formats": "SecondBrain supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files for document ingestion.",
            "circuit breaker": "Circuit breaker can be enabled by setting SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true. This provides automatic failure handling.",
            "Ingestor": "The Ingestor class handles multi-format document parsing and automatic chunking using Docling library.",
            "semantic search": "Semantic search uses sentence-transformers embeddings with cosine similarity in MongoDB vector search. Default model is all-MiniLM-L6-v2.",
            "SecondBrain": "SecondBrain is a local document intelligence CLI tool for semantic search over documents using MongoDB and sentence-transformers.",
            "embedding": "The default embedding model is all-MiniLM-L6-v2 from sentence-transformers. It provides good balance of speed and accuracy.",
            "logging": "Logging is configured via SECONDBRAIN_LOG_LEVEL (INFO, DEBUG, WARNING, ERROR) and SECONDBRAIN_LOG_FORMAT (pretty, json).",
            "configuration": "Configuration uses SECONDBRAIN_* environment variables. Key settings include chunk_size, mongo_uri, log_level, and top_k.",
            "default": "Default values: chunk_size=4096, chunk_overlap=256, top_k=5, embedding_model=all-MiniLM-L6-v2.",
            "default chunk size": "The default chunk size in SecondBrain is 4096 tokens.",
            "What is": "This is a mock response providing information based on the query context.",
        }

        super().__init__(response_map=response_map)

    def generate(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate context-aware mock response.

        Args:
            prompt: User prompt text.
            temperature: Ignored in mock mode.
            max_tokens: Ignored in mock mode.

        Returns:
            Context-aware mock response based on prompt content.
        """
        # Check response map first
        for pattern, response in self._response_map.items():
            if pattern.lower() in prompt.lower():
                return f"[MOCK] {response}"

        # Fall back to hash-based deterministic response
        return super().generate(prompt, temperature, max_tokens)
