"""Chat support helpers: spinner, single-turn, and interactive chat."""

import logging
import os
import readline
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from secondbrain.config import config

logger = logging.getLogger(__name__)

console = Console(markup=True)


def _run_chat_with_spinner(
    pipeline: Any,
    query: str,
    session_obj: Any,
    top_k: int,
    show_sources: bool,
) -> dict[str, Any]:
    """Run chat with a Rich spinner that animates until streaming starts.

    Uses a background thread so the spinner can animate while the LLM
    generates its first response token.  All output is routed through a
    ``queue.Queue`` to avoid interleaving with Rich's Live display.
    The spinner is written to stderr so it never pollutes stdout.
    """
    import contextlib
    import queue
    import threading

    chunk_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    done_event = threading.Event()

    def on_chunk(content: str, reasoning: str | None) -> None:
        if content or reasoning:
            chunk_queue.put((content or "", reasoning or ""))

    pipeline._on_chunk = on_chunk

    result_container: dict[str, Any] = {}

    def _run() -> None:
        try:
            result_container["result"] = pipeline.chat(
                query, session_obj, top_k=top_k, show_sources=show_sources
            )
        except BaseException as exc:
            result_container["error"] = exc
        finally:
            done_event.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    import sys as _sys

    # Thinking/reasoning streams live in dark gray by default, so generation is
    # visibly streaming for the whole thinking phase (which dominates wall-clock
    # time for long-context overviews) instead of hiding behind the spinner.
    # SECONDBRAIN_SHOW_THINKING=0 opts out:
    #   - Fold-capable terminals (iTerm2 OSC-1337, Windows Terminal OSC-133 C/D):
    #     reasoning is buffered and emitted once as a foldable block.
    #   - Other terminals (Ghostty, Linux, ...): reasoning buffers and collapses
    #     to a single dark-gray summary line.
    raw_thinking = os.environ.get("SECONDBRAIN_SHOW_THINKING", "1").strip().lower()
    show_thinking = raw_thinking not in ("0", "false", "no", "off")
    is_tty = _sys.stdout.isatty()
    is_iterm = os.environ.get("TERM_PROGRAM") == "iTerm.app" and is_tty
    is_wt = bool(os.environ.get("WT_SESSION")) and is_tty
    live_thinking = show_thinking
    osc1337 = "\x1b]1337;"
    osc133 = "\x1b]133;"
    bel = "\x07"
    gray_on = "\x1b[38;2;128;128;128m"
    reset = "\x1b[0m"
    reasoning_buffer: list[str] = []
    live_started: list[bool] = [False]
    wrote_content: list[bool] = [False]

    def _flush_buffered_thinking() -> None:
        if not reasoning_buffer:
            return
        text = "".join(reasoning_buffer)
        if is_iterm:
            _sys.stdout.write(
                f"{osc1337}Block=id=thinking;attr=start{bel}{text}"
                f"{osc1337}UpdateBlock=id=thinking;action=fold{bel}"
                f"{osc1337}Block=id=thinking;attr=end{bel}\n"
            )
            _sys.stdout.flush()
        elif is_wt:
            _sys.stdout.write(f"{osc133}C{bel}{text}{osc133}D{bel}\n")
            _sys.stdout.flush()
        else:
            console.print(
                f"\n\u25b8 Thinking: {len(text)} chars (collapsed)", style="#808080"
            )
        reasoning_buffer.clear()

    def _stream_thinking_live(reasoning: str) -> None:
        if not live_started[0]:
            console.print("\u25b8 Thinking:", style="#808080")
            live_started[0] = True
        # stdout is block-buffered on pipes and line-buffered (not delta-
        # buffered) on TTYs; reasoning arrives as many tiny deltas with no
        # newlines, so without an explicit flush it sits in the buffer until
        # the answer phase flushes -- i.e. the entire thinking phase renders
        # as one burst at the end instead of streaming live.
        _sys.stdout.write(f"{gray_on}{reasoning}{reset}")
        _sys.stdout.flush()

    def _separate_before_answer() -> None:
        if live_started[0]:
            _sys.stdout.write("\n")
            _sys.stdout.flush()
            live_started[0] = False

    def _emit(content: str, reasoning: str) -> None:
        if reasoning:
            if live_thinking:
                _stream_thinking_live(reasoning)
            else:
                reasoning_buffer.append(reasoning)
            return
        _flush_buffered_thinking()
        _separate_before_answer()
        if content:
            _sys.stdout.write(content)
            _sys.stdout.flush()
            wrote_content[0] = True

    first_token: tuple[str, str] | None = None
    with console.status("[bold cyan]Thinking...", spinner="dots"):
        while first_token is None:
            try:
                token = chunk_queue.get(timeout=0.1)
            except queue.Empty:
                if done_event.is_set():
                    break
                continue
            content, reasoning = token
            if reasoning and not content:
                if live_thinking:
                    first_token = token
                else:
                    reasoning_buffer.append(reasoning)
                # Lift the spinner as soon as any token (incl. reasoning) arrives
                # so a thinking-model chat is never stuck on "Thinking..." while
                # it reasons in the background.
                if first_token is None:
                    first_token = ("", reasoning)
                continue
            first_token = token

    if first_token is not None:
        _emit(*first_token)

    while not done_event.is_set() or not chunk_queue.empty():
        with contextlib.suppress(queue.Empty):
            _emit(*chunk_queue.get(timeout=0.1))

    _flush_buffered_thinking()
    _separate_before_answer()
    if wrote_content[0]:
        _sys.stdout.write("\n")
        _sys.stdout.flush()

    t.join()

    # Propagate any exception that occurred in the background thread.
    if "error" in result_container:
        raise result_container["error"]

    result: dict[str, Any] = result_container.get("result", {})

    # Non-streaming path: no content streamed through the callback, but the
    # answer is in result["answer"].
    if not wrote_content[0] and result.get("answer"):
        _sys.stdout.write(result["answer"])
        _sys.stdout.flush()

    return result


