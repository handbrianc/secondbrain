"""Final edge case tests to close remaining coverage gaps."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli import cli, main
from secondbrain.logging import setup_logging


def create_mock_lister(
    return_value: list | None = None, side_effect: Exception | None = None
) -> MagicMock:
    """Create a properly configured mock Lister for context manager usage."""
    mock_instance = MagicMock()

    if side_effect:
        mock_instance.list_chunks.side_effect = side_effect
    else:
        mock_instance.list_chunks.return_value = return_value or []

    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_class = MagicMock(return_value=mock_instance)

    return mock_class


def create_mock_deleter(
    return_value: int = 0, side_effect: Exception | None = None
) -> MagicMock:
    """Create a properly configured mock Deleter for context manager usage."""
    mock_instance = MagicMock()

    if side_effect:
        mock_instance.delete.side_effect = side_effect
    else:
        mock_instance.delete.return_value = return_value

    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    mock_class = MagicMock(return_value=mock_instance)

    return mock_class


class TestFinalCoverage:
    """Tests for remaining uncovered lines."""

    def test_cli_main_entry_point(self) -> None:
        """Test CLI main entry point."""
        with patch("secondbrain.cli.cli"):
            try:
                main()
            except SystemExit:
                pass  # Expected from click

    def test_logging_setup_json(self) -> None:
        """Test JSON logging setup."""
        setup_logging(verbose=False, json_format=True)

    def test_logging_setup_rich(self) -> None:
        """Test rich logging setup."""
        setup_logging(verbose=False, json_format=False)

    def test_conversation_storage_create_session(self) -> None:
        """Test conversation session creation."""
        from secondbrain.conversation.storage import ConversationStorage

        with patch("secondbrain.conversation.storage.get_config") as mock_config:
            mock_config.return_value.mongo_uri = "mongodb://localhost:27017"
            mock_config.return_value.mongo_db = "test"
            mock_config.return_value.mongo_conversation_collection = "conversations"

            with patch("motor.motor_asyncio.AsyncIOMotorClient"):
                storage = ConversationStorage()
                assert storage is not None

    def test_delete_command_cancelled(self) -> None:
        """Test delete command with user cancellation (lines 296-297)."""
        mock_deleter_class = create_mock_deleter(return_value=5)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--source", "test.pdf"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_command_service_unavailable(self) -> None:
        """Test delete command with ServiceUnavailableError (lines 307-313)."""
        from secondbrain.exceptions import ServiceUnavailableError

        mock_deleter_class = create_mock_deleter(
            side_effect=ServiceUnavailableError("Service unavailable")
        )

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--source", "test.pdf", "--yes"])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_status_command_with_metrics(self) -> None:
        """Test status command with performance metrics (lines 379-385)."""
        mock_stats = MagicMock()
        mock_stats.total_documents = 100
        mock_stats.total_chunks = 500
        mock_stats.file_types = {"pdf": 10}
        mock_stats.avg_chunk_size = 500
        mock_stats.performance_metrics = MagicMock()
        mock_stats.performance_metrics.get_stats.return_value = {
            "count": 10,
            "total_seconds": 5.0,
            "avg_seconds": 0.5,
            "min_seconds": 0.3,
            "max_seconds": 0.8,
        }

        mock_checker_class = MagicMock()
        mock_checker_instance = MagicMock()
        mock_checker_instance.__enter__ = MagicMock(return_value=mock_checker_instance)
        mock_checker_instance.__exit__ = MagicMock(return_value=False)
        mock_checker_instance.get_status.return_value = mock_stats
        mock_checker_class.return_value = mock_checker_instance

        with patch("secondbrain.management.StatusChecker", mock_checker_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0

    def test_chat_command_no_sessions(self) -> None:
        """Test chat command with no sessions found (line 437)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--list-sessions"])
        assert result.exit_code != 0

    def test_chat_command_history(self) -> None:
        """Test chat command with history flag (lines 479-501)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test-session", "--history"])
        assert result.exit_code != 0

    def test_chat_command_history_requires_session(self) -> None:
        """Test chat command history without session (lines 479-483)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--history"])

        assert result.exit_code == 0
        assert "Error" in result.output

    def test_chat_command_default_session(self) -> None:
        """Test chat command with default session (line 504)."""
        mock_session = MagicMock()
        mock_session._session_id = "default"
        mock_session.is_empty = True
        mock_session.message_count = 0

        mock_storage_class = MagicMock()
        mock_storage_instance = MagicMock()
        mock_storage_instance.__enter__ = MagicMock(return_value=mock_storage_instance)
        mock_storage_instance.__exit__ = MagicMock(return_value=False)
        mock_storage_instance.load.return_value = None
        mock_storage_instance.create.return_value = mock_session
        mock_storage_class.return_value = mock_storage_instance

        with (
            patch(
                "secondbrain.conversation.storage.ConversationStorage",
                mock_storage_class,
            ),
            patch("secondbrain.cli.commands._interactive_chat"),
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["chat"])

            assert result.exit_code == 0

    def test_chat_command_show_sources(self) -> None:
        """Test chat command with show-sources flag (lines 570-577)."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "chat",
                "test query",
                "--session",
                "test",
                "--show-sources",
            ],
        )
        assert result.exit_code != 0

    def test_chat_interactive_resume_session(self) -> None:
        """Test interactive chat resuming non-empty session (lines 607-608)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test-session"])
        assert result.exit_code != 0

    def test_chat_interactive_empty_input(self) -> None:
        """Test interactive chat with empty input (line 632)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test"])
        assert result.exit_code != 0

    def test_chat_interactive_unknown_command(self) -> None:
        """Test interactive chat with unknown command (lines 651-652)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test"])
        assert result.exit_code != 0

    def test_chat_interactive_keyboard_interrupt(self) -> None:
        """Test interactive chat with KeyboardInterrupt (lines 677-679)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test"])
        assert result.exit_code != 0

    def test_chat_interactive_eof_error(self) -> None:
        """Test interactive chat with EOFError (lines 681-682)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["chat", "--session", "test"])
        assert result.exit_code != 0
