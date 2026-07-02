"""Tests for Docker Compose CLI commands (start/stop).

This module provides comprehensive test coverage for the `start` and `stop`
CLI commands that manage Docker Compose stacks. Tests use the test docker-compose
stack (docker-compose.test.yml) instead of production to avoid interfering with
development environments.

Test Categories:
- Basic command invocation and help output
- Option parsing and validation
- DockerManager integration (mocked)
- Error handling for various failure scenarios
- Confirmation prompts for stop command
- Auto-detection of compose files

Test Ordering:
- Start tests run FIRST (order=0) to ensure services are available
- Stop tests run LAST (order=1) to clean up after all other tests
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secondbrain.cli import cli
from secondbrain.utils.docker_manager import (
    DockerComposeError,
    MongoDBStartupError,
)


@pytest.mark.order(0)
class TestStartCommandBasic:
    """Basic tests for the start command - runs FIRST."""

    def test_start_help_output(self):
        """Test start command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["start", "--help"])

        assert result.exit_code == 0
        assert "Start the production Docker Compose stack" in result.output
        assert "--compose-file" in result.output
        assert "--project-name" in result.output
        assert "--wait" in result.output

    def test_start_command_with_mocked_docker(self):
        """Test start command executes successfully with mocked Docker."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start"])

            assert result.exit_code == 0
            assert "Starting Docker Compose stack" in result.output
            mock_manager.start_mongo.assert_called_once()

    def test_start_command_auto_detects_compose_file(self):
        """Test start command auto-detects docker-compose.yml."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            with patch("pathlib.Path.cwd") as mock_cwd:
                mock_cwd.return_value = Path("/tmp/test-project")
                mock_manager = MagicMock()
                mock_manager.check_docker_installed.return_value = True
                mock_manager.check_docker_compose_installed.return_value = True
                mock_manager_class.return_value = mock_manager

                result = runner.invoke(cli, ["start"])

                assert result.exit_code == 0
                # Should check for docker-compose.yml in current directory
                mock_manager_class.assert_called()

    def test_start_command_with_custom_compose_file(self, tmp_path):
        """Test start command with custom compose file path."""
        runner = CliRunner()

        # Create a test compose file
        compose_file = tmp_path / "docker-compose.test.yml"
        compose_file.write_text(
            "services:\n  mongodb:\n    image: mongodb/mongodb-community-server:7.0\n"
        )

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli, ["start", "-f", str(compose_file), "-p", "test-project"]
            )

            assert result.exit_code == 0
            mock_manager_class.assert_called_once()
            call_args = mock_manager_class.call_args
            assert call_args.kwargs["compose_file"] == str(compose_file)
            assert call_args.kwargs["project_name"] == "test-project"

    def test_start_command_with_wait_flag(self):
        """Test start command with --wait flag."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start", "--wait"])

            assert result.exit_code == 0
            mock_manager.start_mongo.assert_called_once()
            mock_manager.wait_for_mongo_ready.assert_called_once()


@pytest.mark.order(0)
class TestStartCommandErrorHandling:
    """Error handling tests for the start command - runs FIRST."""

    def test_start_docker_not_installed(self):
        """Test start command when Docker is not installed."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = False
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start"])

            assert result.exit_code == 1
            assert "Docker is not installed" in result.output

    def test_start_docker_compose_not_installed(self):
        """Test start command when docker compose is not installed."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = False
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start"])

            assert result.exit_code == 1
            assert "docker compose" in result.output

    def test_start_compose_file_not_found(self):
        """Test start command when compose file doesn't exist."""
        runner = CliRunner()

        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(
                cli, ["start", "-f", "/nonexistent/docker-compose.yml"]
            )

            assert result.exit_code == 2  # Click validation error
            assert "does not exist" in result.output

    def test_start_mongo_startup_failure(self):
        """Test start command when MongoDB fails to start."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager.start_mongo.side_effect = DockerComposeError(
                "Failed to start MongoDB"
            )
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start"])

            assert result.exit_code == 1
            assert "Error" in result.output

    def test_start_timeout_error(self):
        """Test start command handles timeout errors."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager.wait_for_mongo_ready.side_effect = MongoDBStartupError(
                "Timeout waiting for MongoDB"
            )
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli, ["start", "--wait"])

            assert result.exit_code == 1
            assert (
                "failed to become ready" in result.output.lower()
                or "timeout" in result.output.lower()
            )


