import subprocess
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.config import Config
from secondbrain.utils.docker_manager import (
    DockerComposeError,
    DockerManager,
    DockerNotInstalledError,
    QdrantStartupError,
)

_test_config = Config()


class TestDockerManagerBasic:
    def test_init_default_values(self):
        """Test DockerManager initializes with default values."""
        manager = DockerManager()
        assert manager.project_name == "secondbrain"
        assert manager.container_name == "secondbrain-qdrant"
        assert manager.compose_file.exists()

    def test_init_custom_compose_file(self, tmp_path):
        """Test DockerManager with custom compose file."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )
        manager = DockerManager(compose_file=str(compose_file))
        assert manager.compose_file == compose_file

    @patch("secondbrain.utils.docker_manager.config")
    def test_is_local_qdrant_true(self, mock_config):
        """Test _is_local_qdrant returns True for localhost URLs."""
        mock_config.return_value.qdrant_url = _test_config.qdrant_url
        manager = DockerManager()
        assert manager._is_local_qdrant() is True

    @patch("secondbrain.utils.docker_manager.config")
    def test_is_local_qdrant_false(self, mock_config):
        """Test _is_local_qdrant returns False for remote URLs."""
        mock_config.return_value.qdrant_url = "https://qdrant.example.com"
        manager = DockerManager()
        assert manager._is_local_qdrant() is False

    @patch("secondbrain.utils.docker_manager.config")
    def test_is_local_qdrant_127_0_0_1(self, mock_config):
        """Test _is_local_qdrant returns True for 127.0.0.1."""
        mock_config.return_value.qdrant_url = _test_config.qdrant_url
        manager = DockerManager()
        assert manager._is_local_qdrant() is True

    def test_is_local_qdrant_static_method(self):
        """Test static method is_local_qdrant_url."""
        assert DockerManager.is_local_qdrant_url(_test_config.qdrant_url) is True
        assert (
            DockerManager.is_local_qdrant_url("https://qdrant.example.com") is False
        )


class TestDockerInstallationChecks:
    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_docker_installed_true(self, mock_run):
        """Test check_docker_installed returns True when Docker is available."""
        mock_run.return_value = MagicMock(returncode=0)
        manager = DockerManager()
        assert manager.check_docker_installed() is True

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_docker_installed_false(self, mock_run):
        """Test check_docker_installed returns False when Docker is not available."""
        mock_run.side_effect = FileNotFoundError()
        manager = DockerManager()
        assert manager.check_docker_installed() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_docker_compose_installed_true(self, mock_run):
        """Test check_docker_compose_installed returns True when compose is available."""
        mock_run.return_value = MagicMock(returncode=0)
        with patch.object(
            manager := DockerManager(), "check_docker_installed", return_value=True
        ):
            assert manager.check_docker_compose_installed() is True

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_docker_compose_installed_false(self, mock_run):
        """Test check_docker_compose_installed returns False when compose fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker compose")
        with patch.object(
            manager := DockerManager(), "check_docker_installed", return_value=True
        ):
            assert manager.check_docker_compose_installed() is False


