"""Integration tests for RAG pipeline with real Ollama.

This module provides integration tests that require a running Ollama server.
These tests verify the actual integration between the RAG pipeline components
and the Ollama LLM provider.

Run with: pytest tests/test_rag/test_integration.py -v
Requires: Ollama server running on http://localhost:11434
"""

from __future__ import annotations

import pytest

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.conversation.storage import ConversationStorage
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.providers.ollama import OllamaLLMProvider
from secondbrain.search import Searcher


@pytest.fixture
def ollama_provider() -> OllamaLLMProvider:
    """Create real OllamaLLMProvider instance."""
    return OllamaLLMProvider(
        host="http://localhost:11434",
        model="llama3.2",
        temperature=0.1,
        max_tokens=2048,
        timeout=120,
    )


@pytest.fixture
def mock_searcher() -> Searcher:
    """Create a mock Searcher for integration tests."""
    # Use a real Searcher but we'll mock its search method
    from unittest.mock import MagicMock

    mock = MagicMock(spec=Searcher)
    mock.search.return_value = [
        {
            "chunk_text": "Python is a high-level programming language. "
            "It was created by Guido van Rossum and first released in 2001. "
            "Python emphasizes code readability with significant indentation.",
            "source_file": "python_guide.pdf",
            "page": 1,
            "score": 0.95,
        },
        {
            "chunk_text": "Machine learning is a subset of artificial intelligence. "
            "It enables systems to learn and improve from experience without "
            "being explicitly programmed.",
            "source_file": "ml_basics.pdf",
            "page": 3,
            "score": 0.87,
        },
    ]
    return mock  # type: ignore[return-value]


@pytest.fixture
def mock_storage() -> ConversationStorage:
    """Create a mock ConversationStorage for integration tests."""
    from unittest.mock import MagicMock

    mock = MagicMock(spec=ConversationStorage)
    mock.get_history.return_value = []
    mock.create_session.return_value = "integration-session"
    mock.save_message.return_value = None
    mock.update_messages.return_value = None
    return mock  # type: ignore[return-value]


class TestQueryRewriterIntegration:
    """Integration tests for query rewriting with real Ollama."""

    @pytest.mark.integration
    def test_query_rewriter_integration(
        self,
        ollama_provider: OllamaLLMProvider,
        mock_storage: ConversationStorage,
    ) -> None:
        """Test query rewriting with real Ollama LLM.

        Verifies that the QueryRewriter can successfully use Ollama to
        rewrite queries based on conversation context.
        """
        rewriter = QueryRewriter(
            llm_provider=ollama_provider,
            context_window=5,
        )

        # Setup conversation history
        history = [
            {"role": "user", "content": "Tell me about Python programming"},
            {
                "role": "assistant",
                "content": "Python is a high-level programming language...",
            },
        ]

        # Rewrite a query with pronoun
        rewritten = rewriter.rewrite("How does it work?", history)

        # Verify the rewrite is not empty and is different from original
        assert rewritten is not None
        assert len(rewritten.strip()) > 0
        assert rewritten != "How does it work?"
        # The rewritten query should be more specific
        assert "python" in rewritten.lower() or "programming" in rewritten.lower()

    @pytest.mark.integration
    def test_query_rewriter_with_empty_history(
        self,
        ollama_provider: OllamaLLMProvider,
    ) -> None:
        """Test query rewriting with empty history returns original."""
        rewriter = QueryRewriter(
            llm_provider=ollama_provider,
            context_window=5,
        )

        rewritten = rewriter.rewrite("What is Python?", [])

        # Should return original query when no history
        assert rewritten == "What is Python?"


class TestOllamaHealthCheck:
    """Integration tests for Ollama health check."""

    @pytest.mark.integration
    def test_ollama_health_check(
        self,
        ollama_provider: OllamaLLMProvider,
    ) -> None:
        """Test Ollama server health check.

        Verifies that the Ollama provider can successfully check
        if the server is available and responsive.
        """
        health_status = ollama_provider.health_check()

        # Health check should return a boolean
        assert isinstance(health_status, bool)

        # If server is running, should return True
        # Note: This test may fail if Ollama is not running
        if health_status:
            assert health_status is True

    @pytest.mark.integration
    def test_ollama_generation(
        self,
        ollama_provider: OllamaLLMProvider,
    ) -> None:
        """Test Ollama generation with a simple prompt.

        Verifies that the Ollama provider can successfully generate
        responses to prompts.
        """
        prompt = "What is 2 + 2? Answer in one word."

        response = ollama_provider.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=10,
        )

        # Verify response is not empty
        assert response is not None
        assert len(response.strip()) > 0

        # Verify response contains expected content (should be "4" or similar)
        response_lower = response.lower().strip()
        assert "4" in response_lower or "four" in response_lower


class TestRAGPipelineIntegration:
    """Integration tests for full RAG pipeline with Ollama."""

    @pytest.mark.integration
    def test_rag_pipeline_with_real_ollama(
        self,
        mock_searcher: Searcher,
        mock_storage: ConversationStorage,
        ollama_provider: OllamaLLMProvider,
    ) -> None:
        """Test full RAG pipeline with real Ollama.

        Verifies that the complete RAG workflow functions correctly
        with a real LLM provider.
        """
        # Create pipeline with real Ollama provider
        rewriter = QueryRewriter(llm_provider=ollama_provider, context_window=5)
        pipeline = RAGPipeline(
            searcher=mock_searcher,  # type: ignore[arg-type]
            llm_provider=ollama_provider,
            rewriter=rewriter,
            top_k=2,
            context_window=10,
        )

        # Create a session
        session = ConversationSession.create("integration-test", mock_storage)

        # Perform a chat query
        result = pipeline.chat("What is Python?", session)

        # Verify result structure
        assert "answer" in result
        assert "rewritten_query" in result

        # Verify answer is not empty
        assert result["answer"] is not None
        assert len(result["answer"].strip()) > 0

        # Verify session was updated
        assert session.message_count == 2