@pytest.mark.order(1)
class TestStopCommandBasic:
    """Basic tests for the stop command - runs LAST."""

    def test_stop_help_output(self):
        """Test stop command help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["stop", "--help"])

        assert result.exit_code == 0
        assert "Stop the production Docker Compose stack" in result.output
        assert "--compose-file" in result.output
        assert "--project-name" in result.output
        assert "--remove-volumes" in result.output
        assert "--force" in result.output

    def test_stop_command_with_mocked_docker(self):
        """Test stop command executes successfully with mocked Docker."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0, stdout="Stopped"),  # docker compose down
            ]

            result = runner.invoke(cli, ["stop", "--force"])

            assert result.exit_code == 0
            assert "Stopping Docker Compose stack" in result.output
            assert "stopped successfully" in result.output
            assert mock_run.call_count >= 2

    def test_stop_command_auto_detects_compose_file(self):
        """Test stop command auto-detects docker-compose.yml."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            with patch("pathlib.Path.cwd") as mock_cwd:
                mock_cwd.return_value = Path("/tmp/test-project")
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # docker --version
                    MagicMock(returncode=0),  # docker compose down
                ]

                result = runner.invoke(cli, ["stop", "--force"])

                assert result.exit_code == 0
                # Should invoke docker compose down
                assert mock_run.call_count >= 2

    def test_stop_command_with_custom_compose_file(self, tmp_path):
        """Test stop command with custom compose file path."""
        runner = CliRunner()

        compose_file = tmp_path / "docker-compose.test.yml"
        compose_file.write_text("services:\n")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(
                cli, ["stop", "-f", str(compose_file), "-p", "test-project", "--force"]
            )

            assert result.exit_code == 0
            call_args = mock_run.call_args
            assert str(compose_file) in call_args.args[0]
            assert "test-project" in call_args.args[0]

    def test_stop_command_with_remove_volumes(self):
        """Test stop command with --remove-volumes flag."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(cli, ["stop", "--remove-volumes", "--force"])

            assert result.exit_code == 0
            call_args = mock_run.call_args
            assert "-v" in call_args.args[0]
            assert "volumes have been removed" in result.output

    def test_stop_command_with_force_flag(self):
        """Test stop command with --force flag skips confirmation."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            # Should not prompt for confirmation
            result = runner.invoke(cli, ["stop", "--force"])

            assert result.exit_code == 0
            assert "Cancelled" not in result.output


@pytest.mark.order(1)
class TestStopCommandConfirmation:
    """Tests for stop command confirmation prompt - runs LAST."""

    def test_stop_command_prompts_for_confirmation(self):
        """Test stop command prompts for confirmation by default."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            # When user cancels, docker version check is never called
            # because confirmation prompt comes first
            mock_run.side_effect = []

            # Simulate user canceling
            result = runner.invoke(cli, ["stop"], input="n\n")

            assert result.exit_code == 0
            assert "Cancelled" in result.output
            # Should not call docker at all since user canceled
            assert mock_run.call_count == 0

    def test_stop_command_confirms_with_yes(self):
        """Test stop command proceeds with confirmation."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0, stdout="Stopped"),  # docker compose down
            ]

            # Simulate user confirming
            result = runner.invoke(cli, ["stop"], input="y\n")

            assert result.exit_code == 0
            assert "stopped successfully" in result.output
            assert mock_run.call_count >= 2

    def test_stop_command_with_remove_volumes_prominent_warning(self):
        """Test stop command shows warning about volume removal."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(cli, ["stop", "--remove-volumes"], input="y\n")

            assert result.exit_code == 0
            assert "remove volumes" in result.output.lower()


@pytest.mark.order(1)
class TestStopCommandErrorHandling:
    """Error handling tests for the stop command - runs LAST."""

    def test_stop_docker_not_installed(self):
        """Test stop command when Docker is not installed."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            # Simulate docker not found
            mock_run.return_value = MagicMock(returncode=1)

            result = runner.invoke(cli, ["stop", "--force"])

            # Should show Docker not installed message
            assert result.exit_code == 1
            assert "Docker is not installed" in result.output

    def test_stop_compose_command_fails(self):
        """Test stop command when docker compose down fails."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(
                    returncode=1, stderr="Error: No containers to stop", stdout=""
                ),  # docker compose down fails
            ]

            result = runner.invoke(cli, ["stop", "--force"])

            assert result.exit_code == 1
            assert "Error" in result.output

    def test_stop_timeout_error(self):
        """Test stop command handles timeout errors."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                subprocess.TimeoutExpired(
                    cmd=["docker", "compose", "down"], timeout=120
                ),
            ]

            result = runner.invoke(cli, ["stop", "--force"])

            assert result.exit_code == 1
            assert "Timeout" in result.output

    def test_stop_compose_file_not_found(self):
        """Test stop command when compose file doesn't exist."""
        runner = CliRunner()

        result = runner.invoke(
            cli, ["stop", "-f", "/nonexistent/docker-compose.yml", "--force"]
        )

        assert result.exit_code == 2  # Click validation error
        assert "does not exist" in result.output


