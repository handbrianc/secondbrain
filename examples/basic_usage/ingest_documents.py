#!/usr/bin/env python3
"""Basic document ingestion example.

This script demonstrates how to ingest documents into SecondBrain
using the DocumentIngestor API directly.

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


def parse_args():
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


def main():
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
    ) as _:
        try:
            if path.is_file():
                # Single file ingestion
                result = ingestor.ingest_file(str(path))
                console.print(f"[green]✓ Ingested: {path.name}[/green]")
                console.print(f"  Created {result.created_chunks} chunks")
            else:
                # Directory ingestion
                results = ingestor.ingest_directory(
                    str(path),
                    recursive=args.recursive,
                    batch_size=args.batch_size,
                )

                total_chunks = sum(r.created_chunks for r in results)
                total_files = len(results)

                console.print(f"[green]✓ Ingested {total_files} files[/green]")
                console.print(f"  Total chunks created: {total_chunks}")

                # Show any failures
                failures = [r for r in results if r.error]
                if failures:
                    console.print(f"[yellow]⚠ {len(failures)} files failed:[/yellow]")
                    for result in failures[:5]:  # Show first 5 failures
                        console.print(f"  - {result.source}: {result.error}")

        except Exception as e:
            console.print(f"[red]Error during ingestion: {e}[/red]")
            sys.exit(1)

    console.print(
        "\n[blue]Ingestion complete! Use 'secondbrain search' to query documents.[/blue]"
    )


if __name__ == "__main__":
    main()
