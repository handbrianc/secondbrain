import subprocess
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.utils.docker_manager import (
    DockerComposeError,
    DockerManager,
    DockerNotInstalledError,
    MongoDBStartupError,
)


class TestDockerManagerBasic:
    def test_init_default_values(self):
        """Test DockerManager initializes with default values."""
        manager = DockerManager()
        assert manager.project_name == "secondbrain"
        assert manager.container_name == "secondbrain-mongodb"
        assert manager.compose_file.exists()

    def test_init_custom_compose_file(self, tmp_path):
        """Test DockerManager with custom compose file."""
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("services:\n")
        manager = DockerManager(compose_file=str(compose_file))
        assert manager.compose_file == compose_file

    @patch("secondbrain.utils.docker_manager.get_config")
    def test_is_local_mongodb_true(self, mock_get_config):
        """Test _is_local_mongodb returns True for localhost URIs."""
        mock_get_config.return_value.mongo_uri = "mongodb://localhost:27017"
        manager = DockerManager()
        assert manager._is_local_mongodb() is True

    @patch("secondbrain.utils.docker_manager.get_config")
    def test_is_local_mongodb_false(self, mock_get_config):
        """Test _is_local_mongodb returns False for Atlas URIs."""
        mock_get_config.return_value.mongo_uri = (
            "mongodb+srv://cluster0.mongodb.net/secondbrain"
        )
        manager = DockerManager()
        assert manager._is_local_mongodb() is False

    @patch("secondbrain.utils.docker_manager.get_config")
    def test_is_local_mongodb_127_0_0_1(self, mock_get_config):
        """Test _is_local_mongodb returns True for 127.0.0.1."""
        mock_get_config.return_value.mongo_uri = "mongodb://127.0.0.1:27017"
        manager = DockerManager()
        assert manager._is_local_mongodb() is True

    def test_is_local_mongodb_static_method(self):
        """Test static method is_local_mongodb_uri."""
        assert DockerManager.is_local_mongodb_uri("mongodb://localhost:27017") is True
        assert (
            DockerManager.is_local_mongodb_uri("mongodb+srv://cluster.mongodb.net")
            is False
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


class TestCheckMongoRunning:
    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_mongo_running_true(self, mock_run):
        """Test check_mongo_running returns True when container is running."""
        mock_run.return_value = MagicMock(stdout="secondbrain-mongodb\n", returncode=0)
        manager = DockerManager()
        assert manager.check_mongo_running() is True

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_mongo_running_false(self, mock_run):
        """Test check_mongo_running returns False when container not running."""
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        manager = DockerManager()
        assert manager.check_mongo_running() is False

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_check_mongo_running_docker_not_installed(self, mock_run):
        """Test check_mongo_running returns False when Docker not installed."""
        mock_run.side_effect = FileNotFoundError()
        manager = DockerManager()
        assert manager.check_mongo_running() is False


class TestStartMongo:
    def test_start_mongo_docker_not_installed(self):
        """Test start_mongo raises DockerNotInstalledError when Docker unavailable."""
        with (
            patch.object(
                manager := DockerManager(), "check_docker_installed", return_value=False
            ),
            pytest.raises(DockerNotInstalledError),
        ):
            manager.start_mongo()

    def test_start_mongo_compose_not_installed(self):
        """Test start_mongo raises DockerComposeError when compose unavailable."""
        with (
            patch.object(
                manager := DockerManager(), "check_docker_installed", return_value=True
            ),
            patch.object(manager, "check_docker_compose_installed", return_value=False),
            pytest.raises(DockerComposeError),
        ):
            manager.start_mongo()

    def test_start_mongo_compose_file_not_found(self, tmp_path):
        manager = DockerManager(compose_file=str(tmp_path / "nonexistent.yml"))
        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                with pytest.raises(DockerComposeError):
                    manager.start_mongo()

    @patch("secondbrain.utils.docker_manager.subprocess.run")
    def test_start_mongo_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Started")
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("services:\n")
        manager = DockerManager(compose_file=str(compose_file))
        with patch.object(manager, "check_docker_installed", return_value=True):
            with patch.object(
                manager, "check_docker_compose_installed", return_value=True
            ):
                with patch.object(manager, "check_mongo_running", return_value=True):
                    manager.start_mongo()


class TestWaitForMongoReady:
    @patch("secondbrain.utils.docker_manager.get_config")
    def test_wait_for_mongo_ready_skips_remote(self, mock_get_config):
        mock_get_config.return_value.mongo_uri = "mongodb+srv://cluster.mongodb.net"
        manager = DockerManager()
        manager.wait_for_mongo_ready(max_wait_seconds=1)

    def test_wait_for_mongo_ready_success(self):
        from unittest.mock import patch

        with patch("secondbrain.utils.docker_manager.get_config") as mock_get_config:
            with patch("secondbrain.storage.VectorStorage") as mock_storage_class:
                mock_get_config.return_value.mongo_uri = "mongodb://localhost:27017"
                mock_storage = MagicMock()
                mock_storage.validate_connection.return_value = True
                mock_storage._wait_for_index_ready.return_value = None
                mock_storage_class.return_value = mock_storage

                manager = DockerManager()
                manager.wait_for_mongo_ready(max_wait_seconds=5, check_interval=0.1)

    def test_wait_for_mongo_ready_timeout(self):
        from unittest.mock import patch

        with patch("secondbrain.utils.docker_manager.get_config") as mock_get_config:
            with patch("secondbrain.storage.VectorStorage") as mock_storage_class:
                mock_get_config.return_value.mongo_uri = "mongodb://localhost:27017"
                mock_storage = MagicMock()
                mock_storage.validate_connection.return_value = False
                mock_storage_class.return_value = mock_storage

                manager = DockerManager()
                with pytest.raises(MongoDBStartupError):
                    manager.wait_for_mongo_ready(max_wait_seconds=1, check_interval=0.1)


class TestEnsureMongoRunning:
    @patch("secondbrain.utils.docker_manager.get_config")
    def test_ensure_mongo_running_skips_remote(self, mock_get_config):
        mock_get_config.return_value.mongo_uri = "mongodb+srv://cluster.mongodb.net"
        manager = DockerManager()
        manager.ensure_mongo_running(verbose=False)

    def test_ensure_mongo_running_already_running(self):
        with patch.object(
            manager := DockerManager(), "check_mongo_running", return_value=True
        ):
            manager.ensure_mongo_running(verbose=False)

    def test_ensure_mongo_running_docker_not_installed(self):
        with (
            patch.object(
                manager := DockerManager(), "check_mongo_running", return_value=False
            ),
            patch.object(manager, "check_docker_installed", return_value=False),
        ):
            with pytest.raises(DockerNotInstalledError):
                manager.ensure_mongo_running(verbose=False)

    @patch("secondbrain.utils.docker_manager.get_config")
    def test_ensure_mongo_running_full_flow(self, mock_get_config):
        mock_get_config.return_value.mongo_uri = "mongodb://localhost:27017"

        manager = DockerManager()
        with patch.object(manager, "check_mongo_running") as mock_check:
            with patch.object(manager, "start_mongo") as mock_start:
                with patch.object(manager, "wait_for_mongo_ready") as mock_wait:
                    with patch.object(
                        manager, "check_docker_installed", return_value=True
                    ):
                        with patch.object(
                            manager, "check_docker_compose_installed", return_value=True
                        ):
                            compose_file = MagicMock()
                            compose_file.exists.return_value = True
                            manager.compose_file = compose_file
                            mock_check.side_effect = [False, True]
                            manager.ensure_mongo_running(verbose=False)
                            mock_start.assert_called_once()
                            mock_wait.assert_called_once()


class TestConvenienceFunctions:
    @patch("secondbrain.utils.docker_manager.DockerManager")
    def test_check_mongo_running_convenience(self, mock_manager_class):
        """Test check_mongo_running convenience function."""
        mock_manager = MagicMock()
        mock_manager.check_mongo_running.return_value = True
        mock_manager_class.return_value = mock_manager

        from secondbrain.utils.docker_manager import check_mongo_running

        assert check_mongo_running() is True

    @patch("secondbrain.utils.docker_manager.DockerManager")
    def test_ensure_mongo_running_convenience(self, mock_manager_class):
        """Test ensure_mongo_running convenience function."""
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager

        from secondbrain.utils.docker_manager import ensure_mongo_running

        ensure_mongo_running(verbose=False)
        mock_manager.ensure_mongo_running.assert_called_once_with(verbose=False)
