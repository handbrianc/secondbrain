#!/usr/bin/env python3
"""Basic document ingestion example.

This script demonstrates how to ingest documents into SecondBrain

Usage:
    python ingest_documents.py /path/to/documents [--recursive]
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
        description="Ingest documents into SecondBrain vector database"
    )
    parser.add_argument(
        "path",
        type=str,
        help="Path to document file or directory",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recursively process all files in subdirectories",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=5,
        help="Number of files to process in parallel (default: 5)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for document ingestion."""
    args = parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    path = Path(args.path)
    if not path.exists():
        console.print(f"[red]Error: Path does not exist: {path}[/red]")
        sys.exit(1)

    console.print(f"[blue]Starting document ingestion from: {path}[/blue]")

    # Create ingestor
    ingestor = DocumentIngestor()

    # Process with progress bar
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Ingesting documents...", total=None)

        try:
            # Use ingest method (handles both files and directories)
            result = ingestor.ingest(
                str(path), recursive=args.recursive, batch_size=args.batch_size
            )

            if path.is_file():
                console.print(f"[green]✓ Ingested: {path.name}[/green]")
                console.print(f"  Created {result['success']} chunks")
            else:
                console.print(f"[green]✓ Ingested directory: {path}[/green]")
                console.print(
                    f"  Success: {result['success']}, Failed: {result['failed']}"
                )

        except Exception as e:
            console.print(f"[red]Error during ingestion: {e}[/red]")
            sys.exit(1)

    console.print(
        "\n[blue]Ingestion complete! Use 'secondbrain search' to query documents.[/blue]"
    )


if __name__ == "__main__":
    main()
