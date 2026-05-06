"""CLI commands for secondbrain document intelligence tool.

This module provides Click-based CLI commands for:
- Document ingestion (ingest)
- Semantic search (search)
- Document listing (list)
- Document deletion (delete)
- Status display (status)
- Health checks (health)

Each command includes comprehensive error handling, progress indicators,
and user-friendly output formatting using Rich library.
"""

import json
import logging
import os
import readline
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from secondbrain.config import config
from secondbrain.exceptions import (
    CLIValidationError,
    ServiceUnavailableError,
    StorageConnectionError,
)
from secondbrain.logging import get_health_status
from secondbrain.storage import ChunkInfo
from secondbrain.utils.docker_manager import (
    DockerComposeError,
    DockerNotInstalledError,
)

from . import cli
from .display import (
    display_health_status,
    display_list_results,
    display_search_results,
    display_status,
)
from .errors import handle_cli_errors

console = Console(markup=True)
logger = logging.getLogger(__name__)

MAX_LIST_LIMIT = 100000


@handle_cli_errors
@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--recursive", "-r", is_flag=True, help="Recursively process directories")
@click.option(
    "--batch-size",
    "-b",
    type=click.IntRange(min=1),
    default=10,
    help="Batch size for ThreadPoolExecutor (used when cores=1)",
)
@click.option("--chunk-size", type=int, help="Override default chunk size")
@click.option("--chunk-overlap", type=int, help="Override default chunk overlap")
@click.option(
    "--cores",
    "-c",
    type=int,
    help="Number of CPU cores to use for parallel processing (default: auto-detect)",
)
@click.pass_context
def ingest(
    ctx: click.Context,
    path: str,
    recursive: bool,
    batch_size: int,
    chunk_size: int | None,
    chunk_overlap: int | None,
    cores: int | None,
) -> None:
    """Ingest documents into the vector database.

    PATH: Path to file or directory to ingest.
    """
    from secondbrain.document import DocumentIngestor

    cfg = config()
    chunk_size = cfg.chunk_size if chunk_size is None else chunk_size
    chunk_overlap = cfg.chunk_overlap if chunk_overlap is None else chunk_overlap

    # Validate and resolve core count
    if cores is not None:
        if cores <= 0:
            raise CLIValidationError("cores must be positive")
        available_cores = os.cpu_count() or 1
        if cores > available_cores:
            console.print(
                f"[yellow]Warning: Requested {cores} cores, but only {available_cores} available. Using {available_cores}.[/yellow]"
            )
            cores = available_cores

    # Use verbose flag from global CLI context
    verbose = ctx.obj.get("verbose", False)

    console.print(f"[bold]Ingesting: {path}[/bold]")

    # Collect files to show progress
    from pathlib import Path

    from secondbrain.document import is_supported

    path_obj = Path(path)
    if path_obj.is_file():
        files = [path_obj]
    else:
        files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
        files = [f for f in files if f.is_file() and is_supported(f)]

    total_files = len(files)

    if total_files > 10:  # Only show progress for larger batches
        from rich.progress import Progress, SpinnerColumn, TextColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TextColumn("[progress.completed]{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Ingesting...", total=total_files)

            # Create progress callback that updates the progress bar
            def progress_callback(file_path: Path, success: bool) -> None:
                status = "[green]✓[/green]" if success else "[red]✗[/red]"
                progress.update(
                    task, description=f"[cyan]Ingesting... {status} {file_path.name}"
                )
                progress.advance(task)
                progress.refresh()  # Force immediate refresh

            ingestor = DocumentIngestor(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                verbose=verbose,
                progress_callback=progress_callback,
            )

            # Use ThreadPoolExecutor when progress tracking is enabled
            # Threads share memory so callbacks can update the progress bar
            # For I/O-bound work, threads perform nearly as well as processes
            results = ingestor.ingest(
                path, recursive=recursive, batch_size=batch_size, cores=cores
            )
    else:
        ingestor = DocumentIngestor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            verbose=verbose,
        )
        results = ingestor.ingest(
            path, recursive=recursive, batch_size=batch_size, cores=cores
        )

    console.print(f"[green]Successfully ingested {results['success']} files[/green]")
    if results["failed"] > 0:
        console.print(f"[yellow]Failed: {results['failed']} files[/yellow]")


