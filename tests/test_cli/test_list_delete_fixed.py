"""Tests for list and delete CLI commands with proper mocking.

This module provides comprehensive tests for the list and delete command
functionality with correct mocking strategy - patching at module level
and mocking classes, not instances.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from secondbrain.cli.commands import cli


def create_mock_lister(
    return_value: list | None = None, side_effect: Exception | None = None
) -> MagicMock:
    """Create a properly configured mock Lister for context manager usage.

    Args:
        return_value: List to return from list_chunks()
        side_effect: Exception to raise from list_chunks()

    Returns:
        A MagicMock configured as a context manager that returns itself,
        with list_chunks() method set up correctly.
    """
    mock_instance = MagicMock()

    if side_effect:
        mock_instance.list_chunks.side_effect = side_effect
    else:
        mock_instance.list_chunks.return_value = return_value or []

    # Set up context manager protocol
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)

    # The class mock returns the instance
    mock_class = MagicMock(return_value=mock_instance)

    return mock_class


def create_mock_deleter(
    return_value: int = 0, side_effect: Exception | None = None
) -> MagicMock:
    """Create a properly configured mock Deleter for context manager usage.

    Args:
        return_value: Number to return from delete()
        side_effect: Exception to raise from delete()

    Returns:
        A MagicMock configured as a context manager that returns itself,
        with delete() method set up correctly.
    """
    mock_instance = MagicMock()

    if side_effect:
        mock_instance.delete.side_effect = side_effect
    else:
        mock_instance.delete.return_value = return_value

    # Set up context manager protocol
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)

    # The class mock returns the instance
    mock_class = MagicMock(return_value=mock_instance)

    return mock_class


class TestListWithLimitParameter:
    """Tests for list command --limit parameter."""

    def test_list_with_limit_parameter(self) -> None:
        """Test --limit parameter restricts results."""
        mock_lister_class = create_mock_lister(
            return_value=[
                {
                    "source_file": "doc1.pdf",
                    "chunk_id": "chunk1",
                    "page_number": 1,
                    "chunk_text": "test content 1",
                },
                {
                    "source_file": "doc2.pdf",
                    "chunk_id": "chunk2",
                    "page_number": 2,
                    "chunk_text": "test content 2",
                },
                {
                    "source_file": "doc3.pdf",
                    "chunk_id": "chunk3",
                    "page_number": 3,
                    "chunk_text": "test content 3",
                },
            ]
        )

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--limit", "2"])

        assert result.exit_code == 0
        mock_instance = mock_lister_class.return_value
        mock_instance.list_chunks.assert_called_once()
        call_kwargs = mock_instance.list_chunks.call_args[1]
        assert call_kwargs["limit"] == 2

    def test_list_with_offset_parameter(self) -> None:
        """Test --offset parameter for pagination."""
        mock_lister_class = create_mock_lister(
            return_value=[
                {
                    "source_file": "doc3.pdf",
                    "chunk_id": "chunk3",
                    "page_number": 3,
                    "chunk_text": "test content 3",
                },
                {
                    "source_file": "doc4.pdf",
                    "chunk_id": "chunk4",
                    "page_number": 4,
                    "chunk_text": "test content 4",
                },
            ]
        )

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--offset", "2"])

        assert result.exit_code == 0
        mock_instance = mock_lister_class.return_value
        mock_instance.list_chunks.assert_called_once()
        call_kwargs = mock_instance.list_chunks.call_args[1]
        assert call_kwargs["offset"] == 2

    def test_list_pagination_combined(self) -> None:
        """Test limit + offset for pagination."""
        mock_lister_class = create_mock_lister(
            return_value=[
                {
                    "source_file": "doc3.pdf",
                    "chunk_id": "chunk3",
                    "page_number": 3,
                    "chunk_text": "test content 3",
                }
            ]
        )

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--limit", "5", "--offset", "10"])

        assert result.exit_code == 0
        mock_instance = mock_lister_class.return_value
        mock_instance.list_chunks.assert_called_once()
        call_kwargs = mock_instance.list_chunks.call_args[1]
        assert call_kwargs["limit"] == 5
        assert call_kwargs["offset"] == 10

    def test_list_all_flag_bypasses_limit(self) -> None:
        """Test --all flag bypasses default limit."""
        mock_lister_class = create_mock_lister(
            return_value=[
                {
                    "source_file": f"doc{i}.pdf",
                    "chunk_id": f"chunk{i}",
                    "page_number": i,
                    "chunk_text": f"content {i}",
                }
                for i in range(150)
            ]
        )

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--all"])

        assert result.exit_code == 0
        mock_instance = mock_lister_class.return_value
        mock_instance.list_chunks.assert_called_once()
        call_kwargs = mock_instance.list_chunks.call_args[1]
        # --all should set limit to MAX_LIST_LIMIT (100000)
        assert call_kwargs["limit"] == 100000

    def test_list_validation_negative_limit(self) -> None:
        """Test negative limit rejection."""
        mock_lister_class = create_mock_lister()

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--limit", "-5"])

        assert result.exit_code != 0
        assert result.exception is not None
        assert "Limit must be non-negative" in str(result.exception)

    def test_list_validation_negative_offset(self) -> None:
        """Test negative offset rejection."""
        mock_lister_class = create_mock_lister()

        with patch("secondbrain.management.Lister", mock_lister_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["ls", "--offset", "-10"])

        assert result.exit_code != 0
        assert result.exception is not None
        assert "Offset must be non-negative" in str(result.exception)


class TestDeleteConfirmation:
    """Tests for delete command confirmation behavior."""

    def test_delete_requires_confirmation(self) -> None:
        """Test interactive confirmation is required."""
        mock_deleter_class = create_mock_deleter(return_value=5)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            # Simulate user answering 'n' to confirmation
            result = runner.invoke(cli, ["delete", "--source", "test.pdf"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_with_yes_flag(self) -> None:
        """Test --yes flag skips confirmation."""
        mock_deleter_class = create_mock_deleter(return_value=3)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--source", "test.pdf", "--yes"])

        assert result.exit_code == 0
        assert "Deleted 3 document(s)" in result.output
        mock_instance = mock_deleter_class.return_value
        mock_instance.delete.assert_called_once()
        call_kwargs = mock_instance.delete.call_args[1]
        assert call_kwargs["source"] == "test.pdf"

    def test_delete_all_confirmation(self) -> None:
        """Test --all with confirmation."""
        mock_deleter_class = create_mock_deleter(return_value=100)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            # Simulate user answering 'y' to confirmation
            result = runner.invoke(cli, ["delete", "--all"], input="y\n")

        assert result.exit_code == 0
        assert "Deleted 100 document(s)" in result.output
        mock_instance = mock_deleter_class.return_value
        mock_instance.delete.assert_called_once()
        call_kwargs = mock_instance.delete.call_args[1]
        assert call_kwargs["all"] is True

    def test_delete_mutually_exclusive_options(self) -> None:
        """Test option validation - only one option allowed."""
        mock_deleter_class = create_mock_deleter()

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--source", "test.pdf", "--all"])

        assert result.exit_code == 1
        assert "Specify only one of" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_by_chunk_id(self) -> None:
        """Test --chunk-id option."""
        mock_deleter_class = create_mock_deleter(return_value=1)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--chunk-id", "chunk-123", "--yes"])

        assert result.exit_code == 0
        assert "Deleted 1 document(s)" in result.output
        mock_instance = mock_deleter_class.return_value
        mock_instance.delete.assert_called_once()
        call_kwargs = mock_instance.delete.call_args[1]
        assert call_kwargs["chunk_id"] == "chunk-123"

    def test_delete_by_source(self) -> None:
        """Test --source option."""
        mock_deleter_class = create_mock_deleter(return_value=5)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["delete", "--source", "/path/to/doc.pdf", "--yes"]
            )

        assert result.exit_code == 0
        assert "Deleted 5 document(s)" in result.output
        mock_instance = mock_deleter_class.return_value
        mock_instance.delete.assert_called_once()
        call_kwargs = mock_instance.delete.call_args[1]
        assert call_kwargs["source"] == "/path/to/doc.pdf"


class TestDeleteByFileType:
    """Tests for the delete command --file-type filter (archived spec scenario)."""

    def test_delete_by_file_type(self) -> None:
        """Test --file-type passes the normalized category to the deleter."""
        mock_deleter_class = create_mock_deleter(return_value=42)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", "pdf", "--yes"])

        assert result.exit_code == 0
        assert "Deleted 42 document(s)" in result.output
        mock_instance = mock_deleter_class.return_value
        mock_instance.delete.assert_called_once()
        call_kwargs = mock_instance.delete.call_args[1]
        assert call_kwargs["file_type"] == "pdf"
        assert call_kwargs["source"] is None
        assert call_kwargs["chunk_id"] is None
        assert call_kwargs["all"] is False

    def test_delete_file_type_requires_confirmation(self) -> None:
        """Test --file-type without --yes asks for confirmation."""
        mock_deleter_class = create_mock_deleter(return_value=7)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", "pdf"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_file_type_extension_alias(self) -> None:
        """Test an extension-style value is mapped to its stored category."""
        mock_deleter_class = create_mock_deleter(return_value=4)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", "md", "--yes"])

        assert result.exit_code == 0
        call_kwargs = mock_deleter_class.return_value.delete.call_args[1]
        assert call_kwargs["file_type"] == "markdown"

    def test_delete_file_type_dotted_extension_alias(self) -> None:
        """Test a dotted extension value (".pdf") maps to the pdf category."""
        mock_deleter_class = create_mock_deleter(return_value=4)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", ".pdf", "--yes"])

        assert result.exit_code == 0
        call_kwargs = mock_deleter_class.return_value.delete.call_args[1]
        assert call_kwargs["file_type"] == "pdf"

    def test_delete_file_type_is_case_insensitive(self) -> None:
        """Test value normalization lowercases the file type."""
        mock_deleter_class = create_mock_deleter(return_value=4)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", "PDF", "--yes"])

        assert result.exit_code == 0
        call_kwargs = mock_deleter_class.return_value.delete.call_args[1]
        assert call_kwargs["file_type"] == "pdf"

    def test_delete_file_type_mutually_exclusive_with_source(self) -> None:
        """Test --file-type cannot be combined with --source."""
        mock_deleter_class = create_mock_deleter()

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(
                cli, ["delete", "--source", "test.pdf", "--file-type", "pdf"]
            )

        assert result.exit_code == 1
        assert "Specify only one of" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_file_type_mutually_exclusive_with_all(self) -> None:
        """Test --file-type cannot be combined with --all."""
        mock_deleter_class = create_mock_deleter()

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--all", "--file-type", "pdf"])

        assert result.exit_code == 1
        assert "Specify only one of" in result.output
        mock_deleter_class.return_value.delete.assert_not_called()

    def test_delete_file_type_only_selector_is_valid(self) -> None:
        """Test --file-type alone satisfies the required-selector validation."""
        mock_deleter_class = create_mock_deleter(return_value=9)

        with patch("secondbrain.management.Deleter", mock_deleter_class):
            runner = CliRunner()
            result = runner.invoke(cli, ["delete", "--file-type", "docx", "--yes"])

        assert result.exit_code == 0
        assert "Deleted 9 document(s)" in result.output
