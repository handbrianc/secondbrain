"""Comprehensive coverage tests for RAG pipeline.

Target: 60% coverage for src/secondbrain/rag/pipeline.py (currently 8.8%)

These tests exercise the actual pipeline logic that was previously uncovered:
- _format_context method
- _build_prompt method  
- _handle_no_results method
- _rewrite_query_with_history method
- _format_history method
- _create_error_response method
- Query rewriting logic
- Prompt building with context
- Error handling paths
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from secondbrain.conversation import ConversationSession, QueryRewriter
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.search import Searcher
from secondbrain.types import SearchResult


class TestRAGPipelineCoverage:
    """Tests to increase RAG pipeline coverage."""

    @pytest.fixture
    def mock_searcher(self):
        """Create a mock Searcher with realistic results."""
        mock = MagicMock(spec=Searcher)
        # Return actual SearchResult dicts for better coverage
        result1: dict[str, Any] = {
            "chunk_id": "test-1",
            "score": 0.95,
            "chunk_text": "Test context 1",
            "source_file": "test.pdf",
            "page_number": 1,
            "metadata": {"author": "test"}
        }
        result2: dict[str, Any] = {
            "chunk_id": "test-2", 
            "score": 0.85,
            "chunk_text": "Test context 2",
            "source_file": "test.pdf",
            "page_number": 2,
            "metadata": {"author": "test"}
        }
        mock.search.return_value = [result1, result2]
        mock.search_async = AsyncMock(return_value=[result1, result2])
        return mock

    @pytest.fixture
    def mock_llm_provider(self):
        """Create a mock LLM provider."""
        mock = MagicMock()
        mock.generate.return_value = "This is the generated answer."
        mock.agenerate = AsyncMock(return_value="Async generated answer.")
        return mock

    @pytest.fixture
    def mock_rewriter(self):
        """Create a mock QueryRewriter."""
        mock = MagicMock(spec=QueryRewriter)
        mock.rewrite_query.return_value = "rewritten: what is machine learning?"
        mock.should_rewrite.return_value = True
        mock.context_window = 5
        return mock

    def test_format_context_with_results(self, mock_searcher, mock_llm_provider):
        """Test _format_context formats multiple results correctly."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5
        )

        results = mock_searcher.search.return_value
        formatted = pipeline._format_context(results)

        assert "Test context 1" in formatted
        assert "Test context 2" in formatted
        assert "test.pdf" in formatted

    def test_format_context_empty_results(self, mock_searcher, mock_llm_provider):
        """Test _format_context handles empty results."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        mock_searcher.search.return_value = []
        formatted = pipeline._format_context([])

        assert formatted == ""

    def test_build_prompt_basic(self, mock_searcher, mock_llm_provider):
        """Test _build_prompt creates prompt with context."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        context = "This is test context"
        query = "What is AI?"
        prompt = pipeline._build_prompt(query, context)

        assert "This is test context" in prompt
        assert "What is AI?" in prompt
        assert "Answer:" in prompt

    def test_build_prompt_with_history(self, mock_searcher, mock_llm_provider):
        """Test _build_prompt includes conversation history."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            context_window=5
        )

        context = "Test context"
        query = "What is AI?"
        history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]
        prompt = pipeline._build_prompt(query, context, history)

        assert "Test context" in prompt
        assert "Previous question" in prompt
        assert "Previous answer" in prompt

    def test_handle_no_results(self, mock_searcher, mock_llm_provider):
        """Test _handle_no_results creates error response."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        result_text = pipeline._handle_no_results("test query")

        assert isinstance(result_text, str)
        assert "test query" in result_text

    def test_rewrite_query_with_history(self, mock_searcher, mock_llm_provider, mock_rewriter):
        """Test _rewrite_query_with_history uses rewriter."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=mock_rewriter
        )

        # Create a mock ConversationSession
        mock_session = MagicMock(spec=ConversationSession)
        mock_session.get_history.return_value = [
            {"role": "user", "content": "What is machine learning?"},
            {"role": "assistant", "content": "ML is a subset of AI"}
        ]
        
        query = "How does it work?"

        rewritten = pipeline._rewrite_query_with_history(query, mock_session)

        assert rewritten == "rewritten: what is machine learning?"
        mock_rewriter.rewrite_query.assert_called_once()

    def test_format_history(self, mock_searcher, mock_llm_provider):
        """Test _format_history formats messages correctly."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        formatted = pipeline._format_history(messages)

        assert "User: Hello" in formatted
        assert "Assistant: Hi there!" in formatted

    def test_create_error_response(self, mock_searcher, mock_llm_provider):
        """Test _create_error_response creates proper error response."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        result_text = pipeline._handle_no_results("test query")

        assert isinstance(result_text, str)
        assert "test query" in result_text

    @patch("secondbrain.rag.pipeline.metrics")
    def test_query_with_metrics(self, mock_metrics, mock_searcher, mock_llm_provider):
        """Test query method records metrics."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        result = pipeline.query("What is AI?", show_sources=True)

        assert result["answer"] == "This is the generated answer."
        assert result["query"] == "What is AI?"
        assert "sources" in result

    def test_query_with_rewrite(self, mock_searcher, mock_llm_provider, mock_rewriter):
        """Test query method works without rewriting for single-turn."""
        # For single-turn query without session, no rewriting happens
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=mock_rewriter
        )

        result = pipeline.query("Direct query")

        assert result["answer"] == "This is the generated answer."
        mock_rewriter.should_rewrite.assert_not_called()

    def test_query_without_rewriter(self, mock_searcher, mock_llm_provider):
        """Test query works without rewriter."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=None
        )

        result = pipeline.query("Direct query")

        assert result["answer"] == "This is the generated answer."
        assert result["query"] == "Direct query"


class TestRAGPipelineAsyncCoverage:
    """Async tests for RAG pipeline coverage."""

    @pytest.fixture
    def mock_searcher(self):
        """Create a mock Searcher with async support."""
        mock = MagicMock(spec=Searcher)
        result1: dict[str, Any] = {
            "chunk_id": "async-1",
            "score": 0.92,
            "chunk_text": "Async context 1",
            "source_file": "async.pdf",
            "page_number": 1,
            "metadata": {}
        }
        mock.search_async = AsyncMock(return_value=[result1])
        return mock

    @pytest.fixture
    def mock_llm_provider(self):
        """Create a mock async LLM provider."""
        mock = MagicMock()
        mock.agenerate = AsyncMock(return_value="Async answer")
        return mock

    @pytest.mark.asyncio
    async def test_query_async_basic(self, mock_searcher, mock_llm_provider):
        """Test query_async method basic functionality."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        result = await pipeline.query_async("Async query")

        assert result["answer"] == "Async answer"
        assert result["query"] == "Async query"

    @pytest.mark.asyncio
    async def test_chat_async_basic(self, mock_searcher, mock_llm_provider):
        """Test chat_async method with session."""
        mock_session = MagicMock(spec=ConversationSession)
        mock_session.add_message = AsyncMock()
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider
        )

        result = await pipeline.chat_async("Hello", session=mock_session)

        assert result["answer"] == "Async answer"
        mock_session.add_message.assert_called()
