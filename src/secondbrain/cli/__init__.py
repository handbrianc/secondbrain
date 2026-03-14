"""CLI module for secondbrain.

This module provides the main CLI entry point and exports all commands.
Commands are now organized in separate modules:
- errors.py: Error handling decorators
- display.py: Display/output formatting functions
- commands.py: All CLI command implementations
"""

import click
from secondbrain.logging import setup_logging


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """SecondBrain - A local document intelligence CLI tool.

    Ingests documents, generates embeddings using Ollama, and stores
    vectors in MongoDB for semantic search.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose=verbose)


# Import and register commands after cli group is defined
# This ensures commands are properly decorated and registered
from . import commands  # noqa: F401 (import for side effects - command registration)


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
