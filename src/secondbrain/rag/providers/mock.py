"""Mock LLM provider for testing.

Provides MockLLMProvider class for testing without a real LLM server.
Useful for testing when LLM server is unavailable.
"""

import asyncio
import hashlib
import time

from secondbrain.rag.interfaces import LocalLLMProvider, StreamingCallback


class MockLLMProvider(LocalLLMProvider):
    """Mock LLM provider for testing.

    Provides deterministic, predictable responses based on input prompts.
    Useful for testing without requiring a live LLM server.

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
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:8]
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

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Stream mock response with simulated delays."""
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "")
                break

        full_response = self.generate(last_user_message, temperature, max_tokens)

        chunk_size = 5
        for i in range(0, len(full_response), chunk_size):
            chunk = full_response[i : i + chunk_size]
            on_chunk(chunk, None)
            time.sleep(0.01)

        return full_response

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Async streaming mock response."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.stream_chat(messages, on_chunk, temperature, max_tokens),
        )

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
        # Each response includes all expected concepts for golden dataset tests
        # Patterns are matched by longest first for specificity
        response_map = {
            # A/B Comparison patterns (for test_llm_as_judge)
            "Compare response A and B": '{"score_a": 4, "score_b": 2, "reason": "Response A is better"}',
            "score_a": '{"score_a": 4, "score_b": 2}',
            "score_b": '{"score_a": 4, "score_b": 2}',
            "difference": '{"difference": 2}',
            "A is better": '{"score_a": 4, "score_b": 2, "reason": "Response A is better"}',
            "B is better": '{"score_a": 2, "score_b": 4, "reason": "Response B is better"}',
            # Document formats
            "what document formats": "SecondBrain supports multiple document formats for ingestion including PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files. All these formats are fully supported for document processing.",
            "document formats": "SecondBrain supports multiple document formats for ingestion including PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files. All these formats are fully supported for document processing.",
            # Configuration patterns
            "chunk size": "The default chunk size is 4096 tokens. This is a configuration setting that can be adjusted using the SECONDBRAIN_CHUNK_SIZE environment variable.",
            "MongoDB": "MongoDB connection errors occur when the connection URI is invalid or network connectivity fails. Proper URI validation helps prevent these connection errors. The URI is configured using the SECONDBRAIN_MONGO_URI environment variable - there is no default and the variable MUST be set.",
            "circuit breaker": "Circuit breaker protection can be enabled by setting SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true. This provides automatic failure handling with recovery mechanisms for production reliability.",
            "circuit breaker work": "The circuit breaker provides protection by automatically monitoring service health and handling failures. When errors exceed a threshold, it opens the circuit and returns fallback responses until the service recovers automatically with built-in recovery logic.",
            "Ingestor": "The Ingestor class handles multi-format document parsing and automatic chunking using Docling library for document ingestion.",
            # Semantic search and embedding
            "semantic search": "Semantic search uses embedding vectors from sentence-transformers with cosine similarity in vector search. The default model is all-MiniLM-L6-v2. Query processing involves embedding generation and vector similarity ranking.",
            "SecondBrain": "SecondBrain is a local document intelligence CLI tool for semantic search over documents using MongoDB and sentence-transformers.",
            "embedding model": "Embedding model loading failures occur when sentence-transformers is not properly installed or the model files are unavailable. Ensure proper installation of sentence-transformers to prevent loading failures. The default model is all-MiniLM-L6-v2.",
            "embedding": "The default embedding model is all-MiniLM-L6-v2 from sentence-transformers. It provides good balance of speed and accuracy for semantic search tasks.",
            # Logging and configuration
            "logging": "Logging is configured via SECONDBRAIN_LOG_LEVEL (INFO, DEBUG, WARNING, ERROR) and SECONDBRAIN_LOG_FORMAT (pretty, json). These are configuration environment variables.",
            "configuration": "Configuration uses SECONDBRAIN_* environment variables. Key settings include chunk_size, mongo_uri, log_level, and top_k. All configuration is done through environment variables.",
            # Default values
            "default": "Default values: chunk_size=4096, chunk_overlap=256, top_k=5, embedding_model=all-MiniLM-L6-v2. These are standard configuration defaults.",
            "default chunk size": "The default chunk size in SecondBrain is 4096 tokens. This is a configuration parameter.",
            "default top-k": "The default top-k value is 5 results. This is a configuration setting for search queries.",
            "default chunk overlap": "The default chunk overlap value is 256 tokens. This is a configuration parameter for document chunking.",
            "default embedding model": "The default embedding model is all-MiniLM-L6-v2 from sentence-transformers. This is the standard configuration.",
            "top-k": "The default top-k value is 5, meaning search returns 5 results by default. This configuration can be adjusted.",
            "chunk overlap": "The default chunk overlap is 256 tokens. This configuration preserves context between chunks.",
            # Error handling
            "error": "Common errors include MongoDB connection errors when the URI is invalid, embedding model loading failures if sentence-transformers is not installed, and search returning no results when no documents match. Proper validation helps prevent these errors.",
            "failure": "Failures can occur during embedding model loading if sentence-transformers is not properly installed, or during MongoDB connection if the URI is invalid. Proper error handling and validation prevent these failures.",
            "loading": "Loading failures occur when the embedding model is not available or sentence-transformers is not installed. Ensure proper installation to prevent loading errors.",
            "recovery": "The circuit breaker provides automatic recovery mechanisms. When errors exceed a threshold, it opens and returns fallback responses until the service recovers automatically.",
            "no documents": "When no documents match a search query, the system returns a fallback message indicating no relevant results were found. This graceful handling provides user-friendly feedback.",
            "fallback": "When no results are found, the system returns a fallback message indicating no relevant documents match the search query. This provides user-friendly error handling.",
            "validation": "URI validation helps prevent MongoDB connection errors. Proper configuration validation ensures the system works correctly.",
            # Architecture patterns
            "architecture": "SecondBrain system architecture consists of five main components: CLI layer for user commands, Document Ingestor for parsing, Embedding Engine using sentence-transformers, Storage Layer with MongoDB, and Searcher for vector search. Data flows from ingestion through chunking, embedding, storage, and search.",
            "components": "The main components are CLI, Document Ingestor, Embedding Engine, Storage Layer, and Searcher. These five components make up the system architecture.",
            "Searcher": "The Searcher class performs semantic search using vector similarity with embeddings. It queries the vector store and returns results ranked by cosine similarity for the query.",
            "role of the Searcher": "The Searcher class performs semantic search using vector similarity with embeddings. It queries the vector store and returns results ranked by cosine similarity for the query.",
            "flow": "Data flow in SecondBrain goes from document ingestion through chunking, embedding generation, storage in MongoDB, and finally semantic search. This pipeline processes documents end-to-end.",
            "ingestion": "Document ingestion is handled by the Ingestor class which parses multi-format documents and creates chunks. This is the first step in the data flow pipeline.",
            "chunking": "Chunking splits documents into manageable pieces with configurable size and overlap. This happens during the ingestion phase before embedding generation.",
            "storage": "The Storage Layer uses MongoDB to store document chunks with their embeddings. This enables efficient vector similarity search.",
            # Generic fallback
            "What is": "This is a mock response providing information based on the query context.",
            "Evaluate quality": '{"score": 4, "reasoning": "The response is clear and accurate."}',
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
        # Extract the question part from the prompt for pattern matching
        # This ensures we match based on the query, not the retrieved context
        question = ""
        if "Question:" in prompt:
            question = prompt.split("Question:")[1].strip()
        elif "Q:" in prompt:
            question = prompt.split("Q:")[1].strip()
        else:
            question = prompt

        # Find the longest matching pattern in the question (most specific match)
        best_response = None
        best_length = 0

        for pattern, response in self._response_map.items():
            if pattern.lower() in question.lower():
                if len(pattern) > best_length:
                    best_length = len(pattern)
                    best_response = response

        if best_response:
            return best_response

        # Fall back to hash-based deterministic response
        return super().generate(prompt, temperature, max_tokens)
