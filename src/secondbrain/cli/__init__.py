"""CLI module for secondbrain.

This module provides the main CLI entry point and exports all commands.
Commands are now organized in separate modules:
- errors.py: Error handling decorators
- display.py: Display/output formatting functions
- commands.py: All CLI command implementations
"""

import click
from rich.console import Console

from secondbrain.logging import setup_logging

console = Console(markup=True)


def _ensure_mongodb(
    ctx: click.Context, _param: click.Parameter | None, _value: bool
) -> None:
    if ctx.invoked_subcommand is None or ctx.invoked_subcommand == "help":
        return

    try:
        from secondbrain.utils.docker_manager import DockerManager

        verbose = ctx.obj.get("verbose", False)
        DockerManager().ensure_mongo_running(verbose=verbose)
    except Exception as e:
        ctx.obj.setdefault("mongo_auto_start_failed", True)
        ctx.obj.setdefault("mongo_auto_start_error", str(e))


@click.group()
@click.option(
    "--verbose", "-v", is_flag=True, help="Enable verbose output", is_eager=True
)
@click.version_option(version="0.4.0", prog_name="secondbrain")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """SecondBrain - A local document intelligence CLI tool.

    Ingests documents, generates embeddings using sentence-transformers, and stores
    vectors in MongoDB for semantic search.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose=verbose)

    _ensure_mongodb(ctx, None, False)


# Import and register commands after cli group is defined
# This ensures commands are properly decorated and registered
from . import commands  # noqa: E402


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
