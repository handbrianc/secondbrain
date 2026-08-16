"""Docker Compose start/stop commands."""

import sys
from pathlib import Path

import click
from rich.console import Console

from secondbrain.exceptions import CLIValidationError
from secondbrain.utils.docker_manager import (
    DockerComposeError,
    DockerNotInstalledError,
)

from . import cli
from .errors import handle_cli_errors

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.option(
    "--compose-file",
    "-f",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose.yml (default: auto-detect in project root)",
)
@click.option(
    "--project-name",
    "-p",
    type=str,
    default="secondbrain",
    help="Docker Compose project name (default: secondbrain)",
)
@click.option(
    "--wait",
    "-w",
    is_flag=True,
    help="Wait for services to be fully ready before returning",
)
@click.pass_context
def start(
    ctx: click.Context,
    compose_file: str | None,
    project_name: str,
    wait: bool,
) -> None:
    """Start the production Docker Compose stack.

    Starts MongoDB and other services defined in docker-compose.yml.
    By default, starts only MongoDB service.

    Examples:
    --------
        secondbrain start                    # Start with auto-detected compose file
        secondbrain start -f docker-compose.prod.yml  # Use specific compose file
        secondbrain start --wait             # Wait for services to be fully ready
    --------
    """
    from secondbrain.utils.docker_manager import DockerManager

    if compose_file is None:
        possible_paths = [
            Path.cwd() / "docker-compose.yml",
            Path.cwd() / "docker-compose.prod.yml",
            Path(__file__).parent.parent.parent.parent / "docker-compose.yml",
        ]
        for path in possible_paths:
            if path.exists():
                compose_file = str(path)
                break

        if compose_file is None:
            raise CLIValidationError(
                "No docker-compose.yml found. Please specify --compose-file "
                "or place docker-compose.yml in the current directory or project root."
            )

    console.print(f"[cyan]Starting Docker Compose stack from: {compose_file}[/cyan]")

    try:
        manager = DockerManager(compose_file=compose_file, project_name=project_name)

        if not manager.check_docker_installed():
            raise DockerNotInstalledError(
                "[red]✗ Docker is not installed or not in PATH[/red]\n\n"
                "Please install Docker Desktop (macOS/Windows) or Docker Engine (Linux):\n"
                "  - https://docs.docker.com/get-docker/"
            )

        if not manager.check_docker_compose_installed():
            raise DockerComposeError(
                "[red]✗ docker compose (v2) is not installed[/red]\n\n"
                "Please install Docker Compose plugin:\n"
                "  - https://docs.docker.com/compose/install/"
            )

        console.print("[cyan]Starting MongoDB...[/cyan]")
        manager.start_mongo()

        if wait:
            console.print("[cyan]Waiting for services to be ready...[/cyan]")
            manager.wait_for_mongo_ready()
            console.print("[green]✓ Docker Compose stack is fully ready[/green]")
        else:
            console.print("[green]✓ Docker Compose stack started successfully[/green]")
            console.print(
                "[dim]Use --wait to wait for services to be fully ready[/dim]"
            )

    except DockerNotInstalledError as e:
        console.print(str(e))
        sys.exit(1)
    except DockerComposeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


@handle_cli_errors
@cli.command()
@click.option(
    "--compose-file",
    "-f",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose.yml (default: auto-detect in project root)",
)
@click.option(
    "--project-name",
    "-p",
    type=str,
    default="secondbrain",
    help="Docker Compose project name (default: secondbrain)",
)
@click.option(
    "--remove-volumes",
    "-v",
    is_flag=True,
    help="Remove named volumes as well",
)
@click.option(
    "--force",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.pass_context
def stop(
    ctx: click.Context,
    compose_file: str | None,
    project_name: str,
    remove_volumes: bool,
    force: bool,
) -> None:
    """Stop the production Docker Compose stack.

    Stops and removes containers created by docker compose up.

    Examples:
    --------
        secondbrain stop                       # Stop with auto-detected compose file
        secondbrain stop -f docker-compose.prod.yml  # Use specific compose file
        secondbrain stop --remove-volumes      # Also remove volumes
        secondbrain stop --force               # Skip confirmation
    --------
    """
    import subprocess

    if compose_file is None:
        possible_paths = [
            Path.cwd() / "docker-compose.yml",
            Path.cwd() / "docker-compose.prod.yml",
            Path(__file__).parent.parent.parent.parent / "docker-compose.yml",
        ]
        for path in possible_paths:
            if path.exists():
                compose_file = str(path)
                break

        if compose_file is None:
            raise CLIValidationError(
                "No docker-compose.yml found. Please specify --compose-file "
                "or place docker-compose.yml in the current directory or project root."
            )

    if not force:
        action = "remove volumes" if remove_volumes else "stop containers"
        if not click.confirm(
            f"Stop Docker Compose stack and {action}? This will stop all services."
        ):
            console.print("Cancelled.")
            return

    console.print(f"[cyan]Stopping Docker Compose stack from: {compose_file}[/cyan]")

    if (
        subprocess.run(
            ["docker", "--version"], capture_output=True, check=False
        ).returncode
        != 0
    ):
        console.print(
            "[red]✗ Docker is not installed or not in PATH[/red]\n"
            "Please install Docker to use this feature."
        )
        sys.exit(1)

    try:
        cmd = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "-p",
            project_name,
            "down",
        ]

        if remove_volumes:
            cmd.append("-v")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise DockerComposeError(
                f"Failed to stop Docker Compose stack: {error_msg}"
            )

        console.print("[green]✓ Docker Compose stack stopped successfully[/green]")

        if remove_volumes:
            console.print("[dim]Named volumes have been removed[/dim]")

    except subprocess.TimeoutExpired:
        console.print(
            "[red]Error: Timeout while stopping Docker Compose stack[/red]\n"
            "Please check running containers with: docker ps"
        )
        sys.exit(1)
    except DockerComposeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
