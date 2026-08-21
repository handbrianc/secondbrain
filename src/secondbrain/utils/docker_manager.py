"""Docker Compose management utilities for automatic Qdrant startup.

This module provides utilities for:
- Checking if Qdrant container is running via Docker
- Starting Qdrant via docker compose up -d
- Waiting for Qdrant to be fully ready (connection + vector index)
- Graceful error handling for Docker not installed, compose failures, etc.

Usage:
    from secondbrain.utils.docker_manager import DockerManager

    manager = DockerManager()
    if not manager.check_qdrant_running():
        manager.start_qdrant()
        manager.wait_for_qdrant_ready()
"""

import logging
import subprocess
import time
from pathlib import Path

from rich.console import Console

from secondbrain.config import config

logger = logging.getLogger(__name__)
console = Console()


class DockerNotInstalledError(Exception):
    """Raised when Docker is not installed or not in PATH."""

    pass


class DockerComposeError(Exception):
    """Raised when docker compose command fails."""

    pass


class QdrantStartupError(Exception):
    """Raised when Qdrant fails to start or become ready."""

    pass


class DockerManager:
    """Manages Docker Compose operations for Qdrant.

    This class provides methods to:
    - Check if Qdrant container is running
    - Start Qdrant via docker compose
    - Wait for Qdrant to be fully ready
    - Handle errors gracefully

    Attributes:
        compose_file: Path to docker-compose.yml file
        container_name: Name of Qdrant container
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
        cfg = config()
        self.qdrant_url: str = cfg.qdrant_url
        self.compose_file: Path = (
            Path(compose_file)
            if compose_file
            else Path(__file__).parent.parent.parent.parent / "docker-compose.yml"
        )
        self.project_name: str = project_name
        self.container_name: str = "secondbrain-qdrant"

    def _is_local_qdrant(self) -> bool:
        """Check if Qdrant URL is for a local server (not remote).

        Returns
        -------
            True if URL points to localhost or local IP, False otherwise.

        Examples:
            >>> manager = DockerManager()
            >>> manager.qdrant_url = os.getenv("SECONDBRAIN_QDRANT_URL", "")
            >>> manager._is_local_qdrant()
            True
            >>> manager.qdrant_url = "https://cluster.qdrant.io"
            >>> manager._is_local_qdrant()
            False
        """
        # Check for localhost variations
        local_hosts = ["localhost", "127.0.0.1", "::1"]
        return any(host in self.qdrant_url for host in local_hosts)

    def _docker_command_available(self, command: str = "docker") -> bool:
        """Check if a Docker command is available.

        Args:
            command: Docker command to check (default: "docker").

        Returns
        -------
            True if command is available, False otherwise.
        """
        try:
            subprocess.run(  # nosec B603
                [command, "--version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
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
            subprocess.run(  # nosec B603
                ["docker", "compose", "version"],
                capture_output=True,
                check=True,
                timeout=5,
            )
            return True
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return False

    def check_qdrant_running(self) -> bool:
        """Check if Qdrant container is running via docker ps.

        Returns
        -------
            True if Qdrant container is running, False otherwise.

        Examples:
            >>> manager = DockerManager()
            >>> manager.check_qdrant_running()
            True
        """
        if not self.check_docker_installed():
            logger.debug("Docker not installed, Qdrant cannot be running via Docker")
            return False

        try:
            result = subprocess.run(  # nosec B603
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
            )
            running_containers = result.stdout.strip().split("\n")
            return self.container_name in running_containers
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ) as e:
            logger.debug(
                "Error checking Qdrant container status: %s: %s", type(e).__name__, e
            )
            return False

    def start_qdrant(self) -> None:
        """Start Qdrant via docker compose up -d.

        Runs docker compose up -d to start the Qdrant container in detached mode.

        Raises:
            DockerNotInstalledError: If Docker is not installed.
            DockerComposeError: If docker compose command fails.
            QdrantStartupError: If Qdrant fails to start.

        Examples:
            >>> manager = DockerManager()
            >>> manager.start_qdrant()
            # Qdrant container started in background
        """
        if not self.check_docker_installed():
            raise DockerNotInstalledError(
                "Docker is not installed or not in PATH. "
                "Please install Docker Desktop or Docker Engine to use local Qdrant. "
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

        logger.info("Starting Qdrant via docker compose...")

        try:
            result = subprocess.run(  # nosec B603
                [
                    "docker",
                    "compose",
                    "-f",
                    str(self.compose_file),
                    "-p",
                    self.project_name,
                    "up",
                    "-d",
                    "qdrant",
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout for compose up
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise DockerComposeError(f"Failed to start Qdrant: {error_msg}")

            logger.info("Qdrant container started successfully")

            if not self.check_qdrant_running():
                raise QdrantStartupError(
                    "Qdrant container started but is not running. "
                    "Check logs with: docker logs secondbrain-qdrant"
                )

        except subprocess.TimeoutExpired as e:
            raise QdrantStartupError(
                "Timeout waiting for docker compose to start Qdrant. "
                "Please check Docker is running and try again."
            ) from e

    def wait_for_qdrant_ready(
        self,
        max_wait_seconds: int = 60,
        check_interval: float = 2.0,
    ) -> None:
        """Wait for Qdrant to be fully ready (connection + vector index).

        This method blocks until Qdrant accepts connections and the vector
        search index is ready. Uses the storage layer's index readiness check.

        Args:
            max_wait_seconds: Maximum time to wait for Qdrant to be ready.
            check_interval: Time between connection checks in seconds.

        Raises:
            QdrantStartupError: If Qdrant doesn't become ready within timeout.

        Examples:
            >>> manager = DockerManager()
            >>> manager.wait_for_qdrant_ready()
            # Qdrant is now ready for use
        """
        if not self._is_local_qdrant():
            logger.debug("Not waiting for local Qdrant (remote URL)")
            return

        logger.info("Waiting for Qdrant to be ready...")

        start_time = time.time()
        last_error: str | None = None

        # Import here to avoid circular dependency
        from secondbrain.storage import StorageFactory

        storage = StorageFactory.create_from_config()

        while time.time() - start_time < max_wait_seconds:
            try:
                # First check if we can connect
                if storage.validate_connection():
                    try:
                        wait_index = getattr(
                            storage, "_wait_for_index_ready", None
                        )
                        if callable(wait_index):
                            wait_index()
                        logger.info("Qdrant is ready for use")
                        return
                    except Exception as index_err:
                        # Index not ready yet, continue waiting
                        last_error = f"Index not ready: {index_err}"
                        logger.debug("Waiting for index: %s", index_err)
                else:
                    last_error = "Connection failed"

            except Exception as e:
                last_error = str(e)
                logger.debug("Qdrant not ready yet: %s", e)

            time.sleep(check_interval)

        # Timeout reached
        raise QdrantStartupError(
            f"Qdrant failed to become ready within {max_wait_seconds} seconds. "
            f"Last error: {last_error}. "
            "Check Docker logs: docker logs secondbrain-qdrant"
        )

    def ensure_qdrant_running(
        self,
        verbose: bool = False,
    ) -> None:
        """Ensure Qdrant is running, start it if necessary.

        This is the main entry point for auto-starting Qdrant. It checks if
        Qdrant is running, and if not, starts it automatically via Docker.

        Args:
            verbose: If True, print status messages to user.

        Raises:
            DockerNotInstalledError: If Docker is not installed and Qdrant not running.
            DockerComposeError: If docker compose fails.
            QdrantStartupError: If Qdrant fails to start or become ready.

        Examples:
            >>> manager = DockerManager()
            >>> manager.ensure_qdrant_running()
            # Qdrant is now running and ready
        """
        if not self._is_local_qdrant():
            if verbose:
                print(
                    "[yellow]Note: Using remote Qdrant server. "
                    "Auto-start disabled.[/yellow]"
                )
            return

        if self.check_qdrant_running():
            if verbose:
                console.print("[green]✓ Qdrant is already running[/green]")
            return

        if not self.check_docker_installed():
            raise DockerNotInstalledError(
                "[red]✗ Docker is not installed or not in PATH[/red]\n\n"
                "To use local Qdrant, please install Docker:\n"
                "  - macOS: https://docs.docker.com/docker-for-mac/install/\n"
                "  - Windows: https://docs.docker.com/docker-for-windows/install/\n"
                "  - Linux: https://docs.docker.com/engine/install/\n\n"
                "Alternatively, configure SECONDBRAIN_QDRANT_URL to use "
                "a remote Qdrant server."
            )

        if verbose:
            console.print("[cyan]Starting Qdrant via Docker...[/cyan]")

        try:
            self.start_qdrant()
        except DockerComposeError as e:
            raise DockerComposeError(
                f"[red]✗ Failed to start Qdrant[/red]\n\n"
                f"Error: {e}\n\n"
                "Please ensure:\n"
                "  1. Docker is running\n"
                "  2. docker-compose.yml exists in project root\n"
                "  3. Qdrant port (from SECONDBRAIN_QDRANT_URL) is not in use\n"
                "  4. You have permission to run Docker commands"
            ) from e

        if verbose:
            console.print("[cyan]Waiting for Qdrant to be ready...[/cyan]")

        try:
            self.wait_for_qdrant_ready()
            if verbose:
                console.print("[green]✓ Qdrant is ready[/green]")
        except QdrantStartupError as e:
            raise QdrantStartupError(
                f"[red]✗ Qdrant failed to become ready[/red]\n\n"
                f"Error: {e}\n\n"
                "Please check Docker logs:\n"
                "  docker logs secondbrain-qdrant"
            ) from e

    @staticmethod
    def is_local_qdrant_url(uri: str) -> bool:
        """Check if Qdrant URL is local."""
        local_hosts = ["localhost", "127.0.0.1", "::1"]
        return any(host in uri for host in local_hosts)


# Convenience functions for simple use cases
def ensure_qdrant_running(
    verbose: bool = True,
    compose_file: str | None = None,
) -> None:
    """Ensure Qdrant is running, start it if necessary.

    Convenience wrapper around DockerManager.ensure_qdrant_running().

    Args:
        verbose: If True, print status messages.
        compose_file: Optional path to docker-compose.yml.

    Raises:
        DockerNotInstalledError: If Docker not installed.
        QdrantStartupError: If Qdrant fails to start.
    """
    manager = DockerManager(compose_file=compose_file)
    manager.ensure_qdrant_running(verbose=verbose)


def check_qdrant_running() -> bool:
    """Check if Qdrant container is running.

    Returns
    -------
        True if Qdrant is running, False otherwise.
    """
    manager = DockerManager()
    return manager.check_qdrant_running()