@handle_cli_errors
@cli.command()
@click.argument("query")
@click.option("--top-k", type=int, help="Number of results to return")
@click.option(
    "--source",
    type=str,
    help="Filter results by source file path (e.g., '/path/to/document.pdf')",
)
@click.option(
    "--file-type",
    type=str,
    help="Filter results by file type (e.g., 'pdf', 'docx', 'markdown')",
)
@click.option(
    "--format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format",
)
@click.option(
    "--min-score",
    type=float,
    default=None,
    help="Minimum similarity score threshold (0.0-1.0, default: 0.46)",
)
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    top_k: int | None,
    source: str | None,
    file_type: str | None,
    format: str,
    min_score: float,
) -> None:
    """Search the vector database with semantic query.

    QUERY: Search query text.
    """
    from secondbrain.constants import DEFAULT_MIN_SIMILARITY_THRESHOLD
    from secondbrain.search import Searcher

    cfg = config()
    top_k = top_k or cfg.default_top_k
    # Use provided min_score or fall back to default constant
    effective_min_score = (
        min_score if min_score is not None else DEFAULT_MIN_SIMILARITY_THRESHOLD
    )

    with (
        console.status("[cyan]Searching...", spinner="dots"),
        Searcher(verbose=ctx.obj.get("verbose", False)) as searcher,
    ):
        results: list[dict[str, Any]] = searcher.search(
            query=query,
            top_k=top_k,
            source_filter=source,
            file_type_filter=file_type,
        )
    display_search_results(results, format, min_score=effective_min_score)


@handle_cli_errors
@cli.command()
@click.option("--source", type=str, help="Filter by source file")
@click.option("--chunk-id", type=str, help="Filter by specific chunk ID")
@click.option("--limit", type=int, default=100, help="Maximum number of results")
@click.option("--offset", type=int, default=0, help="Offset for pagination")
@click.option("--all", "-a", is_flag=True, help="List all documents (ignores limit)")
@click.pass_context
def ls(
    ctx: click.Context,
    source: str | None,
    chunk_id: str | None,
    limit: int,
    offset: int,
    all: bool,
) -> None:
    """List ingested documents and chunks."""
    from secondbrain.management import Lister

    if limit < 0:
        raise CLIValidationError("Limit must be non-negative")
    if limit > MAX_LIST_LIMIT:
        click.echo(
            f"Warning: Limit {limit} exceeds maximum {MAX_LIST_LIMIT}, "
            f"clamping to {MAX_LIST_LIMIT}",
            err=True,
        )
        limit = MAX_LIST_LIMIT

    if offset < 0:
        raise CLIValidationError("Offset must be non-negative")

    with (
        console.status("[cyan]Loading...", spinner="dots"),
        Lister(verbose=ctx.obj.get("verbose", False)) as lister,
    ):
        if all:
            limit = MAX_LIST_LIMIT
        results: list[ChunkInfo] = lister.list_chunks(
            source_filter=source,
            chunk_id=chunk_id,
            limit=limit,
            offset=offset,
        )
    display_list_results(results)


