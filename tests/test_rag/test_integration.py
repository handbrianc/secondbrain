"""RAG pipeline tests with mocked Ollama for fast execution.

These tests verify RAG pipeline functionality using mocked Ollama provider
to avoid 10-20s overhead from real LLM calls.

For real Ollama integration tests, run: pytest -m "integration"
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.conversation.storage import ConversationStorage
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.providers.ollama import OllamaLLMProvider
from secondbrain.search import Searcher


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher for tests."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = [
        {
            "chunk_text": "Python is a high-level programming language. "
            "It was created by Guido van Rossum and first released in 2001.",
            "source_file": "python_guide.pdf",
            "page": 1,
            "score": 0.95,
        },
        {
            "chunk_text": "Machine learning is a subset of artificial intelligence. "
            "It enables systems to learn and improve from experience.",
            "source_file": "ml_basics.pdf",
            "page": 3,
            "score": 0.87,
        },
    ]
    return mock


@pytest.fixture
def mock_storage() -> MagicMock:
    """Create a mock ConversationStorage for tests."""
    mock = MagicMock(spec=ConversationStorage)
    mock.get_history.return_value = []
    mock.create_session.return_value = "test-session"
    mock.save_message.return_value = None
    mock.update_messages.return_value = None
    return mock


@pytest.fixture
def mock_ollama_provider() -> MagicMock:
    mock = MagicMock(spec=OllamaLLMProvider)
    type(mock).health_check = MagicMock(return_value=True)
    type(mock).generate = MagicMock(return_value="Mock response")
    type(mock).generate_stream = MagicMock(return_value=iter(["mock ", "response"]))
    return mock


class TestQueryRewriterWithMock:
    """Query rewriting tests with mocked Ollama."""

    def test_query_rewriter_with_mock(
        self,
        mock_ollama_provider: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Test query rewriting with mocked Ollama LLM."""
        rewriter = QueryRewriter(
            llm_provider=mock_ollama_provider,
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

    def test_query_rewriter_empty_history(
        self,
        mock_ollama_provider: MagicMock,
    ) -> None:
        """Test query rewriting with empty history returns original."""
        rewriter = QueryRewriter(
            llm_provider=mock_ollama_provider,
            context_window=5,
        )

        rewritten = rewriter.rewrite("What is Python?", [])

        # Should return original query when no history
        assert rewritten == "What is Python?"


class TestOllamaMock:
    """Tests for mocked Ollama provider behavior."""

    def test_mock_health_check(self, mock_ollama_provider: MagicMock) -> None:
        """Test mock health check returns True."""
        health_status = mock_ollama_provider.health_check()
        assert health_status is True

    def test_mock_generation(self, mock_ollama_provider: MagicMock) -> None:
        """Test mock generation returns non-empty response."""
        prompt = "What is 2 + 2? Answer in one word."

        response = mock_ollama_provider.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=10,
        )

        assert response is not None
        assert len(response.strip()) > 0


class TestRAGPipelineWithMock:
    """RAG pipeline tests with mocked Ollama for fast execution."""

    def test_rag_pipeline_with_mocked_ollama(
        self,
        mock_searcher: MagicMock,
        mock_storage: MagicMock,
        mock_ollama_provider: MagicMock,
    ) -> None:
        """Test full RAG pipeline with mocked Ollama.

        Verifies that the complete RAG workflow functions correctly
        without real LLM calls (saves ~15s per test).
        """
        # Create pipeline with mocked Ollama provider
        rewriter = QueryRewriter(llm_provider=mock_ollama_provider, context_window=5)
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_ollama_provider,
            rewriter=rewriter,
            top_k=2,
            context_window=10,
        )

        # Create a session
        session = ConversationSession.create("mock-test", mock_storage)

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

    def test_rag_pipeline_multi_turn_with_mock(
        self,
        mock_searcher: MagicMock,
        mock_storage: MagicMock,
        mock_ollama_provider: MagicMock,
    ) -> None:
        """Test multi-turn conversation with mocked Ollama."""
        rewriter = QueryRewriter(llm_provider=mock_ollama_provider, context_window=5)
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_ollama_provider,
            rewriter=rewriter,
            top_k=2,
            context_window=10,
        )

        session = ConversationSession.create("multi-turn-test", mock_storage)

        # First query
        result1 = pipeline.chat("Tell me about Python", session)
        assert result1["answer"] is not None

        # Second query (should use context from first)
        result2 = pipeline.chat("What about its history?", session)
        assert result2["answer"] is not None

        # Session should have both messages
        assert session.message_count == 4  # 2 user + 2 assistant
