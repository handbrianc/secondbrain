"""Mock-based consistency tests for offline validation.

This module provides mock-based unit tests for consistency metrics that
can run without MongoDB, LLM, or other external services. These tests
validate the logic and behavior of consistency-related components.

Benefits:
- Fast execution (no service dependencies)
- Deterministic results (controlled mocks)
- CI/CD friendly (always available)
- Validates component logic without integration overhead
"""

from unittest.mock import MagicMock

import pytest
from sentence_transformers import SentenceTransformer

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.conversation.storage import ConversationStorage
from secondbrain.rag import RAGPipeline
from secondbrain.search import Searcher


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = [
        {
            "chunk_text": "SecondBrain is a local document intelligence CLI tool.",
            "source_file": "README.md",
            "page": 1,
        },
        {
            "chunk_text": "The default chunk size is 4096 tokens.",
            "source_file": "docs/config.md",
            "page": 5,
        },
    ]
    return mock


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LLM provider with deterministic responses."""
    mock = MagicMock()
    # Deterministic response for consistency testing
    mock.generate.return_value = (
        "SecondBrain is a local document intelligence CLI tool that enables "
        "semantic search over documents using embedding models and MongoDB."
    )
    return mock


@pytest.fixture
def mock_storage() -> MagicMock:
    """Create a mock ConversationStorage."""
    mock = MagicMock(spec=ConversationStorage)
    mock.get_history.return_value = []
    mock.create_session.return_value = "test-session"
    mock.save_message.return_value = None
    mock.update_messages.return_value = None
    return mock


@pytest.fixture
def mock_rewriter() -> MagicMock:
    """Create a mock QueryRewriter."""
    mock = MagicMock(spec=QueryRewriter)
    mock.rewrite.return_value = "What is the pricing for SecondBrain?"
    mock.rewrite_query.return_value = "What is the pricing for SecondBrain?"
    mock.context_window = 5
    mock.should_rewrite.return_value = True
    return mock


class TestQueryRewriterConsistency:
    """Tests for QueryRewriter consistency using mocks."""

    def test_rewriter_returns_original_without_history(self) -> None:
        """Test that rewriter returns original query when no history provided."""
        mock_llm = MagicMock()
        rewriter = QueryRewriter(mock_llm, context_window=5)

        original_query = "What is the chunk size?"
        result = rewriter.rewrite(original_query, [])

        # Should return original query unchanged
        assert result == original_query
        mock_llm.generate.assert_not_called()

    def test_rewriter_returns_original_with_empty_history(self) -> None:
        """Test that rewriter returns original query when history is empty."""
        mock_llm = MagicMock()
        rewriter = QueryRewriter(mock_llm, context_window=5)

        original_query = "How to configure MongoDB?"
        result = rewriter.rewrite(original_query, [])

        assert result == original_query
        mock_llm.generate.assert_not_called()

    def test_rewriter_uses_context_window_limit(self) -> None:
        """Test that rewriter respects context window limit."""
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Rewritten query"

        rewriter = QueryRewriter(mock_llm, context_window=3)

        # Create history longer than context window
        history = [{"role": "user", "content": f"Message {i}"} for i in range(10)]

        rewriter.rewrite("What about it?", history)

        # Verify LLM was called (history was processed)
        mock_llm.generate.assert_called_once()

    def test_rewriter_fallback_on_llm_error(self) -> None:
        """Test that rewriter falls back to original query on LLM error."""
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = Exception("LLM failed")

        rewriter = QueryRewriter(mock_llm, context_window=5)

        history = [{"role": "user", "content": "Previous context"}]
        original_query = "What about it?"

        result = rewriter.rewrite(original_query, history)

        # Should fall back to original query
        assert result == original_query

    def test_should_rewrite_detects_pronouns(self) -> None:
        """Test that should_rewrite correctly identifies pronouns."""
        mock_llm = MagicMock()
        rewriter = QueryRewriter(mock_llm, context_window=5)

        # Queries with pronouns should trigger rewriting
        assert rewriter.should_rewrite("How does it work?") is True
        assert rewriter.should_rewrite("What about this?") is True
        assert rewriter.should_rewrite("Tell me about that.") is True

    def test_should_rewrite_standalone_queries(self) -> None:
        """Test that standalone queries don't trigger rewriting."""
        mock_llm = MagicMock()
        rewriter = QueryRewriter(mock_llm, context_window=5)

        # Standalone queries should not trigger rewriting
        assert rewriter.should_rewrite("What is Python?") is False
        assert rewriter.should_rewrite("How to install MongoDB?") is False


class TestConversationSessionConsistency:
    """Tests for ConversationSession consistency using mocks."""

    def test_session_empty_after_create(self, mock_storage: MagicMock) -> None:
        """Test that newly created session is empty."""
        session = ConversationSession.create("test-123", mock_storage)

        assert session.is_empty is True
        assert session.message_count == 0
        assert session.get_history() == []

    def test_session_adds_messages_consistently(self, mock_storage: MagicMock) -> None:
        """Test that session consistently adds messages."""
        session = ConversationSession.create("test-123", mock_storage)

        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        assert session.message_count == 2
        assert len(session.get_history()) == 2

        # Verify messages are in correct order
        history = session.get_history()
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi!"

    def test_session_context_window_limits_history(
        self, mock_storage: MagicMock
    ) -> None:
        """Test that session respects context window limit."""
        session = ConversationSession.create("test-123", mock_storage, context_window=3)

        # Add more messages than context window
        for i in range(5):
            session.add_message("user" if i % 2 == 0 else "assistant", f"Message {i}")

        # Should be trimmed to context window
        assert session.message_count == 3
        assert len(session.get_history()) == 3

    def test_session_get_history_returns_copy(self, mock_storage: MagicMock) -> None:
        """Test that get_history returns a copy, not the original."""
        session = ConversationSession.create("test-123", mock_storage)
        session.add_message("user", "Test")

        history = session.get_history()
        history.append({"role": "fake", "content": "Fake message"})

        # Original should be unchanged
        assert session.message_count == 1
        assert len(session.get_history()) == 1

    def test_session_clear_history_works(self, mock_storage: MagicMock) -> None:
        """Test that clear_history empties the session."""
        session = ConversationSession.create("test-123", mock_storage)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        assert session.message_count == 2
        assert session.is_empty is False

        session.clear_history()

        assert session.message_count == 0
        assert session.is_empty is True


