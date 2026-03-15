#!/usr/bin/env python3
"""Advanced batch ingestion example.

Demonstrates parallel processing of large directories with
progress tracking and error handling.

Usage:
    python batch_ingestion.py /path/to/docs --batch-size 10 --max-workers 4
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from secondbrain.document import DocumentIngestor
from secondbrain.logging import setup_logging

console = Console()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch ingest documents with parallel processing"
    )
    parser.add_argument("path", type=str, help="Directory to process")
    parser.add_argument("--batch-size", type=int, default=10, help="Files per batch")
    parser.add_argument("--max-workers", type=int, default=4, help="Parallel workers")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args()


def process_file(
    ingestor: DocumentIngestor, filepath: Path
) -> tuple[Path, int, str | None]:
    """Process a single file."""
    try:
        result = ingestor.ingest(str(filepath))
        return filepath, result["success"], None
    except (OSError, RuntimeError) as e:
        return filepath, 0, str(e)


def main() -> None:
    """Run main entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    path = Path(args.path)
    if not path.is_dir():
        console.print(f"[red]Error: Not a directory: {path}[/red]")
        sys.exit(1)

    # Collect files
    files = list(path.glob("**/*"))
    files = [f for f in files if f.is_file() and not f.name.startswith(".")]

    if not files:
        console.print("[yellow]No files found.[/yellow]")
        return

    console.print(f"[blue]Found {len(files)} files to process[/blue]")
    console.print(f"  Batch size: {args.batch_size}")
    console.print(f"  Workers: {args.max_workers}\n")

    ingestor = DocumentIngestor()
    total_chunks = 0
    failures = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing batches...", total=len(files))

        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(process_file, ingestor, f): f for f in files}

            for future in as_completed(futures):
                filepath, chunks, error = future.result()
                total_chunks += chunks

                if error:
                    failures.append((filepath, error))
                else:
                    console.print(f"  ✓ {filepath.name}: {chunks} chunks")

                progress.update(task, advance=1)

    console.print(
        f"\n[green]✓ Complete: {total_chunks} chunks from {len(files)} files[/green]"
    )

    if failures:
        console.print(f"\n[yellow]⚠ {len(failures)} failures:[/yellow]")
        for fp, err in failures[:5]:
            console.print(f"  - {fp.name}: {err}")


if __name__ == "__main__":
    main()
