"""Unit tests for QueryRewriter module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from secondbrain.conversation.rewriter import QueryRewriter


@pytest.fixture
def mock_llm_provider():
    """Mock OllamaLLMProvider for QueryRewriter tests."""
    mock = MagicMock()
    mock.generate.return_value = "What about the ACME contract pricing?"
    return mock


@pytest.fixture
def rewriter(mock_llm_provider):
    """Create QueryRewriter with mocked LLM provider."""
    return QueryRewriter(mock_llm_provider, context_window=5)


class TestQueryRewriterInit:
    """Tests for QueryRewriter initialization."""

    def test_init_with_defaults(self, mock_llm_provider):
        """Test initialization with default context window."""
        rewriter = QueryRewriter(mock_llm_provider)

        assert rewriter.context_window == 5

    def test_init_with_custom_context_window(self, mock_llm_provider):
        """Test initialization with custom context window."""
        rewriter = QueryRewriter(mock_llm_provider, context_window=10)

        assert rewriter.context_window == 10


class TestQueryRewriterShouldRewrite:
    """Tests for QueryRewriter.should_rewrite method."""

    def test_should_rewrite_pronoun_it(self, rewriter):
        """Test that 'it' triggers rewriting."""
        assert rewriter.should_rewrite("How does it work?") is True

    def test_should_rewrite_pronoun_this(self, rewriter):
        """Test that 'this' triggers rewriting."""
        assert rewriter.should_rewrite("What about this?") is True

    def test_should_rewrite_pronoun_that(self, rewriter):
        """Test that 'that' triggers rewriting."""
        assert rewriter.should_rewrite("Tell me about that.") is True

    def test_should_rewrite_pronoun_they(self, rewriter):
        """Test that 'they' triggers rewriting."""
        assert rewriter.should_rewrite("What did they say?") is True

    def test_should_rewrite_ambiguous_contract(self, rewriter):
        """Test that 'the contract' triggers rewriting."""
        assert rewriter.should_rewrite("What about the contract?") is True

    def test_should_rewrite_standalone_query(self, rewriter):
        """Test that standalone queries don't trigger rewriting."""
        assert rewriter.should_rewrite("What is Python?") is False

    def test_should_rewrite_no_pronouns(self, rewriter):
        """Test that queries without pronouns don't trigger rewriting."""
        assert rewriter.should_rewrite("How much is the subscription?") is False


class TestQueryRewriterRewrite:
    """Tests for QueryRewriter.rewrite method."""

    def test_rewrite_with_history(self, rewriter, mock_llm_provider):
        """Test rewriting query with conversation history."""
        history = [
            {"role": "user", "content": "Tell me about ACME contract"},
            {"role": "assistant", "content": "The ACME contract is..."},
        ]

        result = rewriter.rewrite("What about pricing?", history)

        assert result == "What about the ACME contract pricing?"
        mock_llm_provider.generate.assert_called_once()

    def test_rewrite_empty_history(self, rewriter, mock_llm_provider):
        """Test that empty history returns original query."""
        history = []

        result = rewriter.rewrite("What about pricing?", history)

        assert result == "What about pricing?"
        mock_llm_provider.generate.assert_not_called()

    def test_rewrite_no_history(self, rewriter, mock_llm_provider):
        """Test that None history returns original query."""
        result = rewriter.rewrite("What about pricing?", None)

        assert result == "What about pricing?"
        mock_llm_provider.generate.assert_not_called()

    def test_rewrite_fallback_on_error(self, rewriter, mock_llm_provider):
        """Test fallback to original query on LLM error."""
        mock_llm_provider.generate.side_effect = Exception("LLM failed")
        history = [{"role": "user", "content": "Test"}]

        result = rewriter.rewrite("What about it?", history)

        assert result == "What about it?"

    def test_rewrite_limits_context_window(self, rewriter, mock_llm_provider):
        """Test that only context_window messages are used."""
        history = [{"role": "user", "content": f"Message {i}"} for i in range(10)]

        rewriter.rewrite("What about it?", history)

        # Check that generate was called (implies history was processed)
        mock_llm_provider.generate.assert_called_once()


class TestQueryRewriterFormatHistory:
    """Tests for QueryRewriter._format_history method."""

    def test_format_history_single_message(self, rewriter):
        """Test formatting single message."""
        history = [{"role": "user", "content": "Hello"}]

        result = rewriter._format_history(history)

        assert result == "User: Hello"

    def test_format_history_multiple_messages(self, rewriter):
        """Test formatting multiple messages."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        result = rewriter._format_history(history)

        assert "User: Hello" in result
        assert "Assistant: Hi!" in result

    def test_format_history_empty(self, rewriter):
        """Test formatting empty history."""
        history = []

        result = rewriter._format_history(history)

        assert result == ""


class TestQueryRewriterCleanResponse:
    """Tests for QueryRewriter._clean_llm_response method."""

    def test_clean_response_strips_whitespace(self, rewriter):
        """Test that whitespace is stripped."""
        response = "  \n\n  What about pricing?  \n\n  "

        result = rewriter._clean_llm_response(response)

        assert result == "What about pricing?"

    def test_clean_response_removes_prefix(self, rewriter):
        """Test that common prefixes are removed."""
        response = "Here is the rewritten question: What about pricing?"

        result = rewriter._clean_llm_response(response)

        assert result == "What about pricing?"

    def test_clean_response_removes_multiple_newlines(self, rewriter):
        """Test that multiple newlines are reduced."""
        response = "What\n\n\nabout\n\n\npricing?"

        result = rewriter._clean_llm_response(response)

        assert "\n\n\n" not in result


class TestQueryRewriterIsValidRewrite:
    """Tests for QueryRewriter._is_valid_rewrite method."""

    def test_is_valid_good_rewrite(self, rewriter):
        """Test that good rewrites are valid."""
        assert rewriter._is_valid_rewrite("What?", "What is machine learning?") is True

    def test_is_valid_empty_rewrite(self, rewriter):
        """Test that empty rewrites are invalid."""
        assert rewriter._is_valid_rewrite("Hello", "") is False

    def test_is_valid_whitespace_only(self, rewriter):
        """Test that whitespace-only rewrites are invalid."""
        assert rewriter._is_valid_rewrite("Hello", "   ") is False

    def test_is_valid_too_short(self, rewriter):
        """Test that very short rewrites are invalid."""
        assert rewriter._is_valid_rewrite("Hello", "Hi") is False

    def test_is_valid_same_as_original(self, rewriter):
        """Test that same-as-original rewrites are valid."""
        assert rewriter._is_valid_rewrite("Hello", "Hello") is True

    def test_is_valid_failure_pattern(self, rewriter):
        """Test that failure patterns make rewrite invalid."""
        assert rewriter._is_valid_rewrite("Hello", "I cannot answer") is False


class TestQueryRewriterIsStandaloneQuery:
    """Tests for QueryRewriter._is_standalone_query method."""

    def test_is_standalone_no_pronouns(self, rewriter):
        """Test that queries without pronouns are standalone."""
        assert rewriter._is_standalone_query("What is Python?") is True

    def test_is_standalone_with_it(self, rewriter):
        """Test that 'it' makes query non-standalone."""
        assert rewriter._is_standalone_query("How does it work?") is False

    def test_is_standalone_with_this(self, rewriter):
        """Test that 'this' makes query non-standalone."""
        assert rewriter._is_standalone_query("What about this?") is False

    def test_is_standalone_with_contract(self, rewriter):
        """Test that 'the contract' makes query non-standalone."""
        assert rewriter._is_standalone_query("What about the contract?") is False