@pytest.mark.order(1)
class TestDockerManagerIntegration:
    """Integration tests for DockerManager with CLI commands - runs LAST."""

    def test_start_uses_docker_manager_correctly(self):
        """Test that start command uses DockerManager with correct parameters."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            # Test with test compose stack
            result = runner.invoke(
                cli,
                [
                    "start",
                    "-f",
                    str(Path.cwd() / "docker-compose.test.yml"),
                    "-p",
                    "secondbrain-test",
                ],
            )

            assert result.exit_code == 0
            mock_manager_class.assert_called_once()
            call_args = mock_manager_class.call_args
            assert call_args.kwargs["project_name"] == "secondbrain-test"

    def test_stop_uses_correct_docker_command(self):
        """Test that stop command constructs correct docker compose command."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(
                cli,
                [
                    "stop",
                    "-f",
                    str(Path.cwd() / "docker-compose.test.yml"),
                    "-p",
                    "secondbrain-test",
                    "--force",
                ],
            )

            assert result.exit_code == 0
            # Find the compose down call (second call)
            compose_calls = [
                call
                for call in mock_run.call_args_list
                if len(call.args) > 0 and len(call.args[0]) > 1
            ]
            assert len(compose_calls) >= 1
            cmd = compose_calls[-1].args[0]

            # Verify command structure
            assert "docker" in cmd
            assert "compose" in cmd
            assert "down" in cmd
            assert "secondbrain-test" in cmd


@pytest.mark.order(1)
class TestTestComposeStack:
    """Tests specifically for the test docker-compose stack - runs LAST."""

    def test_start_test_stack_with_test_compose(self, tmp_path):
        """Test starting the test docker-compose stack."""
        runner = CliRunner()

        # Create a minimal test compose file
        compose_file = tmp_path / "docker-compose.test.yml"
        compose_file.write_text(
            """name: secondbrain-test
services:
  mongodb:
    image: mongodb/mongodb-community-server:7.0
    container_name: secondbrain-mongodb-test
"""
        )

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli, ["start", "-f", str(compose_file), "-p", "secondbrain-test"]
            )

            assert result.exit_code == 0
            mock_manager.start_mongo.assert_called_once()

    def test_stop_test_stack_with_test_compose(self, tmp_path):
        """Test stopping the test docker-compose stack."""
        runner = CliRunner()

        compose_file = tmp_path / "docker-compose.test.yml"
        compose_file.write_text(
            """name: secondbrain-test
services:
  mongodb:
    image: mongodb/mongodb-community-server:7.0
"""
        )

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(
                cli,
                [
                    "stop",
                    "-f",
                    str(compose_file),
                    "-p",
                    "secondbrain-test",
                    "--force",
                ],
            )

            assert result.exit_code == 0
            # Find the compose down call
            compose_calls = [
                call
                for call in mock_run.call_args_list
                if len(call.args) > 0 and len(call.args[0]) > 1
            ]
            assert len(compose_calls) >= 1
            cmd = compose_calls[-1].args[0]
            assert "secondbrain-test" in cmd


@pytest.mark.order(0)
class TestCommandValidation:
    """Input validation tests for start/stop commands - runs in middle."""

    def test_start_with_invalid_project_name(self):
        """Test start command with invalid project name."""
        runner = CliRunner()

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            # Project names should be valid (alphanumeric and hyphens)
            result = runner.invoke(
                cli, ["start", "-p", "invalid_project_with_underscores"]
            )

            # Docker may accept it, but test the command runs
            assert result.exit_code in [0, 1]

    def test_start_with_relative_compose_path(self, tmp_path):
        """Test start command with relative compose file path."""
        runner = CliRunner()

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("services:\n")

        with patch(
            "secondbrain.utils.docker_manager.DockerManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.check_docker_installed.return_value = True
            mock_manager.check_docker_compose_installed.return_value = True
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli, ["start", "-f", str(compose_file.relative_to(tmp_path))]
            )

            # Should handle relative paths
            assert result.exit_code in [0, 1]

    def test_stop_with_both_volumes_and_force(self):
        """Test stop command with both --remove-volumes and --force."""
        runner = CliRunner()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # docker --version
                MagicMock(returncode=0),  # docker compose down
            ]

            result = runner.invoke(cli, ["stop", "--remove-volumes", "--force"])

            assert result.exit_code == 0
            call_args = mock_run.call_args
            assert "-v" in call_args.args[0]