def _single_turn_chat(
    query: str,
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
) -> None:
    """Handle single-turn chat with a query.

    Shows a thinking spinner until the first response token arrives,
    then streams subsequent tokens directly to the terminal.
    """
    from secondbrain.conversation import ConversationSession, ConversationStorage
    from secondbrain.rag import RAGPipeline
    from secondbrain.rag.factory import create_query_rewriter
    from secondbrain.rag.intent_parser import StructuralIntentParser
    from secondbrain.rag.providers import LLMProviderFactory
    from secondbrain.search import Searcher

    cfg = config()

    intent_parser = StructuralIntentParser(cfg)
    intent_result = intent_parser.parse(query)
    click.echo(
        f"\u25b6 Detected intent: {'general query' if intent_result.intent.name == 'UNKNOWN' else intent_result.intent.name.lower().replace('_', ' ')}",
        err=True,
    )

    with ConversationStorage() as storage:
        if session is None:
            session_obj = ConversationSession.create(
                storage=storage, context_window=cfg.rag_context_window
            )
            console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
        else:
            loaded = ConversationSession.load(
                session, storage, context_window=cfg.rag_context_window
            )
            if loaded is None:
                session_obj = ConversationSession.create(
                    session, storage, context_window=cfg.rag_context_window
                )
            else:
                session_obj = loaded

    searcher = Searcher(verbose=False)
    llm_provider = LLMProviderFactory.create_from_config(cfg)

    pipeline = RAGPipeline(
        searcher=searcher,
        llm_provider=llm_provider,
        rewriter=create_query_rewriter(llm_provider),
        top_k=top_k,
        context_window=cfg.rag_context_window,
    )

    result = _run_chat_with_spinner(
        pipeline,
        query,
        session_obj,
        top_k=top_k,
        show_sources=show_sources,
    )

    # Ensure trailing newline after streamed output
    sys.stdout.write("\n")
    sys.stdout.flush()

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
    from secondbrain.conversation import ConversationSession, ConversationStorage
    from secondbrain.rag import RAGPipeline
    from secondbrain.rag.factory import create_query_rewriter
    from secondbrain.rag.intent_parser import StructuralIntentParser
    from secondbrain.rag.providers import LLMProviderFactory
    from secondbrain.search import Searcher

    cfg = config()

    intent_parser = StructuralIntentParser(cfg)
    console.print("\n[bold]SecondBrain Interactive Chat[/bold]")
    console.print("=" * 60)
    console.print(f"Session: [cyan]{session}[/cyan]")
    console.print("Type /quit to exit, /clear to clear history, /help for commands\n")

    with ConversationStorage() as storage:
        if session is None:
            session_obj = ConversationSession.create(
                storage=storage, context_window=cfg.rag_context_window
            )
            console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
        else:
            loaded = ConversationSession.load(
                session, storage, context_window=cfg.rag_context_window
            )
            if loaded is None:
                session_obj = ConversationSession.create(
                    session, storage, context_window=cfg.rag_context_window
                )
                console.print(
                    f"[dim]Created new session: {session_obj.session_id}[/dim]"
                )
            else:
                session_obj = loaded
                if not session_obj.is_empty:
                    console.print(
                        f"[dim]Resuming session with {session_obj.message_count} messages[/dim]"
                    )

    searcher = Searcher(verbose=False)
    llm_provider = LLMProviderFactory.create_from_config(cfg)

    history_file = Path("~/.secondbrain_chat_history").expanduser()

    if history_file.exists():
        readline.read_history_file(history_file)

    readline.set_history_length(1000)

    chat_history: list[str] = []
    while True:
        try:
            try:
                user_input = input("\n[you] ").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input.lower()
                if command == "/quit" or command == "/exit":
                    console.print("[dim]Goodbye![/dim]")
                    break
                elif command == "/clear":
                    session_obj.clear_history()
                    chat_history.clear()
                    try:
                        readline.clear_history()
                        readline.write_history_file(history_file)
                    except OSError as exc:
                        logger.debug("Failed to reset persisted chat history: %s", exc)
                    console.print(
                        "[green]Conversation history cleared (input history reset)[/green]"
                    )
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

            intent_result = intent_parser.parse(user_input)
            click.echo(
                f"\u25b6 Detected intent: {'general query' if intent_result.intent.name == 'UNKNOWN' else intent_result.intent.name.lower().replace('_', ' ')}",
                err=True,
            )

            streaming_pipeline = RAGPipeline(
                searcher=searcher,
                llm_provider=llm_provider,
                rewriter=create_query_rewriter(llm_provider),
                top_k=top_k,
                context_window=cfg.rag_context_window,
            )

            result = _run_chat_with_spinner(
                streaming_pipeline,
                user_input,
                session_obj,
                top_k=top_k,
                show_sources=show_sources,
            )

            sys.stdout.write("\n")
            sys.stdout.flush()

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
            except OSError as exc:
                # History persistence is best-effort; log instead of failing the session.
                logger.debug(
                    "Failed to persist chat history to %s: %s", history_file, exc
                )

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
