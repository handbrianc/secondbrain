"""Tests for RAGPipeline module.

This module provides comprehensive unit tests for the RAGPipeline class,
covering all public and private methods, edge cases, and orchestration logic.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.config import Config
from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.search import Searcher

# Get test config
_test_config = Config()

# Default LLM endpoint for tests
TEST_LLM_HOST = "http://localhost:11434"


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    mock = MagicMock(spec=Searcher)
    mock.search.return_value = []
    mock.search_async = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_llm_provider() -> MagicMock:
    """Create a mock LocalLLMProvider instance."""
    mock = MagicMock(spec=LocalLLMProvider)
    mock.generate.return_value = "Generated answer"
    mock.health_check.return_value = True
    mock.agenerate = AsyncMock(return_value="Async generated answer")
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
        "SECONDBRAIN_MONGO_URI": _test_config.mongo_uri,
        "SECONDBRAIN_MONGO_DB": "test_secondbrain",
        "SECONDBRAIN_MONGO_COLLECTION": "test_embeddings",
        "SECONDBRAIN_LOCALHOST": TEST_LLM_HOST,
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
        assert pipeline._context_window == 5  # Default per spec

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
        assert "=== DOCUMENT CONTEXT START ===" in prompt
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

        assert "You are a helpful assistant" in prompt
        assert "=== DOCUMENT CONTEXT START ===" in prompt
        assert "=== DOCUMENT CONTEXT END ===" in prompt


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


class TestRAGPipelineAsync:
    """Tests for RAGPipeline async methods."""

    @pytest.mark.asyncio
    async def test_query_async_single_turn_success(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test async single-turn query with successful retrieval and generation."""
        mock_chunks = [
            {
                "chunk_text": "Python is a programming language",
                "source_file": "python.pdf",
                "page": 1,
            }
        ]
        mock_searcher.search_async.return_value = mock_chunks
        mock_llm_provider.agenerate.return_value = "Python is a high-level language"

        result = await pipeline_with_mocks.query_async("What is Python?")

        assert result["answer"] == "Python is a high-level language"
        assert result["query"] == "What is Python?"
        mock_searcher.search_async.assert_called_once_with("What is Python?", top_k=5)
        mock_llm_provider.agenerate.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_async_with_show_sources(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async query with show_sources=True includes chunks."""
        mock_chunks = [
            {
                "chunk_text": "Test chunk",
                "source_file": "test.pdf",
                "page": 1,
            }
        ]
        mock_searcher.search_async.return_value = mock_chunks

        result = await pipeline_with_mocks.query_async("Test query", show_sources=True)

        assert "sources" in result
        assert result["sources"] == mock_chunks

    @pytest.mark.asyncio
    async def test_query_async_with_custom_top_k(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async query with custom top_k parameter."""
        mock_searcher.search_async.return_value = []

        await pipeline_with_mocks.query_async("Test query", top_k=10)

        mock_searcher.search_async.assert_called_once_with("Test query", top_k=10)

    @pytest.mark.asyncio
    async def test_query_async_with_no_results_and_show_sources(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async query with no results and show_sources=True."""
        mock_searcher.search_async.return_value = []

        result = await pipeline_with_mocks.query_async("Test query", show_sources=True)

        assert "sources" in result
        assert result["sources"] == []
        assert "couldn't find" in result["answer"].lower()

    @pytest.mark.asyncio
    async def test_query_async_handles_exception_gracefully(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async query handles exceptions and returns error response."""
        mock_searcher.search_async.side_effect = RuntimeError("Connection failed")

        result = await pipeline_with_mocks.query_async("Test query")

        assert "answer" in result
        assert (
            "error" in result["answer"].lower()
            or "apologize" in result["answer"].lower()
        )
        assert result["query"] == "Test query"

    @pytest.mark.asyncio
    async def test_chat_async_multi_turn_with_history(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test async multi-turn chat with conversation history."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "What is Python?")
        session.add_message("assistant", "Python is a language")

        mock_chunks = [
            {"chunk_text": "Python docs", "source_file": "docs.pdf", "page": 1}
        ]
        mock_searcher.search_async.return_value = mock_chunks
        mock_llm_provider.agenerate.return_value = "More Python info"

        result = await pipeline_with_rewriter.chat_async(
            "What about libraries?", session
        )

        assert result["answer"] == "More Python info"
        assert "rewritten_query" in result
        mock_rewriter.rewrite_query.assert_called_once()
        assert session.message_count == 4

    @pytest.mark.asyncio
    async def test_chat_async_without_rewriter(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test async chat without rewriter uses original query."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "Hello")

        mock_searcher.search_async.return_value = [
            {"chunk_text": "test", "source_file": "t.pdf", "page": 1}
        ]

        result = await pipeline_with_mocks.chat_async("How are you?", session)

        assert result["answer"] == "Async generated answer"
        assert result["rewritten_query"] == "How are you?"

    @pytest.mark.asyncio
    async def test_chat_async_with_show_sources(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async chat with show_sources=True."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_chunks = [{"chunk_text": "chunk", "source_file": "f.pdf", "page": 1}]
        mock_searcher.search_async.return_value = mock_chunks

        result = await pipeline_with_rewriter.chat_async(
            "Query", session, show_sources=True
        )

        assert "sources" in result
        assert result["sources"] == mock_chunks

    @pytest.mark.asyncio
    async def test_chat_async_with_no_results_and_show_sources(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async chat with no results and show_sources=True."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_searcher.search_async.return_value = []

        result = await pipeline_with_rewriter.chat_async(
            "Query", session, show_sources=True
        )

        assert (
            result["answer"]
            == "I couldn't find relevant documents for your query: Query"
        )
        assert "sources" in result
        assert result["sources"] == []

    @pytest.mark.asyncio
    async def test_chat_async_handles_exception_gracefully(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
    ) -> None:
        """Test async chat exception handling."""
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        mock_searcher.search_async.side_effect = RuntimeError("Search failed")

        result = await pipeline_with_rewriter.chat_async("Query", session)

        assert "answer" in result
        assert (
            "apologize" in result["answer"].lower()
            or "error" in result["answer"].lower()
        )


class TestRAGPipelineExtended:
    """Extended tests for RAGPipeline functionality."""

    def test_build_prompt_exact_structure(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_rewriter: MagicMock,
    ) -> None:
        """Test that prompt has exact expected structure.

        Verifies that the RAG prompt includes all required sections:
        - System instruction to use context only
        - Document context with source attribution
        - Conversation history (if available)
        - User's current query
        """
        # Setup mocks
        mock_chunks = [
            {
                "chunk_text": "Test content",
                "source_file": "test.pdf",
                "page": 1,
                "similarity": 0.9,
            }
        ]
        pipeline_with_mocks._searcher.search.return_value = mock_chunks
        pipeline_with_mocks._llm_provider.generate.return_value = "Answer"

        # Execute query
        result = pipeline_with_mocks.query("Test query")

        # Verify result contains answer
        assert "answer" in result

    def test_handle_no_retrieved_chunks_informs_llm(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
    ) -> None:
        """Test that no results still informs LLM appropriately.

        Verifies that when search returns no results, the pipeline
        still calls the LLM with appropriate context about missing results.
        """
        # Setup mock to return no results
        mock_searcher.search.return_value = []
        mock_llm_provider.generate.return_value = "I cannot answer from context"

        # Execute query
        result = pipeline_with_mocks.query("Test query")

        # Verify result contains answer (even if it's a fallback)
        assert "answer" in result
        # LLM should indicate it cannot answer
        assert "couldn't" in result["answer"].lower() or "not found" in result["answer"].lower()

    def test_handle_ambiguous_queries(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from secondbrain.config import Config
        from secondbrain.rag.pipeline import RAGPipeline

        mock_searcher = MagicMock()
        mock_searcher.search.return_value = []
        mock_searcher.search_async = AsyncMock(return_value=[])

        mock_llm_provider = MagicMock()
        mock_llm_provider.generate.return_value = "Could you clarify?"

        config = Config()
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
            context_window=5,
        )

        result = pipeline.query("What about it?")

        assert "answer" in result


class TestRAGPipelineCoverageGaps:
    """Tests specifically designed to cover missing coverage lines."""

    def test_query_with_empty_string_returns_validation_error(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that empty query returns validation error.

        Covers line 108: validation error return path.
        """
        result = pipeline_with_mocks.query("")

        assert result["answer"] == "Query cannot be empty. Please provide a valid question."
        assert result["query"] == ""
        assert result["validation_error"] is True

    def test_query_with_whitespace_only_returns_validation_error(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that whitespace-only query returns validation error.

        Covers line 108: validation error return path for whitespace.
        """
        result = pipeline_with_mocks.query("   \t\n  ")

        assert result["answer"] == "Query cannot be empty. Please provide a valid question."
        assert result["validation_error"] is True

    def test_query_with_security_violation_returns_safe_response(
        self,
        pipeline_with_mocks: RAGPipeline,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that security violation returns safe response.

        Covers lines 117-121: security filter violation logging and response.
        """
        from secondbrain.rag.security_filter import SecurityViolation

        # Mock security filter to return a violation
        mock_violation = SecurityViolation(
            violation_type="sql_injection",
            pattern_matched="DROP TABLE",
            severity="high",
        )

        # Patch validate_query to return violation
        monkeypatch.setattr(
            pipeline_with_mocks._security_filter,
            "validate_query",
            lambda q: [mock_violation],
        )

        # Patch get_safe_response
        monkeypatch.setattr(
            pipeline_with_mocks._security_filter,
            "get_safe_response",
            lambda: "I cannot process potentially malicious queries.",
        )

        result = pipeline_with_mocks.query("DROP TABLE users;")

        assert result["answer"] == "I cannot process potentially malicious queries."
        assert result["query"] == "DROP TABLE users;"
        assert result["security_blocked"] is True

    async def test_query_async_with_empty_query_returns_validation_error(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Test that async query with empty query returns validation error.

        Covers line 518: async validation error return path.
        """
        result = await pipeline_with_mocks.query_async("")

        assert result["answer"] == "Query cannot be empty. Please provide a valid question."
        assert result["validation_error"] is True


class TestRAGPipelineTracing:
    """Tests for RAGPipeline tracing span attributes."""

    def test_query_with_tracing_enabled_sets_span_attributes(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that query method sets tracing span attributes when tracing is enabled.

        Covers lines 134-138: retrieval span attributes (query, top_k, chunks_returned).
        Covers lines 163-165: generation span attributes (prompt_length, temperature, max_tokens).
        Covers line 172: generation span answer_length attribute.
        """
        from unittest.mock import MagicMock as MockSpan

        # Create a mock span with set_attribute tracking
        mock_span = MockSpan()
        mock_span.set_attribute = MagicMock()

        # Create a mock context manager that yields the mock span
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__ = MagicMock(return_value=mock_span)
        mock_context_manager.__exit__ = MagicMock(return_value=False)

        # Patch trace_operation to return our mock span
        monkeypatch.setattr(
            "secondbrain.rag.pipeline.trace_operation",
            lambda op: mock_context_manager,
        )

        # Enable tracing by setting the environment variable
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")

        # Setup mocks to return data
        mock_chunks = [
            {"chunk_text": "Test chunk 1", "source_file": "test.pdf", "score": 0.9},
        ]
        mock_searcher.search.return_value = mock_chunks
        mock_llm_provider.generate.return_value = "Test answer"

        # Execute query
        result = pipeline_with_mocks.query("Test query", top_k=5)

        # Verify retrieval span attributes were set
        retrieval_set_attribute_calls = [
            call
            for call in mock_span.set_attribute.call_args_list
            if call[0][0].startswith("rag.")
        ]

        # Check retrieval attributes (lines 134-138)
        assert any("rag.query" in str(call) for call in retrieval_set_attribute_calls)
        assert any("rag.top_k" in str(call) for call in retrieval_set_attribute_calls)
        assert any("rag.chunks_returned" in str(call) for call in retrieval_set_attribute_calls)

        # Check generation attributes (lines 163-165, 172)
        assert any("rag.prompt_length" in str(call) for call in retrieval_set_attribute_calls)
        assert any("rag.temperature" in str(call) for call in retrieval_set_attribute_calls)
        assert any("rag.max_tokens" in str(call) for call in retrieval_set_attribute_calls)
        assert any("rag.answer_length" in str(call) for call in retrieval_set_attribute_calls)

        assert result["answer"] == "Test answer"

    def test_chat_with_tracing_enabled_sets_span_attributes(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_rewriter: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that chat method sets tracing span attributes when tracing is enabled.

        Covers lines 227-232: retrieval span attributes (query, top_k, is_chat, chunks_returned).
        Covers lines 261-264: generation span attributes (prompt_length, temperature, max_tokens, is_chat).
        Covers line 271: generation span answer_length attribute.
        """
        from unittest.mock import MagicMock as MockSpan

        # Create a mock span with set_attribute tracking
        mock_span = MockSpan()
        mock_span.set_attribute = MagicMock()

        # Create a mock context manager that yields the mock span
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__ = MagicMock(return_value=mock_span)
        mock_context_manager.__exit__ = MagicMock(return_value=False)

        # Patch trace_operation to return our mock span
        monkeypatch.setattr(
            "secondbrain.rag.pipeline.trace_operation",
            lambda op: mock_context_manager,
        )

        # Enable tracing
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")

        # Setup mocks
        mock_chunks = [
            {"chunk_text": "Test chunk", "source_file": "test.pdf", "score": 0.9},
        ]
        mock_searcher.search.return_value = mock_chunks
        mock_llm_provider.generate.return_value = "Chat answer"
        mock_rewriter.should_rewrite.return_value = True
        mock_rewriter.rewrite_query.return_value = "rewritten query"

        # Create session with history
        session = ConversationSession("test-session", MagicMock(), context_window=10)
        session.add_message("user", "Previous query")
        session.add_message("assistant", "Previous answer")

        # Execute chat
        result = pipeline_with_rewriter.chat("Current query", session=session)

        # Verify span attributes were set
        span_calls = [
            call for call in mock_span.set_attribute.call_args_list if call[0][0].startswith("rag.")
        ]

        # Check retrieval attributes including is_chat (lines 227-232)
        assert any("rag.query" in str(call) for call in span_calls)
        assert any("rag.top_k" in str(call) for call in span_calls)
        assert any("rag.is_chat" in str(call) for call in span_calls)
        assert any("rag.chunks_returned" in str(call) for call in span_calls)

        # Check generation attributes including is_chat (lines 261-264, 271)
        assert any("rag.prompt_length" in str(call) for call in span_calls)
        assert any("rag.temperature" in str(call) for call in span_calls)
        assert any("rag.max_tokens" in str(call) for call in span_calls)
        assert any("rag.is_chat" in str(call) for call in span_calls)
        assert any("rag.answer_length" in str(call) for call in span_calls)

        assert result["answer"] == "Chat answer"
        assert "rewritten_query" in result

    async def test_query_async_with_tracing_enabled_sets_span_attributes(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that async query method sets tracing span attributes.

        Covers lines 531-534: async retrieval span attributes (query, top_k, is_chat, is_async).
        Covers line 539: async retrieval chunks_returned attribute.
        Covers lines 559-562: async generation span attributes (prompt_length, temperature, max_tokens, is_async).
        Covers line 569: async generation answer_length attribute.
        """
        from unittest.mock import MagicMock as MockSpan

        # Create a mock span
        mock_span = MockSpan()
        mock_span.set_attribute = MagicMock()

        # Create a mock context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__ = MagicMock(return_value=mock_span)
        mock_context_manager.__exit__ = MagicMock(return_value=False)

        # Patch trace_operation
        monkeypatch.setattr(
            "secondbrain.rag.pipeline.trace_operation",
            lambda op: mock_context_manager,
        )

        # Enable tracing
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")

        # Setup async mocks
        mock_chunks = [
            {"chunk_text": "Async chunk", "source_file": "test.pdf", "score": 0.9},
        ]
        mock_searcher.search_async = AsyncMock(return_value=mock_chunks)
        mock_llm_provider.agenerate = AsyncMock(return_value="Async answer")

        # Execute async query
        result = await pipeline_with_mocks.query_async("Async test query", top_k=5)

        # Verify span attributes
        span_calls = [
            call for call in mock_span.set_attribute.call_args_list if call[0][0].startswith("rag.")
        ]

        # Check async retrieval attributes (lines 531-534, 539)
        assert any("rag.query" in str(call) for call in span_calls)
        assert any("rag.top_k" in str(call) for call in span_calls)
        assert any("rag.is_chat" in str(call) for call in span_calls)
        assert any("rag.is_async" in str(call) for call in span_calls)
        assert any("rag.chunks_returned" in str(call) for call in span_calls)

        # Check async generation attributes (lines 559-562, 569)
        assert any("rag.prompt_length" in str(call) for call in span_calls)
        assert any("rag.temperature" in str(call) for call in span_calls)
        assert any("rag.max_tokens" in str(call) for call in span_calls)
        assert any("rag.is_async" in str(call) for call in span_calls)
        assert any("rag.answer_length" in str(call) for call in span_calls)

        assert result["answer"] == "Async answer"

    async def test_chat_async_with_tracing_enabled_sets_span_attributes(
        self,
        pipeline_with_rewriter: RAGPipeline,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_rewriter: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test that async chat method sets tracing span attributes.

        Covers lines 612-615: async chat retrieval span attributes (query, top_k, is_chat, is_async).
        Covers line 620: async chat retrieval chunks_returned attribute.
        Covers lines 644-648: async chat generation span attributes (prompt_length, temperature, max_tokens, is_chat, is_async).
        Covers line 655: async chat generation answer_length attribute.
        """
        from unittest.mock import MagicMock as MockSpan

        # Create a mock span
        mock_span = MockSpan()
        mock_span.set_attribute = MagicMock()

        # Create a mock context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__ = MagicMock(return_value=mock_span)
        mock_context_manager.__exit__ = MagicMock(return_value=False)

        # Patch trace_operation
        monkeypatch.setattr(
            "secondbrain.rag.pipeline.trace_operation",
            lambda op: mock_context_manager,
        )

        # Enable tracing
        monkeypatch.setenv("SECONDBRAIN_TRACING_ENABLED", "true")

        # Setup mocks
        mock_chunks = [
            {"chunk_text": "Async chat chunk", "source_file": "test.pdf", "score": 0.9},
        ]
        mock_searcher.search_async = AsyncMock(return_value=mock_chunks)
        mock_llm_provider.agenerate = AsyncMock(return_value="Async chat answer")
        mock_rewriter.should_rewrite.return_value = True
        mock_rewriter.rewrite_query.return_value = "rewritten async query"

        # Create session
        session = ConversationSession("async-test-session", MagicMock(), context_window=10)
        session.add_message("user", "Previous")
        session.add_message("assistant", "Previous answer")

        # Execute async chat
        result = await pipeline_with_rewriter.chat_async(
            "Async chat query", session=session, top_k=5
        )

        # Verify span attributes
        span_calls = [
            call for call in mock_span.set_attribute.call_args_list if call[0][0].startswith("rag.")
        ]

        # Check async chat retrieval attributes (lines 612-615, 620)
        assert any("rag.query" in str(call) for call in span_calls)
        assert any("rag.top_k" in str(call) for call in span_calls)
        assert any("rag.is_chat" in str(call) for call in span_calls)
        assert any("rag.is_async" in str(call) for call in span_calls)
        assert any("rag.chunks_returned" in str(call) for call in span_calls)

        # Check async chat generation attributes (lines 644-648, 655)
        assert any("rag.prompt_length" in str(call) for call in span_calls)
        assert any("rag.temperature" in str(call) for call in span_calls)
        assert any("rag.max_tokens" in str(call) for call in span_calls)
        assert any("rag.is_chat" in str(call) for call in span_calls)
        assert any("rag.is_async" in str(call) for call in span_calls)
        assert any("rag.answer_length" in str(call) for call in span_calls)

        assert result["answer"] == "Async chat answer"
        assert "rewritten_query" in result
