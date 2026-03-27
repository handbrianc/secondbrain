"""MCP ingest tool implementation."""

import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

logger = logging.getLogger(__name__)
console = Console()


async def handle_ingest(arguments: dict[str, Any]) -> str:
    """Handle ingest tool call.

    Args:
        arguments: Tool arguments with path, recursive, chunk_size, etc.

    Returns:
        Result message with ingestion statistics.
    """
    from secondbrain.config import get_config
    from secondbrain.document import DocumentIngestor, is_supported

    path = arguments.get("path")
    if not path:
        return "Error: path is required"

    try:
        config = get_config()
        chunk_size = arguments.get("chunk_size", config.chunk_size)
        chunk_overlap = arguments.get("chunk_overlap", config.chunk_overlap)
        recursive = arguments.get("recursive", False)
        cores = arguments.get("cores")
        batch_size = arguments.get("batch_size", 10)

        # Collect files to show progress
        path_obj = Path(path)
        if path_obj.is_file():
            files = [path_obj]
        else:
            files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
            files = [f for f in files if f.is_file() and is_supported(f)]

        total_files = len(files)

        # Handle edge case: no files to process
        if total_files == 0:
            return "No supported files found. Ingestion complete: 0 files succeeded, 0 files failed"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("[progress.completed]{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Ingesting...", total=total_files)

            # Create progress callback that updates the progress bar
            def progress_callback(file_path: Path, success: bool) -> None:
                status = "[green]✓[/green]" if success else "[red]✗[/red]"
                progress.update(
                    task, description=f"[cyan]Ingesting... {status} {file_path.name}"
                )
                progress.advance(task, 1)
                progress.refresh()

            ingestor = DocumentIngestor(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                verbose=False,
                progress_callback=progress_callback,
            )

            results = ingestor.ingest(
                path,
                recursive=recursive,
                batch_size=batch_size,
                cores=cores,
                progress_callback=progress_callback,
            )

        success_count = results.get("success", 0)
        fail_count = results.get("failed", 0)

        return (
            f"Ingestion complete: {success_count} files succeeded, "
            f"{fail_count} files failed"
        )
    except Exception as e:
        logger.exception(f"Ingest failed: {e}")
        return f"Error: {e!s}"
