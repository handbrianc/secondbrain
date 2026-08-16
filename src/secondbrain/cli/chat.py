"""Chat command."""

import click
from rich.console import Console

from secondbrain.cli.chat_helpers import (
    _interactive_chat,
    _single_turn_chat,
)
from secondbrain.config import config

from . import cli
from .errors import handle_cli_errors

console = Console(markup=True)


@handle_cli_errors
@cli.command()
@click.argument("query", required=False)
@click.option("--session", "-s", type=str, help="Session ID to use/create")
@click.option(
    "--top-k",
    "-k",
    type=int,
    default=20,
    help="Number of chunks to retrieve (default: 20 for better context)",
)
@click.option("--temperature", "-t", type=float, default=0.1, help="LLM temperature")
@click.option("--model", "-m", type=str, default=None, help="LLM model name")
@click.option("--show-sources", is_flag=True, help="Show retrieved sources")
@click.option("--list-sessions", is_flag=True, help="List all sessions")
@click.option("--history", is_flag=True, help="Show session history")
@click.option("--delete-session", "-d", type=str, help="Delete a session")
@click.option(
    "--create",
    "-c",
    is_flag=True,
    help="Create a new session with UUID (ignores --session if both specified)",
)
@click.option("--check-llm", is_flag=True, help="Check if LLM provider is available")
@click.pass_context
def chat(
    ctx: click.Context,
    query: str | None,
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
    list_sessions: bool,
    history: bool,
    delete_session: str | None,
    create: bool,
    check_llm: bool,
) -> None:
    """Conversational Q&A with your documents using local LLM.

    Examples:
    --------
        secondbrain chat "What is secondbrain?"
        secondbrain chat --session my-chat
        secondbrain chat --list-sessions
        secondbrain chat --check-llm
    --------
    """
    from secondbrain.conversation import ConversationStorage
    from secondbrain.rag.providers import LLMProviderFactory

    cfg = config()

    if list_sessions:
        with ConversationStorage() as storage:
            sessions = storage.list_sessions(limit=100)
        if not sessions:
            console.print("[yellow]No sessions found.[/yellow]")
        else:
            console.print("[bold]Conversation Sessions[/bold]")
            console.print("=" * 60)
            for sess in sessions:
                status = (
                    f"[green]{sess['message_count']} messages[/green]"
                    if sess["message_count"] > 0
                    else "[dim]empty[/dim]"
                )
                console.print(
                    f"  {sess['session_id']}: {status} (created: {sess['created_at']})"
                )
        return

    if delete_session:
        confirm = console.input(
            f"Are you sure you want to delete session '{delete_session}'? [y/N]: "
        )
        if confirm.lower() != "y":
            console.print("[dim]Deletion cancelled.[/dim]")
            return

        with ConversationStorage() as storage:
            deleted = storage.delete_session(delete_session)
        if deleted:
            console.print(f"[green]Deleted session: {delete_session}[/green]")
        else:
            console.print(f"[red]Session not found: {delete_session}[/red]")
        return

    if check_llm:
        try:
            llm_provider = LLMProviderFactory.create_from_config(cfg)
            if llm_provider.health_check():
                console.print(
                    f"[green]✓ LLM provider ({cfg.llm_provider}) is healthy[/green]"
                )
            else:
                console.print(
                    f"[red]✗ LLM provider ({cfg.llm_provider}) health check failed[/red]"
                )
        except Exception as e:
            console.print(f"[red]✗ LLM provider error: {e!s}[/red]")
        return

    if history:
        if not session:
            console.print(
                "[red]Error: --history requires --session to be specified[/red]"
            )
            return
        with ConversationStorage() as storage:
            history_msgs = storage.get_history(session, limit=20)
        if not history_msgs:
            console.print(f"[yellow]No history for session: {session}[/yellow]")
        else:
            console.print(f"[bold]Session History: {session}[/bold]")
            console.print("=" * 60)
            for msg in history_msgs:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")
                role_color = (
                    "[cyan]User[/cyan]"
                    if role == "user"
                    else "[green]Assistant[/green]"
                )
                console.print(f"{role_color} ({timestamp}): {content}")
        return

    if create:
        session = None
    elif session is None:
        session = "default"

    if query is None:
        _interactive_chat(
            session=session,
            top_k=top_k,
            temperature=temperature,
            model=model,
            show_sources=show_sources,
        )
        return

    _single_turn_chat(
        query=query,
        session=session,
        top_k=top_k,
        temperature=temperature,
        model=model,
        show_sources=show_sources,
    )
