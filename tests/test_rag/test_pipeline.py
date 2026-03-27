"""Tests for RAGPipeline module.

This module provides comprehensive unit tests for the RAGPipeline class,
covering all public and private methods, edge cases, and orchestration logic.
"""

from unittest.mock import MagicMock

import pytest

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.search import Searcher


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = []
    return mock


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LocalLLMProvider instance."""
    mock = MagicMock(spec=LocalLLMProvider)
    mock.generate.return_value = "Generated answer"
    mock.health_check.return_value = True
    return mock


@pytest.fixture
def mock_rewriter() -> MagicMock:
    """Create a mock QueryRewriter instance."""
    mock = MagicMock(spec=QueryRewriter)
    mock.rewrite_query.return_value = "rewritten query"
    mock.should_rewrite.return_value = True
    mock.context_window = 10
    return mock


@pytest.fixture
def mock_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Mock configuration for pipeline tests."""
    config: dict[str, str] = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27017",
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_LOCALHOST": "http://localhost:11434",
        "SECONDBRAIN_LOCAL_EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "SECONDBRAIN_CHUNK_SIZE": "512",
        "SECONDBRAIN_CHUNK_OVERLAP": "50",
        "SECONDBRAIN_DEFAULT_TOP_K": "5",
        "SECONDBRAIN_EMBEDDING_DIMENSIONS": "384",
        "SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS": "10",
        "SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS": "1.0",
        "SECONDBRAIN_CONNECTION_CACHE_TTL": "60.0",
        "SECONDBRAIN_LLM_TEMPERATURE": "0.7",
        "SECONDBRAIN_LLM_MAX_TOKENS": "4096",
    }
    for key, value in config.items():
        monkeypatch.setenv(key, value)
    return config


@pytest.fixture
def pipeline_with_mocks(
    mock_searcher: MagicMock,
    mock_llm_provider: MagicMock,
    mock_config: dict[str, str],
) -> RAGPipeline:
    """Create RAGPipeline with mocked dependencies."""
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm_provider,
        top_k=5,
        context_window=10,
    )


@pytest.fixture
def pipeline_with_rewriter(
    mock_searcher: MagicMock,
    mock_llm_provider: MagicMock,
    mock_rewriter: MagicMock,
    mock_config: dict[str, str],
) -> RAGPipeline:
    """Create RAGPipeline with rewriter for chat tests."""
    return RAGPipeline(
        searcher=mock_searcher,
        llm_provider=mock_llm_provider,
        rewriter=mock_rewriter,
        top_k=5,
        context_window=10,
    )


class TestRAGPipelineInit:
    """Tests for RAGPipeline initialization."""

    def test_init_default_parameters(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Test initialization with default parameters."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
        )
        assert pipeline._searcher == mock_searcher
        assert pipeline._llm_provider == mock_llm_provider
        assert pipeline._rewriter is None
        assert pipeline._top_k == 5
        assert pipeline._context_window == 10

    def test_init_custom_parameters(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_rewriter: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Test initialization with custom parameters."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=mock_rewriter,
            top_k=10,
            context_window=20,
        )
        assert pipeline._top_k == 10
        assert pipeline._context_window == 20
        assert pipeline._rewriter == mock_rewriter


