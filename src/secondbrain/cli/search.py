"""Search, list, and delete commands."""

import sys
from typing import Any

import click
from rich.console import Console

from secondbrain.config import config
from secondbrain.constants import MAX_LIST_LIMIT
from secondbrain.exceptions import (
    CLIValidationError,
    ServiceUnavailableError,
    StorageConnectionError,
)
from secondbrain.storage import ChunkInfo

from . import cli
from .display import display_list_results, display_search_results
from .errors import handle_cli_errors

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.argument("query")
@click.option("--top-k", type=int, help="Number of results to return")
@click.option(
    "--source",
    type=str,
    help="Filter results by source file path (e.g., '/path/to/document.pdf')",
)
@click.option(
    "--file-type",
    type=str,
    help="Filter results by file type (e.g., 'pdf', 'docx', 'markdown')",
)
@click.option(
    "--format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--min-score",
    type=float,
    default=None,
    help="Minimum similarity score threshold (0.0-1.0, default: 0.46)",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    top_k: int | None,
    source: str | None,
    file_type: str | None,
    format: str,
    min_score: float | None,
) -> None:
    """Search the vector database with semantic query.

    QUERY: Search query text.
    """
    from secondbrain.constants import DEFAULT_MIN_SIMILARITY_THRESHOLD
    from secondbrain.search import Searcher

    cfg = config()
    top_k = top_k or cfg.default_top_k
    effective_min_score = (
        min_score if min_score is not None else DEFAULT_MIN_SIMILARITY_THRESHOLD
    )

    with (
        console.status("[cyan]Searching...", spinner="dots"),
        Searcher(verbose=ctx.obj.get("verbose", False)) as searcher,
    ):
        results: list[dict[str, Any]] = searcher.search(
            query=query,
            top_k=top_k,
            source_filter=source,
            file_type_filter=file_type,
        )
    display_search_results(results, format, min_score=effective_min_score)


@handle_cli_errors
@cli.command()
@click.option("--source", type=str, help="Filter by source file")
@click.option("--chunk-id", type=str, help="Filter by specific chunk ID")
@click.option("--limit", type=int, default=100, help="Maximum number of results")
@click.option("--offset", type=int, default=0, help="Offset for pagination")
@click.option("--all", "-a", is_flag=True, help="List all documents (ignores limit)")
@click.pass_context
def ls(
    ctx: click.Context,
    source: str | None,
    chunk_id: str | None,
    limit: int,
    offset: int,
    all: bool,
) -> None:
    """List ingested documents and chunks."""
    from secondbrain.management import Lister

    if limit < 0:
        raise CLIValidationError("Limit must be non-negative")
    if limit > MAX_LIST_LIMIT:
        click.echo(
            f"Warning: Limit {limit} exceeds maximum {MAX_LIST_LIMIT}, "
            f"clamping to {MAX_LIST_LIMIT}",
            err=True,
        )
        limit = MAX_LIST_LIMIT

    if offset < 0:
        raise CLIValidationError("Offset must be non-negative")

    with (
        console.status("[cyan]Loading...", spinner="dots"),
        Lister(verbose=ctx.obj.get("verbose", False)) as lister,
    ):
        if all:
            limit = MAX_LIST_LIMIT
        results: list[ChunkInfo] = lister.list_chunks(
            source_filter=source,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )
    display_list_results(results)


@handle_cli_errors
@cli.command()
@click.option("--source", type=str, help="Filter by source file")
@click.option("--chunk-id", type=str, help="Filter by specific chunk ID")
@click.option("--all", "-a", is_flag=True, help="Delete all documents")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete(
    ctx: click.Context,
    source: str | None,
    chunk_id: str | None,
    all: bool,
    yes: bool,
) -> None:
    """Delete documents from the vector database."""
    from secondbrain.management import Deleter

    if not any([source, chunk_id, all]):
        console.print("[red]Error: Must specify --source, --chunk-id, or --all[/red]")
        sys.exit(1)

    if sum([bool(source), bool(chunk_id), all]) > 1:
        console.print(
            "[red]Error: Specify only one of --source, --chunk-id, or --all[/red]"
        )
        sys.exit(1)

    if not yes:
        if all:
            if not click.confirm("Delete all documents? This cannot be undone."):
                console.print("Cancelled.")
                return
        else:
            if not click.confirm("Delete documents matching criteria?"):
                console.print("Cancelled.")
                return

    with (
        console.status("[cyan]Deleting...", spinner="dots"),
        Deleter(verbose=ctx.obj.get("verbose", False)) as deleter,
    ):
        try:
            count = deleter.delete(source=source, chunk_id=chunk_id, all=all)
            console.print(f"[green]Deleted {count} document(s)[/green]")
        except (
            ServiceUnavailableError,
            StorageConnectionError,
            CLIValidationError,
        ) as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
