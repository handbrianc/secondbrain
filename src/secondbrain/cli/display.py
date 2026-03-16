"""CLI display utilities for formatting output."""

import json
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.table import Table

from secondbrain.logging import HealthStatus
from secondbrain.storage import ChunkInfo, DatabaseStats

console = Console()

# Minimum similarity threshold for displaying search results
# Results below this score are considered irrelevant
DEFAULT_MIN_SIMILARITY_THRESHOLD = 0.78


def display_search_results(
    results: list[dict[str, Any]],
    format: str,
    min_score: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
) -> None:
    """Display search results in the specified format.

    Args:
        results: List of search results to display.
        format: Output format: 'table', 'json'.
        min_score: Minimum similarity score threshold (0.0-1.0).
    """
    # JSON format always returns valid JSON, even for empty results
    if format == "json":
        console.print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    # Filter by minimum similarity threshold
    filtered_results = [r for r in results if r.get("score", 0) >= min_score]

    if not filtered_results:
        console.print(
            f"[yellow]No relevant results found (minimum score: {min_score})[/yellow]"
        )
        console.print("[dim]Try different keywords or lower the threshold[/dim]")
        return

    for i, result in enumerate(filtered_results, 1):
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


def display_list_results(results: Sequence[ChunkInfo]) -> None:
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


def display_status(stats: DatabaseStats) -> None:
    """Display database status statistics.

    Args:
        stats: DatabaseStats dictionary with chunk and collection info.
    """
    console.print("[bold]Database Status[/bold]")
    console.print(f"  Total chunks: {stats['total_chunks']}")
    console.print(f"  Unique sources: {stats['unique_sources']}")
    console.print(f"  Database: {stats['database']}")
    console.print(f"  Collection: {stats['collection']}")


def display_health_status(status: HealthStatus) -> None:
    """Display health status in text format.

    Args:
        status: HealthStatus dictionary with service availability and timing.
    """
    status_color = "green" if status["status"] == "healthy" else "yellow"
    status_value = status["status"].upper()
    console.print(
        f"[bold {status_color}]Health Status: {status_value}[/bold {status_color}]"
    )
    console.print(f"  Timestamp: {status['timestamp']}")
    console.print(f"  Check Duration: {status['check_duration_seconds']:.3f}s")
    console.print("\n[bold]Services:[/bold]")
    for service, available in status["services"].items():
        icon = "[green]✓[/green]" if available else "[red]✗[/red]"
        console.print(f"  {icon} {service}")