class TestRAGPipelineQuery:
    """Tests for RAGPipeline.query() method."""

    def test_query_single_turn_success(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test single-turn query with successful retrieval and generation."""
        mock_chunks = [
            {
                "chunk_text": "Python is a programming language",
                "source_file": "python.pdf",
                "page": 1,
            }
        ]
        mock_searcher.search.return_value = mock_chunks
        mock_llm_provider.generate.return_value = "Python is a high-level language"

        result = pipeline_with_mocks.query("What is Python?")

        assert result["answer"] == "Python is a high-level language"
        assert result["query"] == "What is Python?"
        mock_searcher.search.assert_called_once_with("What is Python?", top_k=5)
        mock_llm_provider.generate.assert_called_once()

    def test_query_with_show_sources(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test query with show_sources=True includes chunks."""
        mock_chunks = [
            {
                "chunk_text": "Test chunk",
                "source_file": "test.pdf",
                "page": 1,
            }
        ]
        mock_searcher.search.return_value = mock_chunks

        result = pipeline_with_mocks.query("Test query", show_sources=True)

        assert "sources" in result
        assert result["sources"] == mock_chunks

    def test_query_with_custom_top_k(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test query with custom top_k parameter."""
        mock_searcher.search.return_value = []

        pipeline_with_mocks.query("Test query", top_k=10)

        mock_searcher.search.assert_called_once_with("Test query", top_k=10)

    def test_query_with_no_results_and_show_sources(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test query with no results and show_sources=True covers branch."""
        mock_searcher.search.return_value = []

        result = pipeline_with_mocks.query("Test query", show_sources=True)

        assert "sources" in result
        assert result["sources"] == []
        assert "couldn't find" in result["answer"].lower()

    def test_query_handles_exception_gracefully(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test query handles exceptions and returns error response."""
        mock_searcher.search.side_effect = RuntimeError("Connection failed")

        result = pipeline_with_mocks.query("Test query")

        assert "answer" in result
        assert (
            "error" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
        )
        assert result["query"] == "Test query"


class TestRAGPipelineChat:
    """Tests for RAGPipeline.chat() method."""

    def test_chat_multi_turn_with_history(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test multi-turn chat with conversation history."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "What is Python?")
        session.add_message("assistant", "Python is a language")

        mock_chunks = [
            {"chunk_text": "Python docs", "source_file": "docs.pdf", "page": 1}
        ]
        mock_searcher.search.return_value = mock_chunks
        mock_llm_provider.generate.return_value = "More Python info"

        result = pipeline_with_rewriter.chat("What about libraries?", session)

        assert result["answer"] == "More Python info"
        assert "rewritten_query" in result
        mock_rewriter.rewrite_query.assert_called_once()
        assert session.message_count == 4  # 2 existing + 2 new

    def test_chat_without_rewriter(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test chat without rewriter uses original query."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "Hello")

        mock_searcher.search.return_value = [
            {"chunk_text": "test", "source_file": "t.pdf", "page": 1}
        ]

        result = pipeline_with_mocks.chat("How are you?", session)

        assert result["answer"] == "Generated answer"
        assert result["rewritten_query"] == "How are you?"

    def test_chat_with_show_sources(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test chat with show_sources=True."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_chunks = [{"chunk_text": "chunk", "source_file": "f.pdf", "page": 1}]
        mock_searcher.search.return_value = mock_chunks

        result = pipeline_with_rewriter.chat("Query", session, show_sources=True)

        assert "sources" in result
        assert result["sources"] == mock_chunks

    def test_chat_with_no_results_and_show_sources(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test chat with no results and show_sources=True covers branch."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_searcher.search.return_value = []

        result = pipeline_with_rewriter.chat("Query", session, show_sources=True)

        assert (
            result["answer"]
            == "I couldn't find relevant documents for your query: Query"
        )
        assert "sources" in result
        assert result["sources"] == []

    def test_chat_handles_exception_gracefully(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test chat exception handling covers error branch."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_searcher.search.side_effect = RuntimeError("Search failed")

        result = pipeline_with_rewriter.chat("Query", session)

        assert "answer" in result
        assert (
            "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        )


class TestRAGPipelineFormatContext:
    """Tests for RAGPipeline._format_context() method."""

    def test_format_context_single_chunk(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test formatting a single context chunk."""
        chunks = [
            {
                "chunk_text": "Hello world",
                "source_file": "doc.pdf",
                "page": 1,
            }
        ]

        result = pipeline_with_mocks._format_context(chunks)

        assert "Source: doc.pdf (page 1)" in result
        assert "Hello world" in result

    def test_format_context_multiple_chunks(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test formatting multiple context chunks."""
        chunks = [
            {"chunk_text": "Chunk 1", "source_file": "doc1.pdf", "page": 1},
            {"chunk_text": "Chunk 2", "source_file": "doc2.pdf", "page": 2},
        ]

        result = pipeline_with_mocks._format_context(chunks)

        assert "Chunk 1" in result
        assert "Chunk 2" in result
        assert result.count("Source:") == 2

    def test_format_context_empty_list(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test formatting empty chunk list returns empty string."""
        result = pipeline_with_mocks._format_context([])
        assert result == ""

    def test_format_context_truncates_long_chunks(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that chunks longer than 500 chars are truncated."""
        long_text = "A" * 600
        chunks = [{"chunk_text": long_text, "source_file": "doc.pdf", "page": 1}]

        result = pipeline_with_mocks._format_context(chunks)

        assert "..." in result
        assert len(result.split("\n")[1]) <= 503  # 500 + "..."

    def test_format_context_respects_max_chars(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that context respects max_chars limit."""
        chunks = [
            {"chunk_text": "X" * 100, "source_file": f"doc{i}.pdf", "page": 1}
            for i in range(10)
        ]

        result = pipeline_with_mocks._format_context(chunks, max_chars=300)

        assert len(result) <= 300

    def test_format_context_handles_alternative_keys(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test formatting with alternative dictionary keys."""
        chunks = [
            {
                "text": "Alternative text key",
                "source": "alt.pdf",
                "page_number": 5,
            }
        ]

        result = pipeline_with_mocks._format_context(chunks)

        assert "Alternative text key" in result
        assert "Source: alt.pdf (page 5)" in result


class TestRAGPipelineBuildPrompt:
    """Tests for RAGPipeline._build_prompt() method."""

    def test_build_prompt_basic(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test basic prompt building with context and query."""
        prompt = pipeline_with_mocks._build_prompt("What is Python?", "Python context")

        assert "You are a helpful assistant" in prompt
        assert "Context:" in prompt
        assert "Python context" in prompt
        assert "Question: What is Python?" in prompt
        assert "Answer:" in prompt

    def test_build_prompt_with_empty_context(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test prompt building with empty context."""
        prompt = pipeline_with_mocks._build_prompt("Query", "")

        assert "No relevant context was found" in prompt

    def test_build_prompt_with_conversation_history(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test prompt building with conversation history."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        prompt = pipeline_with_mocks._build_prompt("How are you?", "Context", history)

        assert "Conversation History:" in prompt
        assert "User: Hello" in prompt
        assert "Assistant: Hi there" in prompt

    def test_build_prompt_system_instruction_present(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that system instruction is always present."""
        prompt = pipeline_with_mocks._build_prompt("Query", "Context")

        assert "Answer questions based on the provided context" in prompt
        assert "I cannot find the answer in the provided documents" in prompt


class TestRAGPipelineHandleNoResults:
    """Tests for RAGPipeline._handle_no_results() method."""

    def test_handle_no_returns_fallback_message(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test fallback message includes original query."""
        result = pipeline_with_mocks._handle_no_results("What is X?")

        assert "couldn't find relevant documents" in result.lower()
        assert "What is X?" in result

    def test_handle_no_results_various_queries(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test fallback message with various query types."""
        test_queries = [
            "What is machine learning?",
            "How does the API work?",
            "Tell me about pricing",
        ]

        for query in test_queries:
            result = pipeline_with_mocks._handle_no_results(query)
            assert query in result


class TestRAGPipelineQueryRewriting:
    """Tests for RAGPipeline query rewriting integration."""

    def test_rewrite_with_history_calls_rewriter(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test that query rewriting is called with history."""
        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "Previous query")

        pipeline_with_rewriter._rewrite_query_with_history("Current query", session)

        mock_rewriter.rewrite_query.assert_called_once()

    def test_rewrite_without_rewriter_returns_original(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that without rewriter, original query is returned."""
        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "History")

        result = pipeline_with_mocks._rewrite_query_with_history("Query", session)

        assert result == "Query"

    def test_rewrite_with_empty_history_returns_original(
        self,
        pipeline_with_rewriter: RAGPipeline,
    ) -> None:
        """Test that empty history returns original query."""
        session = ConversationSession("test", MagicMock(), context_window=10)

        result = pipeline_with_rewriter._rewrite_query_with_history("Query", session)

        assert result == "Query"

    def test_rewrite_handles_exception_gracefully(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test that rewriting exceptions fall back to original query."""
        session = ConversationSession("test", MagicMock(), context_window=10)
        session.add_message("user", "History")
        mock_rewriter.rewrite_query.side_effect = RuntimeError("Rewrite failed")

        result = pipeline_with_rewriter._rewrite_query_with_history("Query", session)

        assert result == "Query"


class TestRAGPipelineFormatHistory:
    """Tests for RAGPipeline._format_history() method."""

    def test_format_history_basic(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test basic history formatting."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        result = pipeline_with_mocks._format_history(history)

        assert "User: Hello" in result
        assert "Assistant: Hi" in result

    def test_format_history_empty(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test empty history returns empty string."""
        result = pipeline_with_mocks._format_history([])
        assert result == ""

    def test_format_history_handles_missing_keys(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test history formatting with missing keys."""
        history = [{"role": "user"}]  # Missing content

        result = pipeline_with_mocks._format_history(history)

        assert "User:" in result


class TestRAGPipelineErrorHandling:
    """Tests for RAGPipeline error handling and edge cases."""

    def test_query_error_creates_response(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test error response creation."""
        result = pipeline_with_mocks._create_error_response(
            "Connection error", "Test query"
        )

        assert result["answer"].startswith("I apologize")
        assert result["query"] == "Test query"

    def test_query_with_special_characters(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test query with special characters."""
        mock_searcher.search.return_value = [
            {"chunk_text": "Test", "source_file": "t.pdf", "page": 1}
        ]

        result = pipeline_with_mocks.query('What is <tag>&"special"?')

        assert "answer" in result

    @pytest.mark.parametrize(
        "retrieval_count",
        [0, 1, 3, 5, 10],
        ids=["no_results", "single", "few", "default", "many"],
    )
    def test_query_various_retrieval_counts(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        retrieval_count: int,
    ) -> None:
        """Test query with various numbers of retrieved chunks."""
        mock_chunks = [
            {"chunk_text": f"Chunk {i}", "source_file": "doc.pdf", "page": 1}
            for i in range(retrieval_count)
        ]
        mock_searcher.search.return_value = mock_chunks

        result = pipeline_with_mocks.query("Test query")

        assert "answer" in result
        if retrieval_count == 0:
            assert "couldn't find" in result["answer"].lower()


class TestRAGPipelineThreeLayerArchitecture:
    """Tests for the three-layer RAG architecture integration."""

    def test_presentation_to_retrieval_flow(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test flow from query to retrieval layer."""
        mock_searcher.search.return_value = [
            {"chunk_text": "Data", "source_file": "f.pdf", "page": 1}
        ]

        result = pipeline_with_mocks.query("Query")

        assert mock_searcher.search.called
        assert result["query"] == "Query"

    def test_retrieval_to_generation_flow(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test flow from retrieval to generation layer."""
        mock_searcher.search.return_value = [
            {"chunk_text": "Context data", "source_file": "f.pdf", "page": 1}
        ]

        pipeline_with_mocks.query("Query")

        assert mock_searcher.search.called
        assert mock_llm_provider.generate.called

    def test_context_formatting_between_layers(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test context is properly formatted between retrieval and generation."""
        mock_chunks = [{"chunk_text": "Text", "source_file": "file.pdf", "page": 3}]
        mock_searcher.search.return_value = mock_chunks

        context = pipeline_with_mocks._format_context(mock_chunks)
        prompt = pipeline_with_mocks._build_prompt("Query", context)

        assert "Source: file.pdf (page 3)" in prompt
        assert "Text" in prompt

