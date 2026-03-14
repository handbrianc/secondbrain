"""CLI error handling module."""

import logging
import sys
from collections.abc import Callable
from functools import wraps
from typing import TypeVar, cast

import click
from rich.console import Console
from typing_extensions import ParamSpec

from secondbrain.exceptions import CLIValidationError

console = Console()
logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def handle_cli_errors(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to handle CLI errors gracefully.

    Catches specific exceptions, displays user-friendly error messages,
    logs full traceback for debugging, and exits with status 1.

    Args:
        func: Function to decorate.

    Returns:
        Wrapped function with error handling.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except click.BadParameter as e:
            logger.warning(f"Parameter validation error: {e}", exc_info=True)
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Run with --verbose for full traceback[/yellow]")
            sys.exit(1)
        except (ValueError, FileNotFoundError, CLIValidationError) as e:
            logger.warning(f"Validation error: {e}", exc_info=True)
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Run with --verbose for full traceback[/yellow]")
            sys.exit(1)
        except Exception as e:
            logger.exception("Unexpected error in CLI command")
            console.print(f"[red]Error: {e}[/red]")
            console.print("[yellow]Run with --verbose for full traceback[/yellow]")
            sys.exit(1)

    return wrapper
