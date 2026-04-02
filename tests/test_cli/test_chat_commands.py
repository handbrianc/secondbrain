"""Comprehensive tests for CLI chat commands.

This module tests the chat command functionality including:
- Single-turn chat mode
- Interactive REPL mode with special commands
- Error handling and recovery
- Session management (list, delete)
- LLM health checking
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli
from secondbrain.exceptions import ServiceUnavailableError


class TestChatCommands:
    """Tests for chat CLI commands."""

    def test_single_turn_chat(self) -> None:
        """Test non-interactive chat with a single query.

        Verifies that:
        - Chat command executes with a query argument
        - RAG pipeline is invoked with correct parameters
        - Response is displayed in expected format
        - Session is created/loaded properly
        """
        with (
            patch("secondbrain.rag.RAGPipeline") as mock_pipeline_class,
            patch("secondbrain.conversation.ConversationSession") as mock_session_class,
            patch("secondbrain.config.get_config") as mock_get_config,
        ):
            # Mock config
            mock_config = MagicMock()
            mock_config.llm_model = "llama3.2"
            mock_config.ollama_host = "http://localhost:11435"
            mock_config.rag_context_window = 10
            mock_get_config.return_value = mock_config

            # Mock session
            mock_session = MagicMock()
            mock_session.is_empty = True
            mock_session_class.load.return_value = None
            mock_session_class.create.return_value = mock_session

            # Mock RAG pipeline
            mock_pipeline = MagicMock()
            mock_pipeline.chat.return_value = {
                "answer": "This is a test answer from the RAG pipeline.",
                "rewritten_query": "test query",
            }
            mock_pipeline_class.return_value = mock_pipeline

            runner = CliRunner()
            result = runner.invoke(
                cli, ["chat", "What is secondbrain?", "--session", "test-session"]
            )

            # Verify exit code and output
            assert result.exit_code == 0
            assert "Answer:" in result.output
            assert "This is a test answer" in result.output

            # Verify session loading/creation
            mock_session_class.load.assert_called_once()
            call_args = mock_session_class.load.call_args
            assert call_args[0][0] == "test-session"
            mock_session_class.create.assert_called_once()

            # Verify RAG pipeline chat was called
            mock_pipeline.chat.assert_called_once()
            call_args = mock_pipeline.chat.call_args
            assert call_args[0][0] == "What is secondbrain?"  # query
            assert call_args[0][1] == mock_session  # session object

    def test_interactive_chat_commands(self) -> None:
        """Test interactive chat REPL with special commands (/quit, /clear, /help).

        Verifies that:
        - /quit exits the REPL cleanly
        - /clear clears conversation history
        - /help displays available commands
        - REPL loop handles commands correctly
        """
        with (
            patch("secondbrain.rag.RAGPipeline"),
            patch("secondbrain.conversation.ConversationSession") as mock_session_class,
            patch("secondbrain.config.get_config") as mock_get_config,
        ):
            # Mock config
            mock_config = MagicMock()
            mock_config.llm_model = "llama3.2"
            mock_config.ollama_host = "http://localhost:11435"
            mock_config.rag_context_window = 10
            mock_config.llm_temperature = 0.1
            mock_config.llm_max_tokens = 2048
            mock_get_config.return_value = mock_config

            # Mock session
            mock_session = MagicMock()
            mock_session.is_empty = True
            mock_session_class.load.return_value = None
            mock_session_class.create.return_value = mock_session

            runner = CliRunner()

            # Test /quit command
            result = runner.invoke(
                cli, ["chat", "--session", "test-quit"], input="/quit\n"
            )
            assert result.exit_code == 0
            assert "Goodbye!" in result.output
            assert "Interactive Chat" in result.output

            # Test /help command followed by /quit
            result = runner.invoke(
                cli, ["chat", "--session", "test-help"], input="/help\n/quit\n"
            )
            assert result.exit_code == 0
            assert "Commands:" in result.output
            assert "/quit" in result.output
            assert "/clear" in result.output
            assert "Goodbye!" in result.output

            # Test /clear command followed by /quit
            result = runner.invoke(
                cli, ["chat", "--session", "test-clear"], input="/clear\n/quit\n"
            )
            assert result.exit_code == 0
            mock_session.clear_history.assert_called_once()
            assert "History cleared" in result.output
            assert "Goodbye!" in result.output

    def test_interactive_chat_error_handling(self) -> None:
        """Test LLM failure recovery in interactive chat.

        Verifies that:
        - LLM failures are caught and displayed gracefully
        - REPL continues after errors
        - ServiceUnavailableError is handled properly
        - User can continue chatting after error recovery
        """
        with (
            patch("secondbrain.rag.RAGPipeline") as mock_pipeline_class,
            patch("secondbrain.conversation.ConversationSession") as mock_session_class,
            patch("secondbrain.config.get_config") as mock_get_config,
        ):
            # Mock config
            mock_config = MagicMock()
            mock_config.llm_model = "llama3.2"
            mock_config.ollama_host = "http://localhost:11435"
            mock_config.rag_context_window = 10
            mock_config.llm_temperature = 0.1
            mock_config.llm_max_tokens = 2048
            mock_get_config.return_value = mock_config

            # Mock session
            mock_session = MagicMock()
            mock_session.is_empty = True
            mock_session_class.load.return_value = None
            mock_session_class.create.return_value = mock_session

            # Mock RAG pipeline with error on first call, success on second
            mock_pipeline = MagicMock()
            mock_pipeline.chat.side_effect = [
                ServiceUnavailableError("LLM server unavailable"),
                {"answer": "Recovery successful!", "rewritten_query": "retry query"},
            ]
            mock_pipeline_class.return_value = mock_pipeline

            runner = CliRunner()

            # Send a query that fails, then another that succeeds, then quit
            result = runner.invoke(
                cli,
                ["chat", "--session", "test-error"],
                input="First query that fails\nSecond query that succeeds\n/quit\n",
            )

            assert result.exit_code == 0
            # Error should be displayed
            assert "Error:" in result.output or "unavailable" in result.output.lower()
            # Recovery answer should be displayed
            assert "Recovery successful!" in result.output
            assert "Goodbye!" in result.output

            # Verify chat was called twice (failed + retry)
            assert mock_pipeline.chat.call_count == 2

    def test_list_sessions(self) -> None:
        """Test --list-sessions flag functionality.

        Verifies that:
        - All sessions are listed with metadata
        - Empty sessions show appropriate status
        - Message counts are displayed correctly
        - Session creation timestamps are shown
        """
        with patch(
            "secondbrain.conversation.ConversationStorage"
        ) as mock_storage_class:
            # Mock storage and sessions
            mock_storage = MagicMock()
            mock_sessions = [
                {
                    "session_id": "session-1",
                    "created_at": "2024-01-01T10:00:00Z",
                    "message_count": 5,
                },
                {
                    "session_id": "session-2",
                    "created_at": "2024-01-02T11:00:00Z",
                    "message_count": 0,
                },
            ]
            mock_storage.list_sessions.return_value = mock_sessions
            mock_storage_class.return_value.__enter__ = MagicMock(
                return_value=mock_storage
            )
            mock_storage_class.return_value.__exit__ = MagicMock(return_value=False)

            runner = CliRunner()
            result = runner.invoke(cli, ["chat", "--list-sessions"])

            assert result.exit_code == 0
            assert "Conversation Sessions" in result.output
            assert "session-1" in result.output
            assert "session-2" in result.output
            assert "5 messages" in result.output
            assert "empty" in result.output  # For session with 0 messages

    def test_delete_session(self) -> None:
        """Test --delete-session flag functionality.

        Verifies that:
        - Existing sessions can be deleted
        - Non-existent sessions show error message
        - Deletion confirmation is displayed
        """
        with (
            patch("secondbrain.cli._ensure_mongodb"),
            patch("secondbrain.conversation.ConversationStorage") as mock_storage_class,
        ):
            # Mock storage
            mock_storage = MagicMock()
            mock_storage.delete_session.return_value = True
            mock_storage_class.return_value.__enter__ = MagicMock(
                return_value=mock_storage
            )
            mock_storage_class.return_value.__exit__ = MagicMock(return_value=False)

            runner = CliRunner()

            # Test successful deletion
            result = runner.invoke(
                cli, ["chat", "--delete-session", "session-to-delete"]
            )
            assert result.exit_code == 0
            assert "Deleted session: session-to-delete" in result.output
            mock_storage.delete_session.assert_called_once_with("session-to-delete")

            # Test deletion of non-existent session
            mock_storage.delete_session.return_value = False
            result = runner.invoke(cli, ["chat", "--delete-session", "nonexistent"])
            assert result.exit_code == 0
            assert "Session not found: nonexistent" in result.output

    def test_check_llm(self) -> None:
        """Test --check-llm flag functionality.

        Verifies that:
        - Ollama health check is performed
        - Available Ollama shows success message with model name
        - Unavailable Ollama shows error and startup instructions
        """
        with (
            patch("secondbrain.rag.providers.OllamaLLMProvider") as mock_provider_class,
            patch("secondbrain.config.get_config") as mock_get_config,
        ):
            # Mock config
            mock_config = MagicMock()
            mock_config.ollama_host = "http://localhost:11435"
            mock_config.llm_model = "llama3.2"
            mock_get_config.return_value = mock_config

            # Mock LLM provider
            mock_provider = MagicMock()
            mock_provider.model = "llama3.2"

            # Test 1: Ollama available
            mock_provider.health_check.return_value = True
            mock_provider_class.return_value = mock_provider

            runner = CliRunner()
            result = runner.invoke(cli, ["chat", "--check-llm"])

            assert result.exit_code == 0
            assert "Ollama is available" in result.output
            assert "llama3.2" in result.output
            mock_provider.health_check.assert_called_once()

            # Test 2: Ollama unavailable
            mock_provider.health_check.return_value = False
            result = runner.invoke(cli, ["chat", "--check-llm"])

            assert result.exit_code == 0
            assert "Ollama is not available" in result.output
            assert "sentence-transformers serve" in result.output
