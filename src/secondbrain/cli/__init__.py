"""CLI module for secondbrain."""

import json
import logging
import sys
import traceback
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, TypeVar, cast

import click
from rich.console import Console
from rich.table import Table

from secondbrain.config import get_config
from secondbrain.exceptions import CLIValidationError
from secondbrain.logging import HealthStatus, get_health_status, setup_logging
from secondbrain.storage import ChunkInfo, DatabaseStats

console = Console()
logger = logging.getLogger(__name__)

MAX_LIST_LIMIT = 100000


T = TypeVar("T", bound=Callable[..., Any])


def handle_cli_errors(func: T) -> T:
    """Decorator to handle CLI errors gracefully.

    Catches specific exceptions, displays user-friendly error messages,
    logs full traceback for debugging, and exits with status 1.

    Args:
        func: Function to decorate.

    Returns:
        Wrapped function with error handling.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
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

    return wrapper  # type: ignore[return-value]


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


@cli.command()
@handle_cli_errors
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    help="Recursively process all files in subdirectories",
)
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=10,
    help="Number of files to process in parallel",
)
@click.option(
    "--chunk-size",
    type=int,
    default=None,
    help="Override chunk size for text splitting",
)
@click.option(
    "--chunk-overlap",
    type=int,
    default=None,
    help="Override chunk overlap for text splitting",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    path: str,
    recursive: bool,
    batch_size: int,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> None:
    """Ingest documents into the vector database.

    PATH: Path to file or directory to ingest.
    """
    from secondbrain.document import DocumentIngestor

    config = get_config()
    chunk_size = chunk_size or config.chunk_size
    chunk_overlap = chunk_overlap or config.chunk_overlap

    ingestor = DocumentIngestor(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        verbose=ctx.obj.get("verbose", False),
    )

    console.print(f"[bold]Ingesting: {path}[/bold]")
    results = ingestor.ingest(path, recursive=recursive, batch_size=batch_size)
    console.print(f"[green]Successfully ingested {results['success']} files[/green]")
    if results["failed"] > 0:
        console.print(f"[yellow]Failed: {results['failed']} files[/yellow]")


@cli.command()
@handle_cli_errors
@click.argument("query", type=str)
@click.option(
    "--top-k",
    "-k",
    type=int,
    default=None,
    help="Number of results to return",
)
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Filter by source file",
)
@click.option(
    "--file-type",
    "-t",
    type=str,
    default=None,
    help="Filter by file type",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["default", "verbose", "json"]),
    default="default",
    help="Output format",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    top_k: int | None,
    source: str | None,
    file_type: str | None,
    format: str,
) -> None:
    """Search the vector database with semantic query.

    QUERY: Search query text.
    """
    from secondbrain.search import Searcher

    config = get_config()
    top_k = top_k or config.default_top_k

    with Searcher(verbose=ctx.obj.get("verbose", False)) as searcher:
        results = searcher.search(
            query=query,
            top_k=top_k,
            source_filter=source,
            file_type_filter=file_type,
        )
    _display_search_results(results, format)


def _display_search_results(results: list[dict[str, Any]], format: str) -> None:
    """Display search results in the specified format.

    Args:
        results: List of search results to display.
        format: Output format: 'default', 'verbose', or 'json'.
    """
    import json

    if format == "json":
        console.print(json.dumps(results, indent=2))
        return

    for i, result in enumerate(results, 1):
        chunk_preview = result.get("chunk_text", "")[:100]
        page_num = result.get("page_number", "N/A")
        if format == "verbose":
            console.print(f"\n[bold]Result {i}[/bold]")
            console.print(f"  Source: {result.get('source_file', 'N/A')}")
            console.print(f"  Page: {page_num}")
            console.print(f"  Score: {result.get('score', 0):.4f}")
            console.print(f"  Text: {result.get('chunk_text', '')[:200]}...")
        else:
            console.print(
                f"{i}. {result.get('source_file', 'N/A')} "
                f"(page {page_num}, score: {result.get('score', 0):.4f}) "
                f"- {chunk_preview}..."
            )


@cli.command()
@handle_cli_errors
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Filter by source file",
)
@click.option(
    "--chunk-id",
    "-c",
    type=str,
    default=None,
    help="Filter by chunk ID",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=50,
    help="Maximum number of results to return",
)
@click.option(
    "--offset",
    "-o",
    type=int,
    default=0,
    help="Offset for pagination",
)
@click.option(
    "--all",
    "-a",
    is_flag=True,
    help="Show all results without pagination",
)
@click.pass_context
def list_cmd(
    ctx: click.Context,
    source: str | None,
    chunk_id: str | None,
    limit: int,
    offset: int,
    all: bool = False,
) -> None:
    """List ingested documents/chunks."""
    from secondbrain.management import Lister

    with Lister(verbose=ctx.obj.get("verbose", False)) as lister:
        lister = cast(Lister, lister)
        if all:
            limit = MAX_LIST_LIMIT
        results: list[ChunkInfo] = lister.list_chunks(
            source_filter=source,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )
    _display_list_results(results)


def _display_list_results(results: Sequence[ChunkInfo]) -> None:
    """Display list results in table format.

    Args:
        results: Sequence of ChunkInfo objects to display.
    """
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    table = Table(title="Ingested Documents")
    table.add_column("Chunk ID", style="cyan", no_wrap=True)
    table.add_column("Source File", style="magenta")
    table.add_column("Page", justify="right")

    for chunk_info in results:
        table.add_row(
            chunk_info["chunk_id"][:8] + "...",
            chunk_info["source_file"],
            str(chunk_info["page_number"]) if chunk_info["page_number"] else "N/A",
        )

    console.print(table)


@cli.command()
@click.option(
    "--source",
    "-s",
    type=str,
    default=None,
    help="Delete by source file",
)
@click.option(
    "--chunk-id",
    "-c",
    type=str,
    default=None,
    help="Delete by chunk ID",
)
@click.option(
    "--all",
    "-a",
    is_flag=True,
    help="Delete all documents",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
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

    # Validate options
    if not any([source, chunk_id, all]):
        console.print("[red]Error: Must specify --source, --chunk-id, or --all[/red]")
        sys.exit(1)

    if sum([bool(source), bool(chunk_id), all]) > 1:
        console.print(
            "[red]Error: Specify only one of --source, --chunk-id, or --all[/red]"
        )
        sys.exit(1)

    # Get confirmation
    if not yes:
        if all:
            if not click.confirm("Delete all documents? This cannot be undone."):
                console.print("Cancelled.")
                return
        else:
            if not click.confirm("Delete documents matching criteria?"):
                console.print("Cancelled.")
                return

    with Deleter(verbose=ctx.obj.get("verbose", False)) as deleter:
        deleter = cast(Deleter, deleter)
        try:
            count = deleter.delete(source=source, chunk_id=chunk_id, all=all)
            console.print(f"[green]Deleted {count} document(s)[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)


@cli.command()
@handle_cli_errors
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show statistics about the vector database."""
    from secondbrain.management import StatusChecker

    with StatusChecker(verbose=ctx.obj.get("verbose", False)) as status_checker:
        status_checker = cast(StatusChecker, status_checker)
        stats = status_checker.get_status()
    _display_status(stats)


