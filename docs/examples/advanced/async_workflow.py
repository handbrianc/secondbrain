#!/usr/bin/env python3
"""Advanced async workflow example.

Demonstrates asynchronous document ingestion and search for
high-throughput scenarios.

Usage:
    python async_workflow.py /path/to/docs
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from rich.console import Console

from secondbrain.document import DocumentIngestor
from secondbrain.logging import setup_logging
from secondbrain.search import Searcher
from secondbrain.storage import VectorStorage

console = Console()


async def ingest_file_async(ingestor: DocumentIngestor, filepath: Path) -> None:
    """Asynchronously ingest a single file."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: ingestor.ingest(str(filepath)))


async def search_async(
    searcher: Searcher, query: str, top_k: int = 5
) -> list[dict[str, Any]]:
    """Asynchronously perform a search."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: searcher.search(query, top_k))


async def main_async(path: str, queries: list[str]) -> None:
    """Execute main async workflow."""
    setup_logging(verbose=True)

    console.print("[blue]Starting async workflow[/blue]\n")

    # Initialize components
    ingestor = DocumentIngestor()
    storage = VectorStorage()
    searcher = Searcher()

    # Ingest files
    files = [f for f in Path(path).glob("**/*") if f.is_file()]
    console.print(f"[cyan]Ingesting {len(files)} files asynchronously...[/cyan]")

    tasks = [ingest_file_async(ingestor, f) for f in files[:10]]  # Limit for demo
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if not isinstance(r, Exception))
    console.print(f"[green]✓ Ingested {success}/{len(files)} files[/green]\n")

    # Perform searches
    console.print("[cyan]Performing concurrent searches...[/cyan]")
    search_tasks = [search_async(searcher, query, top_k=3) for query in queries]
    search_results_list = await asyncio.gather(*search_tasks)

    for query, search_result in zip(queries, search_results_list, strict=False):
        console.print(f"\n[bold]Query: {query}[/bold]")
        for r in search_result[:3]:
            console.print(f"  Score: {r['score']:.3f} | {r['source_file']}")

    # Cleanup
    await storage.aclose()
    await searcher.aclose()

    console.print("\n[blue]Async workflow complete![/blue]")


def main() -> None:
    """Run main entry point."""
    parser = argparse.ArgumentParser(description="Async workflow example")
    parser.add_argument("path", type=str, help="Directory to ingest")
    parser.add_argument(
        "--queries",
        nargs="+",
        default=["what is this about?", "summary", "key topics"],
        help="Search queries",
    )
    args = parser.parse_args()

    if not Path(args.path).exists():
        console.print(f"[red]Error: Path not found: {args.path}[/red]")
        sys.exit(1)

    asyncio.run(main_async(args.path, args.queries))


if __name__ == "__main__":
    main()
