#!/usr/bin/env python3
"""Basic document listing example.

This script demonstrates how to list and inspect ingested documents
with pagination and filtering.

Usage:
    python list_documents.py [--limit 10] [--offset 0] [--filter-type pdf]
"""

import argparse
import sys

from rich.console import Console
from rich.table import Table

from secondbrain.logging import setup_logging
from secondbrain.storage import VectorStorage

console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="List ingested documents from SecondBrain"
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=10,
        help="Maximum number of results to show (default: 10)",
    )
    parser.add_argument(
        "--offset",
        "-o",
        type=int,
        default=0,
        help="Number of results to skip (default: 0)",
    )
    parser.add_argument(
        "--filter-type",
        type=str,
        help="Filter by file type (e.g., pdf, docx)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main():
    """Main entry point for listing documents."""
    args = parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    # Create storage
    storage = VectorStorage()

    try:
        # Get chunks
        chunks = storage.list_chunks(
            limit=args.limit,
            offset=args.offset,
            file_type_filter=args.filter_type,
        )

        if not chunks:
            console.print("[yellow]No documents found.[/yellow]")
            return

        # Display results in a table
        table = Table(title=f"Documents (showing {len(chunks)} of total)")
        table.add_column("Source", style="green")
        table.add_column("Page", justify="right")
        table.add_column("Type", style="cyan")
        table.add_column("Size", justify="right")

        for chunk in chunks:
            source = chunk.source_file
            page = chunk.page_number or "-"
            file_type = chunk.metadata.get("file_type", "-") if chunk.metadata else "-"
            size = len(chunk.chunk_text)

            table.add_row(source, str(page), file_type, f"{size} chars")

        console.print(table)

        # Show database stats
        stats = storage.get_stats()
        console.print("\n[blue]Database Statistics:[/blue]")
        console.print(f"  Total chunks: {stats['total_chunks']}")
        console.print(f"  Unique sources: {stats['unique_sources']}")

    except Exception as e:
        console.print(f"[red]Error listing documents: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