@handle_cli_errors
@cli.command()
@click.option("--source", type=str, help="Filter by source file")
@click.option("--chunk-id", type=str, help="Filter by specific chunk ID")
@click.option("--all", "-a", is_flag=True, help="Delete all documents")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete(
    ctx: click.Context,
    source: str | None,
    chunk_id: str | None,
    all: bool,
    yes: bool,
) -> None:
    """Delete documents from the vector database."""
    from secondbrain.management import Deleter

    # Validate options
    if not any([source, chunk_id, all]):
        console.print("[red]Error: Must specify --source, --chunk-id, or --all[/red]")
        sys.exit(1)

    if sum([bool(source), bool(chunk_id), all]) > 1:
        console.print(
            "[red]Error: Specify only one of --source, --chunk-id, or --all[/red]"
        )
        sys.exit(1)

    # Get confirmation
    if not yes:
        if all:
            if not click.confirm("Delete all documents? This cannot be undone."):
                console.print("Cancelled.")
                return
        else:
            if not click.confirm("Delete documents matching criteria?"):
                console.print("Cancelled.")
                return

    with (
        console.status("[cyan]Deleting...", spinner="dots"),
        Deleter(verbose=ctx.obj.get("verbose", False)) as deleter,
    ):
        try:
            count = deleter.delete(source=source, chunk_id=chunk_id, all=all)
            console.print(f"[green]Deleted {count} document(s)[/green]")
        except (
            ServiceUnavailableError,
            StorageConnectionError,
            CLIValidationError,
        ) as e:
            console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)


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
@click.option("--check-llm", is_flag=True, help="Check if Ollama is available")
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
        secondbrain chat "What is secondbrain?"
        secondbrain chat --session my-chat
        secondbrain chat --list-sessions
        secondbrain chat --check-llm
    """
    from secondbrain.config import config
    from secondbrain.conversation import ConversationStorage
    from secondbrain.rag.providers import OllamaLLMProvider

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
        confirm = console.input(f"Are you sure you want to delete session '{delete_session}'? [y/N]: ")
        if confirm.lower() != 'y':
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
        llm_provider = OllamaLLMProvider(host=cfg.ollama_host, model=cfg.llm_model)
        if llm_provider.health_check():
            console.print(
                f"[green]✓ Ollama is available[/green] (model: {llm_provider.model})"
            )
        else:
            console.print(f"[red]✗ Ollama is not available at {cfg.ollama_host}[/red]")
            console.print(
                "[yellow]Start Ollama with: sentence-transformers serve[/yellow]"
            )
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


def _single_turn_chat(
    query: str,
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
) -> None:
    """Handle single-turn chat with a query."""
    from secondbrain.config import config
    from secondbrain.conversation import ConversationSession, ConversationStorage
    from secondbrain.rag import RAGPipeline
    from secondbrain.rag.providers import OllamaLLMProvider
    from secondbrain.search import Searcher

    cfg = config()

    with ConversationStorage() as storage:
        if session is None:
            session_obj = ConversationSession.create(storage=storage)
            console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
        else:
            session_obj = ConversationSession.load(session, storage)
            if session_obj is None:
                session_obj = ConversationSession.create(session, storage)

    searcher = Searcher(verbose=False)
    llm_model = model or cfg.llm_model
    llm_provider = OllamaLLMProvider(
        host=cfg.ollama_host, model=llm_model, temperature=temperature
    )

    pipeline = RAGPipeline(
        searcher=searcher,
        llm_provider=llm_provider,
        top_k=top_k,
        context_window=cfg.rag_context_window,
    )

    with console.status("[cyan]Thinking...", spinner="dots"):
        result = pipeline.chat(
            query, session_obj, top_k=top_k, show_sources=show_sources
        )

    console.print("\n[bold green]Answer:[/bold green]")
    console.print(result["answer"])

    # Show sources if requested
    if show_sources and result.get("sources"):
        console.print("\n[bold blue]Sources:[/bold blue]")
        for i, chunk in enumerate(result["sources"], 1):
            source_file = chunk.get("source_file", chunk.get("source", "unknown"))
            page = chunk.get("page", chunk.get("page_number", "unknown"))
            chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
            if len(chunk_text) > 200:
                chunk_text = chunk_text[:200] + "..."
            console.print(f"  [{i}] {source_file} (page {page}): {chunk_text}")


def _interactive_chat(
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
) -> None:
    """Handle interactive REPL mode for chat."""
    from secondbrain.config import config
    from secondbrain.conversation import ConversationSession, ConversationStorage
    from secondbrain.rag import RAGPipeline
    from secondbrain.rag.providers import OllamaLLMProvider
    from secondbrain.search import Searcher

    cfg = config()

    console.print("\n[bold]SecondBrain Interactive Chat[/bold]")
    console.print("=" * 60)
    console.print(f"Session: [cyan]{session}[/cyan]")
    console.print("Type /quit to exit, /clear to clear history, /help for commands\n")

    # Load or create session
    with ConversationStorage() as storage:
        if session is None:
            session_obj = ConversationSession.create(storage=storage)
            console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
        else:
            session_obj = ConversationSession.load(session, storage)
            if session_obj is None:
                session_obj = ConversationSession.create(session, storage)
                console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
            elif not session_obj.is_empty:
                console.print(
                    f"[dim]Resuming session with {session_obj.message_count} messages[/dim]"
                )

    searcher = Searcher(verbose=False)
    llm_model = model or cfg.llm_model
    llm_provider = OllamaLLMProvider(
        host=cfg.ollama_host, model=llm_model, temperature=temperature
    )

    # Initialize RAG pipeline
    pipeline = RAGPipeline(
        searcher=searcher,
        llm_provider=llm_provider,
        top_k=top_k,
        context_window=cfg.rag_context_window,
    )

    history_file = Path("~/.secondbrain_chat_history").expanduser()

    if history_file.exists():
        readline.read_history_file(history_file)

    readline.set_history_length(1000)

    chat_history = []
    while True:
        try:
            try:
                user_input = input("\n[you] ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            # Handle special commands
            if user_input.startswith("/"):
                command = user_input.lower()
                if command == "/quit" or command == "/exit":
                    console.print("[dim]Goodbye![/dim]")
                    break
                elif command == "/clear":
                    session_obj.clear_history()
                    console.print("[green]History cleared[/green]")
                    continue
                elif command == "/help":
                    console.print("[bold]Commands:[/bold]")
                    console.print("  /quit     Exit the chat")
                    console.print("  /clear    Clear conversation history")
                    console.print("  /help     Show this help")
                    continue
                else:
                    console.print(f"[yellow]Unknown command: {user_input}[/yellow]")
                    continue

            with console.status("[cyan]Thinking...", spinner="dots"):
                result = pipeline.chat(
                    user_input, session_obj, top_k=top_k, show_sources=show_sources
                )

            console.print("\n[bold green]Assistant:[/bold green]")
            console.print(result["answer"])

            # Show sources if requested
            if show_sources and result.get("sources"):
                console.print("\n[bold blue]Sources:[/bold blue]")
                for i, chunk in enumerate(result["sources"], 1):
                    source_file = chunk.get(
                        "source_file", chunk.get("source", "unknown")
                    )
                    page = chunk.get("page", chunk.get("page_number", "unknown"))
                    chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
                    if len(chunk_text) > 200:
                        chunk_text = chunk_text[:200] + "..."
                    console.print(f"  [{i}] {source_file} (page {page}): {chunk_text}")

            # Save to history
            chat_history.append(user_input)
            try:
                with history_file.open("a") as f:
                    f.write(user_input + "\n")
                readline.write_history_file(history_file)
            except Exception:
                pass

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@handle_cli_errors
@cli.command()
@click.option(
    "--compose-file",
    "-f",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose.yml (default: auto-detect in project root)",
)
@click.option(
    "--project-name",
    "-p",
    type=str,
    default="secondbrain",
    help="Docker Compose project name (default: secondbrain)",
)
@click.option(
    "--wait",
    "-w",
    is_flag=True,
    help="Wait for services to be fully ready before returning",
)
@click.pass_context
def start(
    ctx: click.Context,
    compose_file: str | None,
    project_name: str,
    wait: bool,
) -> None:
    """Start the production Docker Compose stack.

    Starts MongoDB and other services defined in docker-compose.yml.
    By default, starts only MongoDB service.

    Examples:
        secondbrain start                    # Start with auto-detected compose file
        secondbrain start -f docker-compose.prod.yml  # Use specific compose file
        secondbrain start --wait             # Wait for services to be fully ready
    """
    from secondbrain.utils.docker_manager import DockerManager

    # Auto-detect compose file if not specified
    if compose_file is None:
        # Check common locations
        possible_paths = [
            Path.cwd() / "docker-compose.yml",
            Path.cwd() / "docker-compose.prod.yml",
            Path(__file__).parent.parent.parent.parent / "docker-compose.yml",
        ]
        for path in possible_paths:
            if path.exists():
                compose_file = str(path)
                break

        if compose_file is None:
            raise CLIValidationError(
                "No docker-compose.yml found. Please specify --compose-file "
                "or place docker-compose.yml in the current directory or project root."
            )

    console.print(f"[cyan]Starting Docker Compose stack from: {compose_file}[/cyan]")

    try:
        manager = DockerManager(compose_file=compose_file, project_name=project_name)

        # Check if Docker is available
        if not manager.check_docker_installed():
            raise DockerNotInstalledError(
                "[red]✗ Docker is not installed or not in PATH[/red]\n\n"
                "Please install Docker Desktop (macOS/Windows) or Docker Engine (Linux):\n"
                "  - https://docs.docker.com/get-docker/"
            )

        if not manager.check_docker_compose_installed():
            raise DockerComposeError(
                "[red]✗ docker compose (v2) is not installed[/red]\n\n"
                "Please install Docker Compose plugin:\n"
                "  - https://docs.docker.com/compose/install/"
            )

        # Start MongoDB
        console.print("[cyan]Starting MongoDB...[/cyan]")
        manager.start_mongo()

        # Wait for ready if requested
        if wait:
            console.print("[cyan]Waiting for services to be ready...[/cyan]")
            manager.wait_for_mongo_ready()
            console.print("[green]✓ Docker Compose stack is fully ready[/green]")
        else:
            console.print("[green]✓ Docker Compose stack started successfully[/green]")
            console.print(
                "[dim]Use --wait to wait for services to be fully ready[/dim]"
            )

    except DockerNotInstalledError as e:
        console.print(str(e))
        sys.exit(1)
    except DockerComposeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)


@handle_cli_errors
@cli.command()
@click.option(
    "--compose-file",
    "-f",
    type=click.Path(exists=True),
    default=None,
    help="Path to docker-compose.yml (default: auto-detect in project root)",
)
@click.option(
    "--project-name",
    "-p",
    type=str,
    default="secondbrain",
    help="Docker Compose project name (default: secondbrain)",
)
@click.option(
    "--remove-volumes",
    "-v",
    is_flag=True,
    help="Remove named volumes as well",
)
@click.option(
    "--force",
    "-y",
    is_flag=True,
    help="Skip confirmation prompt",
)
@click.pass_context
def stop(
    ctx: click.Context,
    compose_file: str | None,
    project_name: str,
    remove_volumes: bool,
    force: bool,
) -> None:
    """Stop the production Docker Compose stack.

    Stops and removes containers created by docker compose up.

    Examples:
        secondbrain stop                       # Stop with auto-detected compose file
        secondbrain stop -f docker-compose.prod.yml  # Use specific compose file
        secondbrain stop --remove-volumes      # Also remove volumes
        secondbrain stop --force               # Skip confirmation
    """
    import subprocess

    # Auto-detect compose file if not specified
    if compose_file is None:
        # Check common locations
        possible_paths = [
            Path.cwd() / "docker-compose.yml",
            Path.cwd() / "docker-compose.prod.yml",
            Path(__file__).parent.parent.parent.parent / "docker-compose.yml",
        ]
        for path in possible_paths:
            if path.exists():
                compose_file = str(path)
                break

        if compose_file is None:
            raise CLIValidationError(
                "No docker-compose.yml found. Please specify --compose-file "
                "or place docker-compose.yml in the current directory or project root."
            )

    # Get confirmation
    if not force:
        action = "remove volumes" if remove_volumes else "stop containers"
        if not click.confirm(
            f"Stop Docker Compose stack and {action}? This will stop all services."
        ):
            console.print("Cancelled.")
            return

    console.print(f"[cyan]Stopping Docker Compose stack from: {compose_file}[/cyan]")

    # Check if Docker is available
    if (
        subprocess.run(
            ["docker", "--version"], capture_output=True, check=False
        ).returncode
        != 0
    ):
        console.print(
            "[red]✗ Docker is not installed or not in PATH[/red]\n"
            "Please install Docker to use this feature."
        )
        sys.exit(1)

    try:
        # Run docker compose down
        cmd = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "-p",
            project_name,
            "down",
        ]

        if remove_volumes:
            cmd.append("-v")

        console.print("[cyan]Stopping services...[/cyan]")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise DockerComposeError(
                f"Failed to stop Docker Compose stack: {error_msg}"
            )

        console.print("[green]✓ Docker Compose stack stopped successfully[/green]")

        if remove_volumes:
            console.print("[dim]Named volumes have been removed[/dim]")

    except subprocess.TimeoutExpired:
        console.print(
            "[red]Error: Timeout while stopping Docker Compose stack[/red]\n"
            "Please check running containers with: docker ps"
        )
        sys.exit(1)
    except DockerComposeError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
