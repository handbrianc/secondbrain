"""Docker Compose management utilities for automatic MongoDB startup.

This module provides utilities for:
- Checking if MongoDB container is running via Docker
- Starting MongoDB via docker compose up -d
- Waiting for MongoDB to be fully ready (connection + vector index)
- Graceful error handling for Docker not installed, compose failures, etc.

Usage:
    from secondbrain.utils.docker_manager import DockerManager

    manager = DockerManager()
    if not manager.check_mongo_running():
        manager.start_mongo()
        manager.wait_for_mongo_ready()
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from secondbrain.config import get_config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)
console = Console()


class DockerNotInstalledError(Exception):
    """Raised when Docker is not installed or not in PATH."""

    pass


class DockerComposeError(Exception):
    """Raised when docker compose command fails."""

    pass


class MongoDBStartupError(Exception):
    """Raised when MongoDB fails to start or become ready."""

    pass


class DockerManager:
    """Manages Docker Compose operations for MongoDB.

    This class provides methods to:
    - Check if MongoDB container is running
    - Start MongoDB via docker compose
    - Wait for MongoDB to be fully ready
    - Handle errors gracefully

    Attributes:
        compose_file: Path to docker-compose.yml file
        container_name: Name of MongoDB container
        project_name: Docker Compose project name
    """

    def __init__(
        self,
        compose_file: str | None = None,
        project_name: str = "secondbrain",
    ) -> None:
        """Initialize Docker manager.

        Args:
            compose_file: Path to docker-compose.yml. If None, uses default location.
            project_name: Docker Compose project name (default: "secondbrain").
        """
        config = get_config()
        self.mongo_uri: str = config.mongo_uri
        self.compose_file: Path = (
            Path(compose_file)
            if compose_file
            else Path(__file__).parent.parent.parent.parent / "docker-compose.yml"
        )
        self.project_name: str = project_name
        self.container_name: str = "secondbrain-mongodb"

    def _is_local_mongodb(self) -> bool:
        """Check if MongoDB URI is for local MongoDB (not Atlas).

        Returns
        -------
            True if URI points to localhost or local IP, False otherwise.

        Examples:
            >>> manager = DockerManager()
            >>> manager.mongo_uri = "mongodb://localhost:27017"
            >>> manager._is_local_mongodb()
            True
            >>> manager.mongo_uri = "mongodb+srv://cluster0.mongodb.net"
            >>> manager._is_local_mongodb()
            False
        """
        # Check for localhost variations
        local_hosts = ["localhost", "127.0.0.1", "::1"]
        return any(host in self.mongo_uri for host in local_hosts)

    def _docker_command_available(self, command: str = "docker") -> bool:
        """Check if a Docker command is available.

        Args:
            command: Docker command to check (default: "docker").

        Returns
        -------
            True if command is available, False otherwise.
        """
        try:
            subprocess.run(
                [command, "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )  # nosec B603, B607 - safe: checking Docker availability, no user input in command
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False

    def check_docker_installed(self) -> bool:
        """Check if Docker is installed and available.

        Returns
        -------
            True if Docker is installed, False otherwise.
        """
        return self._docker_command_available("docker")

    def check_docker_compose_installed(self) -> bool:
        """Check if docker compose (v2) is installed.

        Returns
        -------
            True if docker compose is available, False otherwise.
        """
        if not self.check_docker_installed():
            return False

        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                check=True,
                timeout=5,
            )  # nosec B603, B607 - safe: hardcoded docker command, no user input
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False

    def check_mongo_running(self) -> bool:
        """Check if MongoDB container is running via docker ps.

        Returns
        -------
            True if MongoDB container is running, False otherwise.

        Examples:
            >>> manager = DockerManager()
            >>> manager.check_mongo_running()
            True
        """
        if not self.check_docker_installed():
            logger.debug("Docker not installed, MongoDB cannot be running via Docker")
            return False

        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "--filter",
                    f"name={self.container_name}",
                    "--format",
                    "{{.Names}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )  # nosec B603, B607 - safe: hardcoded docker ps, container_name from validated config
            running_containers = result.stdout.strip().split("\n")
            return self.container_name in running_containers
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as e:
            logger.debug(
                "Error checking MongoDB container status: %s: %s", type(e).__name__, e
            )
            return False

    def start_mongo(self) -> None:
        """Start MongoDB via docker compose up -d.

        Runs docker compose up -d to start the MongoDB container in detached mode.

        Raises:
            DockerNotInstalledError: If Docker is not installed.
            DockerComposeError: If docker compose command fails.
            MongoDBStartupError: If MongoDB fails to start.

        Examples:
            >>> manager = DockerManager()
            >>> manager.start_mongo()
            # MongoDB container started in background
        """
        if not self.check_docker_installed():
            raise DockerNotInstalledError(
                "Docker is not installed or not in PATH. "
                "Please install Docker Desktop or Docker Engine to use local MongoDB. "
                "See: https://docs.docker.com/get-docker/"
            )

        if not self.check_docker_compose_installed():
            raise DockerComposeError(
                "docker compose (v2) is not installed. "
                "Please install Docker Compose plugin. "
                "See: https://docs.docker.com/compose/install/"
            )

        if not self.compose_file.exists():
            raise DockerComposeError(
                f"docker-compose.yml not found at {self.compose_file}. "
                "Please ensure docker-compose.yml exists in your project root."
            )

        logger.info("Starting MongoDB via docker compose...")

        try:
            # Run docker compose up -d
            result = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self.compose_file),
                    "-p",
                    self.project_name,
                    "up",
                    "-d",
                    "mongodb",
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout for compose up
            )  # nosec B603, B607 - safe: docker compose with validated compose_file path from config

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise DockerComposeError(f"Failed to start MongoDB: {error_msg}")

            logger.info("MongoDB container started successfully")

            # Verify container is actually running
            if not self.check_mongo_running():
                raise MongoDBStartupError(
                    "MongoDB container started but is not running. "
                    "Check logs with: docker logs secondbrain-mongodb"
                )

        except subprocess.TimeoutExpired as e:
            raise MongoDBStartupError(
                "Timeout waiting for docker compose to start MongoDB. "
                "Please check Docker is running and try again."
            ) from e

    def wait_for_mongo_ready(
        self,
        max_wait_seconds: int = 60,
        check_interval: float = 2.0,
    ) -> None:
        """Wait for MongoDB to be fully ready (connection + vector index).

        This method blocks until MongoDB accepts connections and the vector
        search index is ready. Uses the storage layer's index readiness check.

        Args:
            max_wait_seconds: Maximum time to wait for MongoDB to be ready.
            check_interval: Time between connection checks in seconds.

        Raises:
            MongoDBStartupError: If MongoDB doesn't become ready within timeout.

        Examples:
            >>> manager = DockerManager()
            >>> manager.wait_for_mongo_ready()
            # MongoDB is now ready for use
        """
        if not self._is_local_mongodb():
            logger.debug("Not waiting for local MongoDB (Atlas or remote URI)")
            return

        logger.info("Waiting for MongoDB to be ready...")

        start_time = time.time()
        last_error: str | None = None

        # Import here to avoid circular dependency
        from secondbrain.storage import VectorStorage

        storage = VectorStorage()

        while time.time() - start_time < max_wait_seconds:
            try:
                # First check if we can connect
                if storage.validate_connection():
                    # Connection works, now wait for index
                    try:
                        storage._wait_for_index_ready()
                        logger.info("MongoDB is ready for use")
                        return
                    except Exception as index_err:
                        # Index not ready yet, continue waiting
                        last_error = f"Index not ready: {index_err}"
                        logger.debug("Waiting for index: %s", index_err)
                else:
                    last_error = "Connection failed"

            except Exception as e:
                last_error = str(e)
                logger.debug("MongoDB not ready yet: %s", e)

            time.sleep(check_interval)

        # Timeout reached
        raise MongoDBStartupError(
            f"MongoDB failed to become ready within {max_wait_seconds} seconds. "
            f"Last error: {last_error}. "
            "Check Docker logs: docker logs secondbrain-mongodb"
        )

    def ensure_mongo_running(
        self,
        verbose: bool = False,
    ) -> None:
        """Ensure MongoDB is running, start it if necessary.

        This is the main entry point for auto-starting MongoDB. It checks if
        MongoDB is running, and if not, starts it automatically via Docker.

        Args:
            verbose: If True, print status messages to user.

        Raises:
            DockerNotInstalledError: If Docker is not installed and MongoDB not running.
            DockerComposeError: If docker compose fails.
            MongoDBStartupError: If MongoDB fails to start or become ready.

        Examples:
            >>> manager = DockerManager()
            >>> manager.ensure_mongo_running()
            # MongoDB is now running and ready
        """
        # Skip auto-start for non-local MongoDB
        if not self._is_local_mongodb():
            if verbose:
                print(
                    "[yellow]Note: Using remote MongoDB (Atlas or other). "
                    "Auto-start disabled.[/yellow]"
                )
            return

        # Check if already running
        if self.check_mongo_running():
            if verbose:
                console.print("[green]✓ MongoDB is already running[/green]")
            return

        # Docker not installed check
        if not self.check_docker_installed():
            raise DockerNotInstalledError(
                "[red]✗ Docker is not installed or not in PATH[/red]\n\n"
                "To use local MongoDB, please install Docker:\n"
                "  - macOS: https://docs.docker.com/docker-for-mac/install/\n"
                "  - Windows: https://docs.docker.com/docker-for-windows/install/\n"
                "  - Linux: https://docs.docker.com/engine/install/\n\n"
                "Alternatively, configure SECONDBRAIN_MONGO_URI to use "
                "a remote MongoDB instance."
            )

        # Try to start MongoDB
        if verbose:
            console.print("[cyan]Starting MongoDB via Docker...[/cyan]")

        try:
            self.start_mongo()
        except DockerComposeError as e:
            raise DockerComposeError(
                f"[red]✗ Failed to start MongoDB[/red]\n\n"
                f"Error: {e}\n\n"
                "Please ensure:\n"
                "  1. Docker is running\n"
                "  2. docker-compose.yml exists in project root\n"
                "  3. Port 27017 is not in use\n"
                "  4. You have permission to run Docker commands"
            ) from e

        # Wait for MongoDB to be ready
        if verbose:
            print("[cyan]Waiting for MongoDB to be ready...[/cyan]")

        try:
            self.wait_for_mongo_ready()
            if verbose:
                print("[green]✓ MongoDB is ready[/green]")
        except MongoDBStartupError as e:
            raise MongoDBStartupError(
                f"[red]✗ MongoDB failed to become ready[/red]\n\n"
                f"Error: {e}\n\n"
                "Please check Docker logs:\n"
                "  docker logs secondbrain-mongodb"
            ) from e

    @staticmethod
    def is_local_mongodb_uri(uri: str) -> bool:
        """Check if MongoDB URI is local."""
        local_hosts = ["localhost", "127.0.0.1", "::1"]
        return any(host in uri for host in local_hosts)


# Convenience functions for simple use cases
def ensure_mongo_running(
    verbose: bool = True,
    compose_file: str | None = None,
) -> None:
    """Ensure MongoDB is running, start it if necessary.

    Convenience wrapper around DockerManager.ensure_mongo_running().

    Args:
        verbose: If True, print status messages.
        compose_file: Optional path to docker-compose.yml.

    Raises:
        DockerNotInstalledError: If Docker not installed.
        MongoDBStartupError: If MongoDB fails to start.
    """
    manager = DockerManager(compose_file=compose_file)
    manager.ensure_mongo_running(verbose=verbose)


def check_mongo_running() -> bool:
    """Check if MongoDB container is running.

    Returns
    -------
        True if MongoDB is running, False otherwise.
    """
    manager = DockerManager()
    return manager.check_mongo_running()
