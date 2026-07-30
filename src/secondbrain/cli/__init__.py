"""CLI module for secondbrain.

This module provides the main CLI entry point and exports all commands.
Commands are now, in separate modules:
- errors.py: Error handling decorators
- display.py: Display/output formatting functions
- commands.py: All CLI command implementations
"""

import click
from rich.console import Console

from secondbrain.logging import setup_logging
from secondbrain.utils.mps_patch import patch_transformers_for_mps

# Apply RT-DETR float32 patch at the earliest possible point — before any
# docling/transformers import that might trigger the RT-DETR layout model.
patch_transformers_for_mps()

console = Console(markup=True)


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


# This ensures commands are properly decorated and registered
from . import commands  # noqa: E402


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
