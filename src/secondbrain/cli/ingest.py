"""Ingest command."""

import os
from pathlib import Path

import click
from rich.console import Console

from secondbrain.config import config
from secondbrain.exceptions import CLIValidationError

from . import cli
from .errors import handle_cli_errors
from .ingest_progress import IngestProgressUI

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True, help="Recursively process directories")
@click.option(
    "--batch-size",
    "-b",
    type=click.IntRange(min=1),
    default=30,
    help="Batch size for ThreadPoolExecutor (used when cores=1)",
)
@click.option("--chunk-size", type=int, help="Override default chunk size")
@click.option("--chunk-overlap", type=int, help="Override default chunk overlap")
@click.option(
    "--cores",
    "-c",
    type=int,
    help="Number of CPU cores to use for parallel processing (default: auto-detect)",
)
@click.option(
    "--pool",
    type=click.Choice(["process", "thread"]),
    default=None,
    help="Pool type for CPU-bound extraction: 'process' (multicore, default) or 'thread'",
)
@click.option(
    "--no-skip-existing",
    is_flag=True,
    default=False,
    help="Re-embed and re-store all chunks, ignoring chunks already present from a previous ingest",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output (show extraction errors and warnings)",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    path: str,
    recursive: bool,
    batch_size: int,
    chunk_size: int | None,
    chunk_overlap: int | None,
    cores: int | None,
    pool: str | None,
    no_skip_existing: bool,
    verbose: bool,
) -> None:
    """Ingest documents into the vector database.

    PATH: Path to file or directory to ingest.
    """
    from secondbrain.document import DocumentIngestor

    cfg = config()
    chunk_size = cfg.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = cfg.chunk_overlap if chunk_overlap is None else chunk_overlap
    pool = cfg.ingest_pool if pool is None else pool

    skip_existing = False if no_skip_existing else None

    if cores is not None:
        if cores <= 0:
            raise CLIValidationError("cores must be positive")
        available_cores = os.cpu_count() or 1
        if cores > available_cores:
            console.print(
                f"[yellow]Warning: Requested {cores} cores, but only {available_cores} available. Using {available_cores}.[/yellow]"
            )
            cores = available_cores

    # Global verbose flag can also be passed via ctx.obj (e.g. from parent command)
    if not verbose:
        verbose = ctx.obj.get("verbose", False)

    console.print(f"[bold]Ingesting: {path}[/bold]")

    from secondbrain.document import is_supported

    path_obj = Path(path)
    if path_obj.is_file():
        files = [path_obj]
    else:
        files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
        files = [f for f in files if f.is_file() and is_supported(f)]

    total_files = len(files)

    if total_files == 0:
        ingestor = DocumentIngestor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            verbose=verbose,
        )
        results = ingestor.ingest(
            path,
            recursive=recursive,
            batch_size=batch_size,
            cores=cores,
            pool=pool,
            skip_existing=skip_existing,
        )
    else:
        ui = IngestProgressUI(console, total_files, is_single=total_files == 1)
        with ui:
            ingestor = DocumentIngestor(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                verbose=verbose,
                progress_callback=ui.on_file_done,
                on_phase_progress=ui.on_phase,
            )
            results = ingestor.ingest(
                path,
                recursive=recursive,
                batch_size=batch_size,
                cores=cores,
                pool=pool,
                skip_existing=skip_existing,
            )
            ui.finish()

    num_success = results["success"]
    num_failed = results["failed"]
    console.print(f"[green]Successfully ingested {num_success} files[/green]")
    if isinstance(num_failed, int) and num_failed > 0:
        console.print(f"[yellow]Failed: {num_failed} files[/yellow]")
        failures = results.get("failures", [])
        for f in failures if isinstance(failures, list) else []:
            console.print(f"  [red]✗[/red] {f[0]}: {f[1]}")
