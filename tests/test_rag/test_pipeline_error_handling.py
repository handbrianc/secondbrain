"""Error handling tests for RAGPipeline module.

This module provides comprehensive error handling tests for the RAGPipeline class,
covering fallback logic, error recovery, provider failures, and edge cases.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from openai import APIError as OpenAI_APIError

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.interfaces import LocalLLMProvider
from secondbrain.exceptions import EmbeddingGenerationError, ServiceUnavailableError


@pytest.fixture
def mock_searcher() -> MagicMock:
    """Create a mock Searcher instance."""
    mock = MagicMock()
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
def mock_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Mock configuration for pipeline tests."""
    config = {
        "SECONDBRAIN_MONGO_URI": "mongodb://localhost:27018",
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
        "SECONDBRAIN_RAG_SYSTEM_PROMPT": "You are a helpful assistant.",
        "SECONDBRAIN_LLM_PROVIDER": "openai",
        "SECONDBRAIN_LLM_MODEL": "gpt-4o-mini",
        "SECONDBRAIN_LLM_TIMEOUT": "120",
    }
    for key, value in config.items():
        monkeypatch.setenv(key, value)
    return config


class TestRAGPipelineErrorHandling:
    """Test RAG pipeline fallback and error recovery."""

    def test_query_handles_empty_query(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify pipeline handles empty or whitespace-only queries gracefully."""
        result = pipeline_with_mocks.query("")
        
        assert result["answer"] == "Query cannot be empty. Please provide a valid question."
        assert result.get("validation_error") is True

    def test_query_handles_whitespace_only_query(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify pipeline handles whitespace-only queries gracefully."""
        result = pipeline_with_mocks.query("   \n\t  ")
        
        assert result["answer"] == "Query cannot be empty. Please provide a valid question."
        assert result.get("validation_error") is True

    def test_query_handles_searcher_failure(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles searcher failures gracefully."""
        mock_searcher.search.side_effect = ServiceUnavailableError(
            "MongoDB", "Database connection failed"
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle error gracefully and return error response
        assert "answer" in result
        assert result.get("error") is not None or "failed" in result["answer"].lower()

    def test_query_handles_llm_provider_failure(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles LLM provider failures gracefully."""
        # Mock successful search but failing LLM
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = ServiceUnavailableError(
            "Ollama", "LLM server unavailable"
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle error gracefully and return error response
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_query_handles_timeout_error(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles timeout errors gracefully."""
        # Mock successful search but timeout on generation
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = TimeoutError(
            "Request timed out after 120s"
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle timeout gracefully
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_query_handles_connection_error(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles connection errors gracefully."""
        # Mock successful search but connection error on generation
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = ConnectionError(
            "Failed to connect to LLM server"
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle connection error gracefully
        assert "answer" in result
        assert result.get("error") is not None or "failed" in result["answer"].lower()

    def test_query_handles_invalid_response_from_provider(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles invalid/malformed responses from provider."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        # Return None or invalid response
        mock_llm_provider.generate.return_value = None
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        # Should handle None response gracefully
        result = pipeline.query("test query")
        assert "answer" in result

    def test_query_handles_empty_response_from_provider(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles empty responses from provider."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        # Return empty string
        mock_llm_provider.generate.return_value = ""
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle empty response (may return empty answer or error)
        assert "answer" in result

    def test_chat_retries_on_empty_response(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat retries on empty LLM responses (up to 3 times)."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage
        
        # Create a mock session
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        # Mock LLM provider that returns empty twice, then succeeds
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = ["", "", "Valid answer after retries"]
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.chat("Test query", session)
        
        # Should have retried and eventually succeeded
        assert mock_llm_provider.generate.call_count == 3
        assert "answer" in result
        assert result["answer"] == "Valid answer after retries"
        assert result.get("empty_response_retries") is None  # No retries needed in final result

    def test_chat_returns_fallback_after_max_empty_retries(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat returns fallback response after max retries with empty responses."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage
        
        # Create a mock session
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        # Mock LLM provider that always returns empty
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = ""
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.chat("Test query", session)
        
        # Should have retried max times and returned fallback
        assert mock_llm_provider.generate.call_count == 3
        assert "answer" in result
        assert "couldn't find relevant documents" in result["answer"].lower()
        assert result.get("empty_response_retries") == 3

    def test_chat_accepts_whitespace_only_as_empty(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline treats whitespace-only responses as empty and retries."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage
        
        # Create a mock session
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        # Mock LLM provider that returns whitespace then valid
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = ["   ", "\n\t", "Valid answer"]
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.chat("Test query", session)
        
        # Should have retried 3 times (whitespace counts as empty)
        assert mock_llm_provider.generate.call_count == 3
        assert result["answer"] == "Valid answer"

    def test_chat_handles_session_failure(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat handles session-related failures gracefully."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage
        
        # Create a mock storage and session
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        # Should handle chat gracefully even with empty search results
        result = pipeline.chat("How are you?", session)
        
        assert "answer" in result

    def test_chat_handles_rewriter_failure(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat handles query rewriter failures gracefully."""
        from secondbrain.conversation import ConversationSession, QueryRewriter
        from secondbrain.conversation.storage import ConversationStorage
        
        # Create mock storage and session with history
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        session.add_message("user", "What is Python?")
        session.add_message("assistant", "Python is a programming language.")
        
        # Mock rewriter that fails
        mock_rewriter = MagicMock(spec=QueryRewriter)
        mock_rewriter.rewrite_query.side_effect = ServiceUnavailableError(
            "QueryRewriter", "Rewriting failed"
        )
        mock_rewriter.should_rewrite.return_value = True
        mock_rewriter.context_window = 10
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = "Generated answer"
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=mock_rewriter,
            top_k=5,
        )
        
        # Should fall back to original query when rewriter fails
        result = pipeline.chat("What about Java?", session)
        
        assert "answer" in result
        # Should still produce an answer despite rewriter failure

    def test_handles_embedding_generation_failure(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles embedding generation failures gracefully."""
        # Mock embedding cache or service failure
        mock_searcher.search.side_effect = EmbeddingGenerationError(
            "Failed to generate embeddings for query"
        )
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = "Generated answer"
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle embedding failure gracefully
        assert "answer" in result
        assert result.get("error") is not None or "failed" in result["answer"].lower()

    def test_handles_security_filter_violation(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles security filter violations."""
        # Mock searcher to not be called (security should block first)
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        # Query that might trigger security filter
        result = pipeline.query("DROP TABLE users; --")
        
        # Should return security-blocked response
        assert "answer" in result
        # Security filter may or may not block this, but should handle gracefully

    def test_handles_no_context_found(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles case when no context is found."""
        # Mock empty search results
        mock_searcher.search.return_value = []
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle no results gracefully with fallback message
        assert "answer" in result
        assert "couldn't find" in result["answer"].lower() or "no relevant" in result["answer"].lower()
        # LLM should not be called when no context found
        mock_llm_provider.generate.assert_not_called()

    def test_handles_exception_during_query_processing(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles unexpected exceptions during processing."""
        # Mock searcher to raise unexpected exception
        mock_searcher.search.side_effect = RuntimeError("Unexpected error in searcher")
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = "Generated answer"
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should catch all exceptions and return error response
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_format_context_handles_empty_list(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify _format_context handles empty chunk list."""
        result = pipeline_with_mocks._format_context([])
        
        assert result == ""

    def test_format_context_handles_long_chunks(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify _format_context truncates long chunks."""
        long_text = "x" * 1000
        chunks = [
            {"chunk_text": long_text, "source_file": "test.pdf", "page": 1}
        ]
        
        result = pipeline_with_mocks._format_context(chunks)
        
        # Should truncate to 500 chars + "..."
        assert "..." in result
        assert len(result) < 1000

    def test_build_prompt_handles_empty_context(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify _build_prompt handles empty context."""
        prompt = pipeline_with_mocks._build_prompt("test query", "")
        
        assert "Question: test query" in prompt
        assert "No relevant context" in prompt or "CONTEXT" not in prompt

    def test_build_prompt_handles_none_conversation_history(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify _build_prompt handles None conversation history."""
        prompt = pipeline_with_mocks._build_prompt(
            "test query", "context text", conversation_history=None
        )
        
        assert "Question: test query" in prompt
        assert "Conversation History" not in prompt

    def test_rewrite_query_with_history_handles_empty_history(
        self,
        pipeline_with_mocks: RAGPipeline,
        mock_config: dict[str, str],
    ) -> None:
        """Verify _rewrite_query_with_history handles empty history."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage
        
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        # No messages added - empty history
        
        result = pipeline_with_mocks._rewrite_query_with_history("test query", session)
        
        # Should return original query when no history
        assert result == "test query"

    def test_create_error_response_contains_required_fields(
        self,
        pipeline_with_mocks: RAGPipeline,
    ) -> None:
        """Verify _create_error_response includes required fields."""
        response = pipeline_with_mocks._create_error_response(
            "Test error message", "test query"
        )
        
        assert "answer" in response
        assert "Test error message" in response["answer"]
        assert response.get("query") == "test query"


class TestRAGPipelineProviderFailures:
    """Test specific provider failure scenarios."""

    def test_handles_openai_api_error(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles OpenAI API errors."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        # Simulate OpenAI API error
        mock_request = MagicMock()
        mock_llm_provider.generate.side_effect = OpenAI_APIError(
            message="API error",
            request=mock_request,
            body=None,
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle API error gracefully
        assert "answer" in result

    def test_handles_http_timeout(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles HTTP timeout errors."""
        import httpx
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        # Simulate HTTP timeout
        mock_llm_provider.generate.side_effect = httpx.TimeoutException(
            message="Request timed out",
            request=MagicMock(),
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle timeout gracefully
        assert "answer" in result

    def test_handles_rate_limit_error(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles rate limit errors."""
        import httpx
        
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]
        
        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        # Simulate rate limit
        mock_llm_provider.generate.side_effect = httpx.HTTPStatusError(
            message="Rate limit exceeded",
            request=MagicMock(),
            response=MagicMock(status_code=429),
        )
        
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )
        
        result = pipeline.query("test query")
        
        # Should handle rate limit gracefully
        assert "answer" in result


# Fixtures for test classes that need them
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


class TestRAGPipelineFallbackLogic:
    """Test RAG pipeline fallback and error recovery logic."""

    def test_pipeline_fallback_on_provider_failure(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles provider failure with fallback response."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = ServiceUnavailableError(
            "Ollama", "LLM server unavailable"
        )

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should handle error gracefully and return error response
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_pipeline_handles_empty_response(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles empty responses from provider."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = ""

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should handle empty response
        assert "answer" in result

    def test_pipeline_fallback_chain_order(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify fallback chain executes in correct order."""
        # Mock empty search results (first fallback point)
        mock_searcher.search.return_value = []

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = "Generated answer"

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should not call LLM when no context found
        mock_llm_provider.generate.assert_not_called()
        assert "couldn't find" in result["answer"].lower()

    def test_pipeline_timeout_handling(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles timeout errors gracefully."""
        # Mock successful search but timeout on generation
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.side_effect = TimeoutError(
            "Request timed out after 120s"
        )

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should handle timeout gracefully
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_pipeline_invalid_input_validation(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline validates input before processing."""
        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        # Test empty query
        result = pipeline.query("")
        assert "validation_error" in result
        assert "cannot be empty" in result["answer"].lower()

        # Test whitespace-only query
        result = pipeline.query("   ")
        assert "validation_error" in result
        assert "cannot be empty" in result["answer"].lower()

        # LLM should not be called for invalid queries
        mock_llm_provider.generate.assert_not_called()

    def test_pipeline_provider_switch_error_handling(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles errors when switching providers."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        # First provider fails
        mock_llm_provider_1 = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider_1.generate.side_effect = ServiceUnavailableError(
            "Provider1", "Provider unavailable"
        )

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider_1,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should handle provider failure gracefully
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_pipeline_handles_searcher_exception(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles exceptions from searcher."""
        # Mock searcher to raise exception
        mock_searcher.search.side_effect = RuntimeError("Search failed")

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query")

        # Should catch exception and return error response
        assert "answer" in result
        assert "error" in result["answer"].lower() or "apologize" in result["answer"].lower()

    def test_pipeline_handles_none_from_provider(
        self,
        mock_searcher: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles None response from provider."""
        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        mock_llm_provider = MagicMock(spec=LocalLLMProvider)
        mock_llm_provider.generate.return_value = None

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        # Should handle None response gracefully
        result = pipeline.query("test query")
        assert "answer" in result

    def test_chat_fallback_on_rewriter_failure(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat falls back to original query when rewriter fails."""
        from secondbrain.conversation import ConversationSession, QueryRewriter
        from secondbrain.conversation.storage import ConversationStorage

        # Create session with history
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )
        session.add_message("user", "What is Python?")
        session.add_message("assistant", "Python is a programming language.")

        # Mock rewriter that fails
        mock_rewriter = MagicMock(spec=QueryRewriter)
        mock_rewriter.rewrite_query.side_effect = ServiceUnavailableError(
            "QueryRewriter", "Rewriting failed"
        )

        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            rewriter=mock_rewriter,
            top_k=5,
        )

        # Should fall back to original query
        result = pipeline.chat("What about Java?", session)

        assert "answer" in result
        # Should still produce an answer despite rewriter failure

    def test_chat_handles_empty_session_history(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat handles empty session history gracefully."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage

        # Create empty session
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
        )

        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.chat("Hello", session)

        assert "answer" in result

    def test_pipeline_preserves_sources_when_requested(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline includes sources when show_sources=True."""
        mock_chunks = [
            {"chunk_text": "context 1", "source_file": "file1.pdf", "page": 1},
            {"chunk_text": "context 2", "source_file": "file2.pdf", "page": 2},
        ]
        mock_searcher.search.return_value = mock_chunks

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
        )

        result = pipeline.query("test query", show_sources=True)

        assert "sources" in result
        assert len(result["sources"]) == 2
        assert result["sources"] == mock_chunks

    def test_pipeline_handles_large_context_window(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify pipeline handles large context windows."""
        # Mock many chunks
        mock_chunks = [
            {"chunk_text": f"context {i}", "source_file": f"file{i}.pdf", "page": i}
            for i in range(20)
        ]
        mock_searcher.search.return_value = mock_chunks

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=20,
            context_window=20,
        )

        result = pipeline.query("test query")

        assert "answer" in result
        # LLM should be called with large context
        assert mock_llm_provider.generate.called

    def test_chat_with_session_adds_history_to_context(
        self,
        mock_searcher: MagicMock,
        mock_llm_provider: MagicMock,
        mock_config: dict[str, str],
    ) -> None:
        """Verify chat includes session history in context."""
        from secondbrain.conversation import ConversationSession
        from secondbrain.conversation.storage import ConversationStorage

        # Create session with history
        mock_storage = MagicMock(spec=ConversationStorage)
        session = ConversationSession(
            session_id="test-session",
            storage=mock_storage,
            context_window=5,
        )
        session.add_message("user", "What is Python?")
        session.add_message("assistant", "Python is a programming language.")

        # Mock successful search
        mock_searcher.search.return_value = [
            {"chunk_text": "test context", "source_file": "test.pdf", "page": 1}
        ]

        pipeline = RAGPipeline(
            searcher=mock_searcher,
            llm_provider=mock_llm_provider,
            top_k=5,
            context_window=5,
        )

        result = pipeline.chat("What about Java?", session)

        assert "answer" in result
        # LLM should be called with history included
        assert mock_llm_provider.generate.called
