#!/usr/bin/env python3
"""Basic semantic search example.

This script demonstrates how to perform semantic searches using
the Searcher API with various filters.

Usage:
    python semantic_search.py "your query here" [--top-k 5] [--filter source_file]
"""

import argparse
import sys

from rich.console import Console
from rich.table import Table

from secondbrain.logging import setup_logging
from secondbrain.search import Searcher

console = Console()


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Perform semantic search on ingested documents"
    )
    parser.add_argument(
        "query",
        type=str,
        help="Search query (natural language)",
    )
    parser.add_argument(
        "--top-k",
        "-k",
        type=int,
        default=5,
        help="Number of results to return (default: 5)",
    )
    parser.add_argument(
        "--filter-source",
        type=str,
        help="Filter by source file (partial match)",
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
    """Main entry point for semantic search."""
    args = parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose)

    console.print(f"[blue]Searching for: '{args.query}'[/blue]")
    if args.filter_source:
        console.print(f"[blue]Filter by source: {args.filter_source}[/blue]")
    if args.filter_type:
        console.print(f"[blue]Filter by type: {args.filter_type}[/blue]")

    # Create searcher
    searcher = Searcher()

    try:
        # Perform search
        results = searcher.search(
            query=args.query,
            top_k=args.top_k,
            source_filter=args.filter_source,
            file_type_filter=args.filter_type,
        )

        if not results:
            console.print("[yellow]No results found.[/yellow]")
            return

        # Display results in a table
        table = Table(title=f"Search Results (top {len(results)} matches)")
        table.add_column("Score", justify="right", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Page", justify="right")
        table.add_column("Chunk Text", style="white")

        for result in results:
            # Truncate long text
            chunk_text = result.chunk_text
            if len(chunk_text) > 100:
                chunk_text = chunk_text[:100] + "..."

            table.add_row(
                f"{result.score:.3f}",
                result.source_file,
                str(result.page_number or "-"),
                chunk_text,
            )

        console.print(table)
        console.print(f"\n[blue]Total results: {len(results)}[/blue]")

    except Exception as e:
        console.print(f"[red]Search error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
