"""Status, health, and metrics commands."""

import json

import click
from rich.console import Console

from secondbrain.logging import get_health_status

from . import cli
from .display import display_health_status, display_status
from .errors import handle_cli_errors

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show statistics about the vector database."""
    from secondbrain.management import StatusChecker

    with (
        console.status("[cyan]Loading status...", spinner="dots"),
        StatusChecker(verbose=ctx.obj.get("verbose", False)) as status_checker,
    ):
        stats = status_checker.get_status()
    display_status(stats)


@handle_cli_errors
@cli.command()
@click.option(
    "--output",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def health(ctx: click.Context, output: str) -> None:
    """Check health status of all services."""
    with console.status("[cyan]Checking health...", spinner="dots"):
        health_status = get_health_status()
    if output == "json":
        console.print(json.dumps(health_status, indent=2))
    else:
        display_health_status(health_status)


@handle_cli_errors
@cli.command()
@click.option("--reset", "-r", is_flag=True, help="Reset all metrics")
@click.pass_context
def metrics(ctx: click.Context, reset: bool) -> None:
    """Show performance metrics and statistics."""
    from secondbrain.utils.perf_monitor import metrics as perf_metrics

    if reset:
        perf_metrics.reset()
        console.print("[green]All metrics reset[/green]")
        return

    with console.status("[cyan]Loading metrics...", spinner="dots"):
        all_metrics = [
            "embedding_generate",
            "embedding_generate_async",
            "embedding_generate_batch",
            "embedding_generate_batch_async",
            "storage_store",
            "storage_store_batch",
            "storage_search",
            "storage_store_async",
            "storage_store_batch_async",
            "storage_search_async",
        ]

        console.print("[bold]Performance Metrics[/bold]")
        console.print("=" * 60)

        has_data = False
        for metric_name in all_metrics:
            stats = perf_metrics.get_stats(metric_name)
            if stats and stats["count"] > 0:
                has_data = True
                console.print(f"\n[bold]{metric_name}[/bold]")
                console.print(f"  Count: {stats['count']}")
                console.print(f"  Total: {stats['total_seconds']:.3f}s")
                console.print(f"  Avg: {stats['avg_seconds']:.3f}s")
                console.print(f"  Min: {stats['min_seconds']:.3f}s")
                console.print(f"  Max: {stats['max_seconds']:.3f}s")

        if not has_data:
            console.print(
                "[yellow]No metrics collected yet. Run some operations first.[/yellow]"
            )
