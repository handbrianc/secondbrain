"""Tests for multi-turn conversation and session management in RAG pipeline.

This module provides tests for conversational RAG capabilities, including
multi-turn chat, context window management, session persistence, query
rewriting, and session CRUD operations.
"""

from unittest.mock import MagicMock

import pytest

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.conversation.storage import ConversationStorage
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.providers.ollama import OllamaLLMProvider
from secondbrain.search import Searcher


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = [
        {"chunk_text": "Test context", "source_file": "doc.pdf", "page": 1}
    ]
    return mock


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LLM provider."""
    mock = MagicMock(spec=OllamaLLMProvider)
    mock.generate.return_value = "Generated answer"
    return mock


@pytest.fixture
def mock_rewriter() -> MagicMock:
    """Create a mock QueryRewriter."""
    mock = MagicMock(spec=QueryRewriter)
    mock.rewrite_query.return_value = "rewritten query"
    mock.context_window = 5
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
def pipeline_with_rewriter(
    mock_searcher: MagicMock,
    mock_llm_provider: MagicMock,
    mock_rewriter: MagicMock,
) -> RAGPipeline:
    """Create RAGPipeline with rewriter."""
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm_provider,
        rewriter=mock_rewriter,
        top_k=5,
        context_window=10,
    )


class TestMultiTurnChat:
    """Tests for multi-turn conversational chat."""

    def test_multi_turn_chat_sequential_queries(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_storage: MagicMock,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test sequential queries in a multi-turn conversation."""
        session = ConversationSession.create("multi-turn", mock_storage)

        # First turn - no history, so rewriter not called
        result1 = pipeline_with_rewriter.chat("What is Python?", session)
        assert result1["answer"] == "Generated answer"
        assert session.message_count == 2  # user + assistant
        mock_rewriter.rewrite_query.assert_not_called()

        # Second turn - has history, rewriter should be called
        result2 = pipeline_with_rewriter.chat("What about libraries?", session)
        assert result2["answer"] == "Generated answer"
        assert session.message_count == 4  # 2 previous + 2 new
        mock_rewriter.rewrite_query.assert_called_once()

    def test_multi_turn_chat_accumulates_context(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_storage: MagicMock,
    ) -> None:
        """Test that conversation context accumulates across turns."""
        session = ConversationSession.create("context-test", mock_storage)

        # Add multiple turns
        for i in range(3):
            pipeline_with_rewriter.chat(f"Query {i}", session)

        # Verify all messages are stored
        assert session.message_count == 6  # 3 user + 3 assistant

        # Verify history contains all messages
        history = session.get_history()
        assert len(history) == 6


class TestContextWindowManagement:
    """Tests for context window management."""

    def test_context_window_limits_history(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_storage: MagicMock,
    ) -> None:
        """Test that context window limits history size."""
        session = ConversationSession.create(
            "window-test", mock_storage, context_window=4
        )

        # Add 6 turns (12 messages)
        for i in range(6):
            pipeline_with_rewriter.chat(f"Query {i}", session)

        # Session should trim to context window
        assert session.message_count == 4
        assert len(session.get_history()) == 4

    def test_context_window_get_context_messages(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test get_context_messages respects context window."""
        session = ConversationSession.create("ctx-test", mock_storage, context_window=3)

        # Add 5 messages
        for i in range(5):
            session.add_message("user" if i % 2 == 0 else "assistant", f"Msg {i}")

        # Context should return only most recent 3
        context = session.get_context_messages()
        assert len(context) == 3
        assert context[0]["content"] == "Msg 2"


class TestSessionPersistence:
    """Tests for session persistence and loading."""

    def test_session_persistence_add_message(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test that messages are persisted to storage."""
        session = ConversationSession.create("persist-test", mock_storage)

        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")

        # Verify storage was called
        assert mock_storage.save_message.call_count == 2

    def test_session_persistence_load_session(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test loading a persisted session."""
        # Simulate existing session in storage
        existing_messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
        ]
        mock_storage.get_history.return_value = existing_messages

        session = ConversationSession.load("persisted-session", mock_storage)

        assert session is not None
        assert session.message_count == 2
        assert session.get_history() == existing_messages

    def test_session_persistence_load_nonexistent(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test loading a session that doesn't exist."""
        mock_storage.get_history.return_value = []

        session = ConversationSession.load("nonexistent", mock_storage)

        assert session is None


class TestQueryRewritingIntegration:
    """Tests for query rewriting in conversation context."""

    def test_query_rewriting_with_history(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_storage: MagicMock,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test that queries are rewritten using conversation history."""
        session = ConversationSession.create("rewrite-test", mock_storage)
        session.add_message("user", "Tell me about ACME contract")
        session.add_message("assistant", "The ACME contract is...")

        # Query with pronoun should trigger rewriting
        pipeline_with_rewriter.chat("What about pricing?", session)

        # Verify rewriter was called
        mock_rewriter.rewrite_query.assert_called_once()

    def test_query_rewriting_without_history(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_storage: MagicMock,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test that queries without history return original query."""
        session = ConversationSession.create("no-history", mock_storage)

        # First query with no history - rewriter should not be called
        result = pipeline_with_rewriter.chat("What is Python?", session)

        # When no history, rewriter is not called and original query is used
        assert result["rewritten_query"] == "What is Python?"
        mock_rewriter.rewrite_query.assert_not_called()

    def test_query_rewriting_fallback_on_error(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Test fallback to original query when rewriting fails."""
        failing_rewriter = MagicMock(spec=QueryRewriter)
        failing_rewriter.rewrite_query.side_effect = Exception("Rewrite failed")
        failing_rewriter.context_window = 5

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=failing_rewriter,
            top_k=5,
            context_window=10,
        )

        session = ConversationSession.create("fallback-test", mock_storage)
        session.add_message("user", "History")

        result = pipeline.chat("What about it?", session)

        # Should fall back to original query
        assert result["rewritten_query"] == "What about it?"


class TestSessionCRUD:
    """Tests for session create, read, update, delete operations."""

    def test_session_create_new(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test creating a new session."""
        session = ConversationSession.create("new-session", mock_storage)

        assert session is not None
        assert session._session_id == "new-session"
        assert session.is_empty is True
        assert mock_storage.create_session.called

    def test_session_read_existing(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test reading an existing session."""
        mock_storage.get_history.return_value = [{"role": "user", "content": "Hello"}]

        session = ConversationSession.load("existing", mock_storage)

        assert session is not None
        assert session.message_count == 1

    def test_session_update_messages(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test updating session messages via add_message."""
        session = ConversationSession.create("update-test", mock_storage)

        session.add_message("user", "Test message")

        # Verify message was added and persisted
        assert len(session._history) == 1
        assert mock_storage.save_message.called

    def test_session_clear_history(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test clearing session history."""
        session = ConversationSession.create("clear-test", mock_storage)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")

        session.clear_history()

        assert session.is_empty is True
        assert session.message_count == 0

    def test_session_trimming_on_update(
        self,
        mock_storage: MagicMock,
    ) -> None:
        """Test that session trimming updates storage."""
        session = ConversationSession.create(
            "trim-test", mock_storage, context_window=2
        )

        # Add messages exceeding context window
        session.add_message("user", "1")
        session.add_message("assistant", "2")
        session.add_message("user", "3")
        session.add_message("assistant", "4")

        # Should be trimmed to context window
        assert session.message_count == 2
        assert mock_storage.update_messages.called
