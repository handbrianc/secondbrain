#!/usr/bin/env python3
"""Advanced custom chunking example.

Demonstrates how to configure custom chunk sizes and overlap for
different document types.

Usage:
    python custom_chunking.py /path/to/docs --chunk-size 2048 --overlap 100
"""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from secondbrain.document import DocumentIngestor
from secondbrain.logging import setup_logging

console = Console()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Ingest documents with custom chunking parameters"
    )
    parser.add_argument("path", type=str, help="Path to document or directory")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2048,
        help="Chunk size in tokens (default: 2048)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=100,
        help="Chunk overlap in tokens (default: 100)",
    )
    parser.add_argument(
        "--recursive", "-r", action="store_true", help="Process subdirectories"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser.parse_args()


def main() -> None:
    """Run main entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    path = Path(args.path)
    if not path.exists():
        console.print(f"[red]Error: Path not found: {path}[/red]")
        sys.exit(1)

    console.print("[blue]Custom chunking configuration:[/blue]")
    console.print(f"  Chunk size: {args.chunk_size} tokens")
    console.print(f"  Overlap: {args.overlap} tokens")
    console.print(f"  Path: {path}\n")

    # Create ingestor with custom chunking
    ingestor = DocumentIngestor(
        chunk_size=args.chunk_size,
        chunk_overlap=args.overlap,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Processing...", total=None)

        try:
            result = ingestor.ingest(
                str(path),
                recursive=args.recursive,
                batch_size=5,
            )
            console.print("[green]✓ Ingestion complete[/green]")
            console.print(f"  Success: {result['success']}, Failed: {result['failed']}")
        except (OSError, RuntimeError, ValueError) as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)


if __name__ == "__main__":
    main()