class TestCheckQdrantRunning:
    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_qdrant_running_true(self, mock_run):
        """Test check_qdrant_running returns True when container is running."""
        mock_run.return_value = MagicMock(stdout="secondbrain-qdrant\n", returncode=0)
        manager = DockerManager()
        assert manager.check_qdrant_running() is True

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_qdrant_running_false(self, mock_run):
        """Test check_qdrant_running returns False when container not running."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        manager = DockerManager()
        assert manager.check_qdrant_running() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_qdrant_running_docker_not_installed(self, mock_run):
        """Test check_qdrant_running returns False when Docker not installed."""
        mock_run.side_effect = FileNotFoundError()
        manager = DockerManager()
        assert manager.check_qdrant_running() is False


class TestStartQdrant:
    def test_start_qdrant_docker_not_installed(self, tmp_path):
        """Test start_qdrant raises DockerNotInstalledError when Docker unavailable."""
        # Create a valid compose file to avoid file not found errors
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )
        manager = DockerManager(compose_file=str(compose_file))
        with (
            patch.object(manager, "check_docker_installed", return_value=False),
            pytest.raises(DockerNotInstalledError),
        ):
            manager.start_qdrant()

    def test_start_qdrant_compose_not_installed(self, tmp_path):
        """Test start_qdrant raises DockerComposeError when compose unavailable."""
        # Create a valid compose file to avoid file not found errors
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )
        manager = DockerManager(compose_file=str(compose_file))
        with (
            patch.object(manager, "check_docker_installed", return_value=True),
            patch.object(manager, "check_docker_compose_installed", return_value=False),
            pytest.raises(DockerComposeError),
        ):
            manager.start_qdrant()

    def test_start_qdrant_compose_file_not_found(self, tmp_path):
        manager = DockerManager(compose_file=str(tmp_path / "nonexistent.yml"))
        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                with pytest.raises(DockerComposeError):
                    manager.start_qdrant()

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_start_qdrant_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Started")
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )
        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                with patch.object(manager, "check_qdrant_running", return_value=True):
                    manager.start_qdrant()


class TestWaitForQdrantReady:
    @patch("secondbrain.utils.docker_manager.config")
    def test_wait_for_qdrant_ready_skips_remote(self, mock_config):
        mock_config.return_value.qdrant_url = "https://qdrant.example.com"
        manager = DockerManager()
        manager.wait_for_qdrant_ready(max_wait_seconds=1)

    def test_wait_for_qdrant_ready_success(self):
        from unittest.mock import patch

        with patch("secondbrain.utils.docker_manager.config") as mock_config_func:
            with patch("secondbrain.storage.factory.StorageFactory.create_from_config") as mock_storage_class:
                from secondbrain.config import Config

                _test_config = Config()
                mock_config_func.return_value.qdrant_url = _test_config.qdrant_url
                mock_storage = MagicMock()
                mock_storage.validate_connection.return_value = True
                mock_storage._wait_for_index_ready.return_value = None
                mock_storage_class.return_value = mock_storage

                manager = DockerManager()
                manager.wait_for_qdrant_ready(max_wait_seconds=5, check_interval=0.1)

    def test_wait_for_qdrant_ready_timeout(self):
        from unittest.mock import patch

        with patch("secondbrain.utils.docker_manager.config") as mock_config_func:
            with patch("secondbrain.storage.factory.StorageFactory.create_from_config") as mock_storage_class:
                from secondbrain.config import Config

                _test_config = Config()
                mock_config_func.return_value.qdrant_url = _test_config.qdrant_url
                mock_storage = MagicMock()
                mock_storage.validate_connection.return_value = False
                mock_storage_class.return_value = mock_storage

                manager = DockerManager()
                with pytest.raises(QdrantStartupError):
                    manager.wait_for_qdrant_ready(max_wait_seconds=1, check_interval=0.1)


class TestEnsureQdrantRunning:
    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_skips_remote(self, mock_config):
        mock_config.return_value.qdrant_url = "https://qdrant.example.com"
        manager = DockerManager()
        manager.ensure_qdrant_running(verbose=False)

    def test_ensure_qdrant_running_already_running(self):
        with patch.object(
            manager := DockerManager(), "check_qdrant_running", return_value=True
        ):
            manager.ensure_qdrant_running(verbose=False)

    def test_ensure_qdrant_running_docker_not_installed(self, tmp_path):
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )
        manager = DockerManager(compose_file=str(compose_file))
        with (
            patch.object(manager, "_is_local_qdrant", return_value=True),
            patch.object(manager, "check_qdrant_running", return_value=False),
            patch.object(manager, "check_docker_installed", return_value=False),
            pytest.raises(DockerNotInstalledError),
        ):
            manager.ensure_qdrant_running(verbose=False)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_full_flow(self, mock_config):
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        manager = DockerManager()
        with patch.object(manager, "check_qdrant_running") as mock_check:
            with patch.object(manager, "start_qdrant") as mock_start:
                with patch.object(manager, "wait_for_qdrant_ready") as mock_wait:
                    mock_check.return_value = False
                    manager.ensure_qdrant_running(verbose=False)
                    mock_start.assert_called_once()
                    mock_wait.assert_called_once()


class TestDockerManagerCoverage:
    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_docker_compose_installed_returns_false_when_docker_not_installed(
        self, mock_run
    ):
        """Test check_docker_compose_installed returns False when Docker not installed (line 147)."""
        mock_run.side_effect = FileNotFoundError()
        manager = DockerManager()
        assert manager.check_docker_compose_installed() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_qdrant_running_handles_timeout_expired(self, mock_run):
        """Test check_qdrant_running handles subprocess.TimeoutExpired (lines 196-204)."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker ps", timeout=10)
        manager = DockerManager()
        assert manager.check_qdrant_running() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_qdrant_running_handles_called_process_error(self, mock_run):
        """Test check_qdrant_running handles CalledProcessError (lines 196-204)."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "docker ps")
        manager = DockerManager()
        assert manager.check_qdrant_running() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_start_qdrant_handles_compose_failure(self, mock_run, tmp_path):
        """Test start_qdrant handles docker compose failure (lines 263-264)."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                mock_run.side_effect = [
                    MagicMock(returncode=1, stderr="Compose failed", stdout=""),
                ]
                with pytest.raises(DockerComposeError) as exc_info:
                    manager.start_qdrant()
                assert "Compose failed" in str(exc_info.value)

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_start_qdrant_handles_container_not_running_after_start(
        self, mock_run, tmp_path
    ):
        """Test start_qdrant raises QdrantStartupError when container not running (lines 270-276)."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                with patch.object(manager, "check_qdrant_running", return_value=False):
                    with pytest.raises(QdrantStartupError) as exc_info:
                        manager.start_qdrant()
                    assert "not running" in str(exc_info.value)

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_start_qdrant_handles_timeout_expired(self, mock_run, tmp_path):
        """Test start_qdrant handles subprocess.TimeoutExpired (lines 275-279)."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                mock_run.side_effect = subprocess.TimeoutExpired(
                    cmd="docker compose", timeout=120
                )
                with pytest.raises(QdrantStartupError) as exc_info:
                    manager.start_qdrant()
                assert "Timeout" in str(exc_info.value)

    @patch("secondbrain.utils.docker_manager.config")
    def test_wait_for_qdrant_ready_handles_index_not_ready(self, mock_config):
        """Test wait_for_qdrant_ready handles index not ready exception (lines 326-329)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        with patch("secondbrain.storage.factory.StorageFactory.create_from_config") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.validate_connection.return_value = True
            mock_storage._wait_for_index_ready.side_effect = Exception(
                "Index not ready"
            )
            mock_storage_class.return_value = mock_storage

            manager = DockerManager()
            with pytest.raises(QdrantStartupError):
                manager.wait_for_qdrant_ready(max_wait_seconds=1, check_interval=0.1)

    @patch("secondbrain.utils.docker_manager.config")
    def test_wait_for_qdrant_ready_handles_generic_exception(self, mock_config):
        """Test wait_for_qdrant_ready handles generic exception (lines 333-335)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        with patch("secondbrain.storage.factory.StorageFactory.create_from_config") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage.validate_connection.side_effect = Exception("Connection error")
            mock_storage_class.return_value = mock_storage

            manager = DockerManager()
            with pytest.raises(QdrantStartupError):
                manager.wait_for_qdrant_ready(max_wait_seconds=1, check_interval=0.1)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_verbose_remote(self, mock_config, capsys):
        """Test ensure_qdrant_running verbose output for remote Qdrant (line 371)."""
        mock_config.return_value.qdrant_url = "https://qdrant.example.com"
        manager = DockerManager()
        manager.ensure_qdrant_running(verbose=True)
        captured = capsys.readouterr()
        assert "remote Qdrant" in captured.out

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_verbose_already_running(self, mock_config):
        """Test ensure_qdrant_running verbose output when already running (line 380)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        with patch.object(
            manager := DockerManager(), "check_qdrant_running", return_value=True
        ):
            manager.ensure_qdrant_running(verbose=True)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_verbose_starting(self, mock_config):
        """Test ensure_qdrant_running verbose output when starting (line 397)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        with patch.object(
            manager := DockerManager(), "check_qdrant_running", return_value=False
        ):
            with patch.object(manager, "check_docker_installed", return_value=False):
                with pytest.raises(DockerNotInstalledError):
                    manager.ensure_qdrant_running(verbose=True)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_verbose_waiting(self, mock_config, tmp_path):
        """Test ensure_qdrant_running verbose output when waiting (line 414)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_qdrant_running", return_value=False):
            with patch.object(manager, "check_docker_installed", return_value=True):
                with patch.object(
                    manager, "check_docker_compose_installed", return_value=True
                ):
                    with patch.object(manager, "start_qdrant", return_value=None):
                        with patch.object(
                            manager, "wait_for_qdrant_ready", return_value=None
                        ):
                            manager.ensure_qdrant_running(verbose=True)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_verbose_ready(self, mock_config, tmp_path):
        """Test ensure_qdrant_running verbose output when ready (line 419)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_qdrant_running", return_value=False):
            with patch.object(manager, "check_docker_installed", return_value=True):
                with patch.object(
                    manager, "check_docker_compose_installed", return_value=True
                ):
                    with patch.object(manager, "start_qdrant", return_value=None):
                        with patch.object(
                            manager, "wait_for_qdrant_ready", return_value=None
                        ):
                            manager.ensure_qdrant_running(verbose=True)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_handles_compose_error(self, mock_config, tmp_path):
        """Test ensure_qdrant_running handles DockerComposeError (lines 401-402)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_qdrant_running", return_value=False):
            with patch.object(manager, "check_docker_installed", return_value=True):
                with patch.object(
                    manager, "check_docker_compose_installed", return_value=True
                ):
                    with patch.object(
                        manager,
                        "start_qdrant",
                        side_effect=DockerComposeError("Compose failed"),
                    ):
                        with pytest.raises(DockerComposeError) as exc_info:
                            manager.ensure_qdrant_running(verbose=False)
                        assert "Failed to start Qdrant" in str(exc_info.value)

    @patch("secondbrain.utils.docker_manager.config")
    def test_ensure_qdrant_running_handles_startup_error(self, mock_config, tmp_path):
        """Test ensure_qdrant_running handles QdrantStartupError (lines 420-421)."""
        from secondbrain.config import Config

        _test_config = Config()
        mock_config.return_value.qdrant_url = _test_config.qdrant_url

        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text(
            "services:\n  qdrant:\n    image: qdrant/qdrant:latest\n"
        )

        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_qdrant_running", return_value=False):
            with patch.object(manager, "check_docker_installed", return_value=True):
                with patch.object(
                    manager, "check_docker_compose_installed", return_value=True
                ):
                    with patch.object(manager, "start_qdrant", return_value=None):
                        with patch.object(
                            manager,
                            "wait_for_qdrant_ready",
                            side_effect=QdrantStartupError("Startup failed"),
                        ):
                            with pytest.raises(QdrantStartupError) as exc_info:
                                manager.ensure_qdrant_running(verbose=False)
                            assert "failed to become ready" in str(exc_info.value)


class TestConvenienceFunctions:
    @patch("secondbrain.utils.docker_manager.DockerManager")
    def test_check_qdrant_running_convenience(self, mock_manager_class):
        """Test check_qdrant_running convenience function."""
        mock_manager = MagicMock()
        mock_manager.check_qdrant_running.return_value = True
        mock_manager_class.return_value = mock_manager

        from secondbrain.utils.docker_manager import check_qdrant_running

        assert check_qdrant_running() is True

    @patch("secondbrain.utils.docker_manager.DockerManager")
    def test_ensure_qdrant_running_convenience(self, mock_manager_class):
        """Test ensure_qdrant_running convenience function."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        from secondbrain.utils.docker_manager import ensure_qdrant_running

        ensure_qdrant_running(verbose=False)
        mock_manager.ensure_qdrant_running.assert_called_once_with(verbose=False)
