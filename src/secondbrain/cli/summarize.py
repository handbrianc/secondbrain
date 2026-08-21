"""Summarize command."""

import sys
from typing import Any

import click
from rich.console import Console

from secondbrain.config import config

from . import cli
from .errors import handle_cli_errors

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.option(
    "--chapter",
    "-c",
    type=int,
    help="Chapter number to summarize (required when not using --by-section)",
)
@click.option(
    "--by-section",
    is_flag=True,
    help="Summarize by section instead of by chapter. Requires --chapter to specify the parent chapter.",
)
@click.option(
    "--section-id",
    "-s",
    type=str,
    help="Section ID (dot-separated, e.g. '3.9'). Used with --by-section.",
)
@click.pass_context
def summarize(
    ctx: click.Context,
    chapter: int | None,
    by_section: bool,
    section_id: str | None,
) -> None:
    """Summarize document content by chapter or section.

    Produces a concise summary of the specified chapter or section using
    an LLM. Outputs the summary with title, content, chunk count, and
    token usage.

    Examples:
    --------
        secondbrain summarize --chapter 3          # Summarize chapter 3
        secondbrain summarize -c 2 --by-section    # Summarize a section within chapter 2
        secondbrain summarize -c 2 --by-section -s 2.9   # Summarize section 2.9 of chapter 2
    --------
    """
    import asyncio

    from secondbrain.document.summarizer import Summarizer
    from secondbrain.embedding import EmbeddingProviderFactory
    from secondbrain.rag.providers import LLMProviderFactory
    from secondbrain.storage import StorageFactory

    if by_section and chapter is None:
        console.print(
            "[red]Error: --by-section requires --chapter to specify the parent chapter[/red]"
        )
        sys.exit(1)

    if section_id is not None and not by_section:
        console.print("[red]Error: --section-id requires --by-section flag[/red]")
        sys.exit(1)

    if chapter is None and not by_section:
        console.print(
            "[red]Error: Must specify --chapter or use --by-section with --chapter[/red]"
        )
        sys.exit(1)

    cfg = config()

    llm_provider = LLMProviderFactory.create_from_config(cfg)
    embedder = EmbeddingProviderFactory.create_from_config(cfg)
    storage = StorageFactory.create_from_config()

    max_tokens = getattr(cfg, "llm_max_tokens", 512)
    summary_model = getattr(cfg, "llm_model", None)

    summarizer = Summarizer(
        llm_provider=llm_provider,
        embedder=embedder,
        storage=storage,
        max_summary_tokens=max_tokens,
        summary_model=summary_model,
    )

    async def _run() -> tuple[bool, str]:
        """Run summarization and return (has_content, formatted_output)."""
        try:
            if by_section:
                section_id_value: str = section_id  # type: ignore[assignment]
                section_result = await summarizer.summarize_by_section(section_id_value)
                if not section_result.summary:
                    return (False, "")
                tokens_used = (
                    getattr(section_result, "token_budget_used", 0) or max_tokens
                )
                return (
                    True,
                    _format_section_summary(section_result, tokens_used),
                )
            else:
                chapter_num: int = chapter  # type: ignore[assignment]
                chapter_result = await summarizer.summarize_by_chapter(chapter_num)
                if not chapter_result.summary:
                    return (False, "")
                tokens_used = (
                    getattr(chapter_result, "token_budget_used", 0) or max_tokens
                )
                return (
                    True,
                    _format_chapter_summary(chapter_result, tokens_used),
                )
        finally:
            storage.close()
            if hasattr(embedder, "close"):
                embedder.close()

    has_content, output = asyncio.run(_run())

    if not has_content:
        console.print(
            "[yellow]No content found for the specified chapter or section.[/yellow]\n"
            "[dim]This may mean the document hasn't been ingested yet, "
            "or the chapter/section doesn't exist.[/dim]"
        )
        return

    console.print(output)


def _format_chapter_summary(result: Any, tokens_used: int) -> str:
    """Format chapter summary for display."""
    lines = [
        "",
        f"[bold cyan]Chapter {result.chapter_id}: {result.chapter_title}[/bold cyan]",
        "─" * 60,
        "",
        result.summary,
        "",
        "─" * 60,
        f"[dim]Chunks processed: {result.chunk_count}  |  Tokens used: {tokens_used}[/dim]",
    ]
    return "\n".join(lines)


def _format_section_summary(result: Any, tokens_used: int) -> str:
    """Format section summary for display."""
    lines = [
        "",
        f"[bold cyan]Section {result.section_id}: {result.section_title}[/bold cyan]",
        f"[dim](Part of Chapter {result.belongs_to_chapter})[/dim]",
        "─" * 60,
        "",
        result.summary,
        "",
        "─" * 60,
        f"[dim]Tokens used: {tokens_used}[/dim]",
    ]
    return "\n".join(lines)