def _display_status(stats: DatabaseStats) -> None:
    """Display database status statistics.

    Args:
        stats: DatabaseStats dictionary with chunk and collection info.
    """
    console.print("[bold]Database Status[/bold]")
    console.print(f"  Total chunks: {stats['total_chunks']}")
    console.print(f"  Unique sources: {stats['unique_sources']}")
    console.print(f"  Database: {stats['database']}")
    console.print(f"  Collection: {stats['collection']}")


@cli.command()
@handle_cli_errors
@click.option("--output", "-o", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def health(ctx: click.Context, output: str) -> None:
    """Check health status of all services."""

    health_status = get_health_status()
    if output == "json":
        console.print(json.dumps(health_status, indent=2))
    else:
        _display_health_text(health_status)


def _display_health_text(status: HealthStatus) -> None:
    """Display health status in text format.

    Args:
        status: HealthStatus dictionary with service availability and timing.
    """
    status_color = "green" if status["status"] == "healthy" else "yellow"
    console.print(
        f"[bold {status_color}]Health Status: {status['status'].upper()}[/bold {status_color}]"
    )
    console.print(f"  Timestamp: {status['timestamp']}")
    console.print(f"  Check Duration: {status['check_duration_seconds']:.3f}s")
    console.print("\n[bold]Services:[/bold]")
    for service, available in status["services"].items():
        icon = "[green]✓[/green]" if available else "[red]✗[/red]"
        console.print(f"  {icon} {service}")


def main() -> None:
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
