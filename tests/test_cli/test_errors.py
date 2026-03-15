"""Tests for CLI error handling module.

This module provides comprehensive test coverage for the handle_cli_errors
decorator, ensuring all exception paths are properly handled.
"""

import logging

import click
import pytest
from click.testing import CliRunner

from secondbrain.cli.errors import handle_cli_errors
from secondbrain.exceptions import CLIValidationError


class TestHandleCliErrors:
    """Test suite for handle_cli_errors decorator."""

    def test_handles_click_bad_parameter(self):
        """Test that click.BadParameter is caught and handled gracefully."""

        @handle_cli_errors
        def test_func():
            raise click.BadParameter("Invalid value for '--name'")

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_handles_value_error(self):
        """Test that ValueError is caught and handled gracefully."""

        @handle_cli_errors
        def test_func():
            raise ValueError("Invalid configuration value")

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_handles_file_not_found(self):
        """Test that FileNotFoundError is caught and handled gracefully."""

        @handle_cli_errors
        def test_func():
            raise FileNotFoundError("Config file not found: config.yaml")

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_handles_cli_validation_error(self):
        """Test that CLIValidationError is caught and handled gracefully."""

        @handle_cli_errors
        def test_func():
            raise CLIValidationError("Limit must be non-negative")

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_handles_generic_exception(self):
        """Test that generic Exception is caught and handled gracefully."""

        @handle_cli_errors
        def test_func():
            raise RuntimeError("Unexpected error occurred")

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_verbose_suggestion_shown(self, capsys):
        """Test that verbose suggestion is shown on error."""

        @handle_cli_errors
        def test_func():
            raise ValueError("Test error")

        with pytest.raises(SystemExit):
            test_func()

        captured = capsys.readouterr()
        assert "Run with --verbose for full traceback" in captured.out

    def test_successful_execution_no_error(self):
        """Test that successful execution returns normally."""

        @handle_cli_errors
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_logging_called_on_error(self, caplog):
        """Test that error is logged when exception occurs."""

        @handle_cli_errors
        def test_func():
            raise ValueError("Test error for logging")

        with caplog.at_level(logging.WARNING), pytest.raises(SystemExit):
            test_func()

        assert any(
            "Test error for logging" in record.message for record in caplog.records
        )

    def test_logging_exception_on_unexpected_error(self, caplog):
        """Test that full exception is logged on unexpected error."""

        @handle_cli_errors
        def test_func():
            raise RuntimeError("Unexpected error")

        with caplog.at_level(logging.DEBUG), pytest.raises(SystemExit):
            test_func()

        # Should log with exception info
        assert any("Unexpected error" in record.message for record in caplog.records)

    def test_click_bad_parameter_with_full_message(self, capsys):
        """Test click.BadParameter shows full error message."""

        @handle_cli_errors
        def test_func():
            raise click.BadParameter(
                "Invalid value for '--output': must be a valid file path"
            )

        with pytest.raises(SystemExit):
            test_func()

        captured = capsys.readouterr()
        assert "Invalid value for '--output'" in captured.out

    def test_file_not_found_with_path(self, capsys):
        """Test FileNotFoundError shows file path in message."""

        @handle_cli_errors
        def test_func():
            raise FileNotFoundError("/path/to/file.txt")

        with pytest.raises(SystemExit):
            test_func()

        captured = capsys.readouterr()
        assert "/path/to/file.txt" in captured.out

    def test_cli_validation_error_preserves_message(self, capsys):
        """Test CLIValidationError preserves the validation message."""

        @handle_cli_errors
        def test_func():
            raise CLIValidationError("Offset must be non-negative")

        with pytest.raises(SystemExit):
            test_func()

        captured = capsys.readouterr()
        assert "Offset must be non-negative" in captured.out


class TestHandleCliErrorsWithCliRunner:
    """Test handle_cli_errors with Click's CliRunner for integration testing."""

    def test_error_handling_in_click_command(self):
        """Test error handling in a Click command context."""
        runner = CliRunner()

        @click.command()
        @handle_cli_errors
        def test_cmd():
            raise ValueError("Command error")

        result = runner.invoke(test_cmd, [])
        assert result.exit_code == 1
        assert "Error:" in result.output

    def test_successful_click_command(self):
        """Test successful Click command execution."""
        runner = CliRunner()

        @click.command()
        @handle_cli_errors
        def test_cmd():
            click.echo("Success!")

        result = runner.invoke(test_cmd, [])
        assert result.exit_code == 0
        assert "Success!" in result.output

    def test_click_bad_parameter_in_command(self):
        """Test Click parameter error in command context."""
        runner = CliRunner()

        @click.command()
        @click.option("--value", required=True)
        @handle_cli_errors
        def test_cmd(value):
            if not value:
                raise click.BadParameter("Value is required")
            click.echo(f"Value: {value}")

        result = runner.invoke(test_cmd, [])
        assert result.exit_code != 0  # Click handles required option error


class TestHandleCliErrorsEdgeCases:
    """Test edge cases for handle_cli_errors decorator."""

    def test_nested_exception_handling(self):
        """Test that nested exceptions are handled correctly."""

        @handle_cli_errors
        def inner_func():
            raise ValueError("Inner error")

        @handle_cli_errors
        def outer_func():
            inner_func()

        with pytest.raises(SystemExit) as exc_info:
            outer_func()

        assert exc_info.value.code == 1

    def test_exception_with_none_message(self):
        """Test exception with None message."""

        @handle_cli_errors
        def test_func():
            exc = Exception()
            exc.args = ()
            raise exc

        with pytest.raises(SystemExit) as exc_info:
            test_func()

        assert exc_info.value.code == 1

    def test_exception_with_empty_string_message(self, capsys):
        """Test exception with empty string message."""

        @handle_cli_errors
        def test_func():
            raise Exception("")

        with pytest.raises(SystemExit):
            test_func()

        captured = capsys.readouterr()
        # Should still show error message even if empty
        assert "Error:" in captured.out

    def test_multiple_sequential_errors(self):
        """Test that multiple sequential calls handle errors independently."""
        call_count = 0

        @handle_cli_errors
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First error")
            return "success"

        # First call should fail
        with pytest.raises(SystemExit):
            test_func()

        # Second call should succeed
        result = test_func()
        assert result == "success"
        assert call_count == 2