class TestRAGPipelineConsistency:
    """Tests for RAGPipeline consistency using mocks."""

    def test_pipeline_query_returns_consistent_structure(
        self, mock_searcher: MagicMock, mock_llm_provider: MagicMock
    ) -> None:
        """Test that pipeline.query returns consistent result structure."""
        pipeline = RAGPipeline(
            searcher=mock_searcher, llm_provider=mock_llm_provider, top_k=5
        )

        result = pipeline.query("What is SecondBrain?")

        # Verify consistent structure
        assert "answer" in result
        assert "query" in result
        assert isinstance(result["answer"], str)
        assert isinstance(result["query"], str)

    def test_pipeline_query_with_show_sources(
        self, mock_searcher: MagicMock, mock_llm_provider: MagicMock
    ) -> None:
        """Test that show_sources adds sources to result."""
        pipeline = RAGPipeline(
            searcher=mock_searcher, llm_provider=mock_llm_provider, top_k=5
        )

        result = pipeline.query("What is SecondBrain?", show_sources=True)

        assert "sources" in result
        assert isinstance(result["sources"], list)
        assert len(result["sources"]) > 0

    def test_pipeline_chat_with_session(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Test that pipeline.chat works with session."""
        pipeline = RAGPipeline(
            searcher=mock_searcher, llm_provider=mock_llm_provider, top_k=5
        )

        session = ConversationSession.create("test-session", mock_storage)

        result = pipeline.chat("What is SecondBrain?", session)

        assert "answer" in result
        assert "rewritten_query" in result
        assert session.message_count == 2  # user + assistant

    def test_pipeline_chat_accumulates_history(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Test that chat accumulates conversation history."""
        pipeline = RAGPipeline(
            searcher=mock_searcher, llm_provider=mock_llm_provider, top_k=5
        )

        session = ConversationSession.create("test-session", mock_storage)

        # Multiple turns
        for i in range(3):
            pipeline.chat(f"Query {i}", session)

        # Should have 6 messages (3 user + 3 assistant)
        assert session.message_count == 6


class TestEmbeddingConsistency:
    """Tests for embedding consistency using the actual model."""

    @pytest.fixture
    def embedding_model(self) -> SentenceTransformer:
        """Load embedding model for testing."""
        return SentenceTransformer("all-MiniLM-L6-v2")

    def test_embedding_determinism(self, embedding_model: SentenceTransformer) -> None:
        """Test that embeddings are deterministic for same input."""
        text = "This is a test sentence for embedding consistency."

        embedding1 = embedding_model.encode(text, convert_to_numpy=True)
        embedding2 = embedding_model.encode(text, convert_to_numpy=True)

        # Embeddings should be identical
        import numpy as np

        assert np.allclose(embedding1, embedding2, rtol=1e-5)

    def test_embedding_cosine_similarity_self(
        self, embedding_model: SentenceTransformer
    ) -> None:
        """Test that text has cosine similarity of 1.0 with itself."""
        text = "Testing cosine similarity with self."

        from sklearn.metrics.pairwise import cosine_similarity

        embedding = embedding_model.encode(text, convert_to_numpy=True)
        embedding = embedding.reshape(1, -1)

        similarity = cosine_similarity(embedding, embedding)[0][0]

        # Self-similarity should be 1.0
        assert abs(similarity - 1.0) < 1e-5

    def test_embedding_semantic_similarity(
        self, embedding_model: SentenceTransformer
    ) -> None:
        """Test that semantically similar texts have high cosine similarity."""
        from sklearn.metrics.pairwise import cosine_similarity

        text1 = "The quick brown fox jumps over the lazy dog."
        text2 = "A fast brown fox leaps over a sleepy dog."

        embedding1 = embedding_model.encode(text1, convert_to_numpy=True)
        embedding2 = embedding_model.encode(text2, convert_to_numpy=True)

        embedding1 = embedding1.reshape(1, -1)
        embedding2 = embedding2.reshape(1, -1)

        similarity = cosine_similarity(embedding1, embedding2)[0][0]

        # Semantically similar texts should have high similarity
        assert similarity > 0.5

    def test_embedding_dissimilarity(
        self, embedding_model: SentenceTransformer
    ) -> None:
        """Test that unrelated texts have lower cosine similarity."""
        from sklearn.metrics.pairwise import cosine_similarity

        text1 = "Machine learning is a subset of artificial intelligence."
        text2 = "Cooking pasta requires boiling water and adding salt."

        embedding1 = embedding_model.encode(text1, convert_to_numpy=True)
        embedding2 = embedding_model.encode(text2, convert_to_numpy=True)

        embedding1 = embedding1.reshape(1, -1)
        embedding2 = embedding2.reshape(1, -1)

        similarity = cosine_similarity(embedding1, embedding2)[0][0]

        # Unrelated texts should have lower similarity
        assert similarity < 0.7
