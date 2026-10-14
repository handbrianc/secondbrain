"""Chat support helpers: spinner, single-turn, and interactive chat."""

import contextlib
import logging
import os
import queue
import readline
import sys
import threading
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from secondbrain.config import config

logger = logging.getLogger(__name__)

console = Console(markup=True)

# Escape sequences used to fold buffered reasoning into collapsible terminal
# blocks (iTerm2 OSC-1337, Windows Terminal OSC-133 C/D).
_OSC1337 = "\x1b]1337;"
_OSC133 = "\x1b]133;"
_BEL = "\x07"
_GRAY_ON = "\x1b[38;2;128;128;128m"
_RESET = "\x1b[0m"


class _ThinkingStream:
    """Terminal output renderer for chat streaming with reasoning support.

    Encapsulates the terminal-capability detection (iTerm2 OSC-1337 and
    Windows Terminal OSC-133 fold protocols) and the reasoning/content
    emission state machine used by :func:`_run_chat_with_spinner`.
    """

    def __init__(self) -> None:
        # Thinking/reasoning streams live in dark gray by default, so generation
        # is visibly streaming for the whole thinking phase (which dominates
        # wall-clock time for long-context overviews) instead of hiding behind
        # the spinner.  SECONDBRAIN_SHOW_THINKING=0 opts out:
        #   - Fold-capable terminals (iTerm2 OSC-1337, Windows Terminal OSC-133
        #     C/D): reasoning is buffered and emitted once as a foldable block.
        #   - Other terminals (Ghostty, Linux, ...): reasoning buffers and
        #     collapses to a single dark-gray summary line.
        raw_thinking = os.environ.get("SECONDBRAIN_SHOW_THINKING", "1").strip().lower()
        show_thinking = raw_thinking not in ("0", "false", "no", "off")
        is_tty = sys.stdout.isatty()
        self._is_iterm = os.environ.get("TERM_PROGRAM") == "iTerm.app" and is_tty
        self._is_wt = bool(os.environ.get("WT_SESSION")) and is_tty
        self.live_thinking = show_thinking
        self._reasoning_buffer: list[str] = []
        self._live_started = False
        self.wrote_content = False

    def buffer_reasoning(self, reasoning: str) -> None:
        """Buffer a reasoning delta for later collapsed emission."""
        self._reasoning_buffer.append(reasoning)

    def _flush_buffered_thinking(self) -> None:
        """Emit buffered reasoning as a fold or collapsed summary line.

        Fold-capable terminals receive an OSC-1337/OSC-133 foldable block;
        everything else gets a single dark-gray summary line.
        """
        if not self._reasoning_buffer:
            return
        text = "".join(self._reasoning_buffer)
        if self._is_iterm:
            sys.stdout.write(
                f"{_OSC1337}Block=id=thinking;attr=start{_BEL}{text}"
                f"{_OSC1337}UpdateBlock=id=thinking;action=fold{_BEL}"
                f"{_OSC1337}Block=id=thinking;attr=end{_BEL}\n"
            )
            sys.stdout.flush()
        elif self._is_wt:
            sys.stdout.write(f"{_OSC133}C{_BEL}{text}{_OSC133}D{_BEL}\n")
            sys.stdout.flush()
        else:
            console.print(
                f"\n\u25b8 Thinking: {len(text)} chars (collapsed)", style="#808080"
            )
        self._reasoning_buffer.clear()

    def _stream_thinking_live(self, reasoning: str) -> None:
        """Stream a reasoning delta live in dark gray."""
        if not self._live_started:
            console.print("\u25b8 Thinking:", style="#808080")
            self._live_started = True
        # stdout is block-buffered on pipes and line-buffered (not delta-
        # buffered) on TTYs; reasoning arrives as many tiny deltas with no
        # newlines, so without an explicit flush it sits in the buffer until
        # the answer phase flushes -- i.e. the entire thinking phase renders
        # as one burst at the end instead of streaming live.
        sys.stdout.write(f"{_GRAY_ON}{reasoning}{_RESET}")
        sys.stdout.flush()

    def _separate_before_answer(self) -> None:
        """Terminate a live reasoning stream before the answer is written."""
        if self._live_started:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._live_started = False

    def emit(self, content: str, reasoning: str) -> None:
        """Emit one (content, reasoning) chunk from the stream queue.

        Args:
            content: Answer text delta (may be empty).
            reasoning: Thinking/reasoning delta (may be empty).
        """
        if reasoning:
            if self.live_thinking:
                self._stream_thinking_live(reasoning)
            else:
                self._reasoning_buffer.append(reasoning)
            return
        self._flush_buffered_thinking()
        self._separate_before_answer()
        if content:
            sys.stdout.write(content)
            sys.stdout.flush()
            self.wrote_content = True

    def finish(self) -> None:
        """Flush trailing reasoning/state and terminate the answer line."""
        self._flush_buffered_thinking()
        self._separate_before_answer()
        if self.wrote_content:
            sys.stdout.write("\n")
            sys.stdout.flush()


def _wait_for_first_token(
    chunk_queue: queue.Queue[tuple[str, str]],
    done_event: threading.Event,
    stream: _ThinkingStream,
) -> tuple[str, str] | None:
    """Block under the spinner until the first streamed token arrives.

    Args:
        chunk_queue: Queue fed by the background chat thread.
        done_event: Set by the background thread when it terminates.
        stream: Renderer providing ``live_thinking`` and reasoning buffering.

    Returns
    -------
        The first (content, reasoning) token, or ``None`` when the chat
        finished without streaming anything.
    """
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
                # Lift the spinner as soon as any token (incl. reasoning) arrives
                # so a thinking-model chat is never stuck on "Thinking..." while
                # it reasons in the background.
                if stream.live_thinking:
                    first_token = token
                else:
                    stream.buffer_reasoning(reasoning)
                    first_token = ("", reasoning)
                continue
            first_token = token
    return first_token


def _drain_chunk_queue(
    chunk_queue: queue.Queue[tuple[str, str]],
    done_event: threading.Event,
    stream: _ThinkingStream,
) -> None:
    """Stream remaining (content, reasoning) chunks until the chat is done.

    Args:
        chunk_queue: Queue fed by the background chat thread.
        done_event: Set by the background thread when it terminates.
        stream: Renderer used to emit each chunk.
    """
    while not done_event.is_set() or not chunk_queue.empty():
        with contextlib.suppress(queue.Empty):
            stream.emit(*chunk_queue.get(timeout=0.1))


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

    stream = _ThinkingStream()
    first_token = _wait_for_first_token(chunk_queue, done_event, stream)
    if first_token is not None:
        stream.emit(*first_token)
    _drain_chunk_queue(chunk_queue, done_event, stream)
    stream.finish()

    t.join()

    # Propagate any exception that occurred in the background thread.
    if "error" in result_container:
        raise result_container["error"]

    result: dict[str, Any] = result_container.get("result", {})

    # Non-streaming path: no content streamed through the callback, but the
    # answer is in result["answer"].
    if not stream.wrote_content and result.get("answer"):
        sys.stdout.write(result["answer"])
        sys.stdout.flush()

    return result


def _print_chat_sources(result: dict[str, Any]) -> None:
    """Print the source chunks attached to a chat result, if any.

    Args:
        result: Chat result dict; prints nothing without a non-empty
            ``sources`` list.
    """
    if not result.get("sources"):
        return

    console.print("\n[bold blue]Sources:[/bold blue]")
    for i, chunk in enumerate(result["sources"], 1):
        source_file = chunk.get("source_file", chunk.get("source", "unknown"))
        page = chunk.get("page", chunk.get("page_number", "unknown"))
        score = chunk.get("score", 0)
        chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
        if len(chunk_text) > 200:
            chunk_text = chunk_text[:200] + "..."
        console.print(
            f"  [{i}] {source_file} (page {page}, score: {score:.4f}): {chunk_text}"
        )


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

    if show_sources:
        _print_chat_sources(result)


def _ensure_interactive_session(
    session: str | None,
    storage: Any,
    cfg: Any,
) -> Any:
    """Create or load the conversation session for interactive chat.

    Args:
        session: Session ID to resume, or ``None`` to create a new session.
        storage: Open ``ConversationStorage`` context.
        cfg: Application configuration providing the context window size.

    Returns
    -------
        The active ``ConversationSession``.
    """
    from secondbrain.conversation import ConversationSession

    if session is None:
        session_obj = ConversationSession.create(
            storage=storage, context_window=cfg.rag_context_window
        )
        console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
        return session_obj

    loaded = ConversationSession.load(
        session, storage, context_window=cfg.rag_context_window
    )
    if loaded is not None:
        if not loaded.is_empty:
            console.print(
                f"[dim]Resuming session with {loaded.message_count} messages[/dim]"
            )
        return loaded

    session_obj = ConversationSession.create(
        session, storage, context_window=cfg.rag_context_window
    )
    console.print(f"[dim]Created new session: {session_obj.session_id}[/dim]")
    return session_obj


def _handle_slash_command(
    user_input: str,
    session_obj: Any,
    chat_history: list[str],
    history_file: Path,
) -> bool:
    """Handle a ``/command`` entered in interactive chat.

    Args:
        user_input: Raw user input (starts with ``/``).
        session_obj: Active conversation session.
        chat_history: In-session list of user inputs.
        history_file: Path of the persisted readline history file.

    Returns
    -------
        ``True`` when the command requests exiting the REPL (``/quit``),
        ``False`` to continue the chat loop.
    """
    command = user_input.lower()
    if command == "/quit" or command == "/exit":
        console.print("[dim]Goodbye![/dim]")
        return True
    if command == "/clear":
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
        return False
    if command == "/help":
        console.print("[bold]Commands:[/bold]")
        console.print("  /quit     Exit the chat")
        console.print("  /clear    Clear conversation history")
        console.print("  /help     Show this help")
        return False
    console.print(f"[yellow]Unknown command: {user_input}[/yellow]")
    return False


def _persist_chat_history(user_input: str, history_file: Path) -> None:
    """Append the user input to the persisted chat history (best effort).

    Args:
        user_input: User input to persist.
        history_file: Path of the persisted chat history file.
    """
    try:
        with history_file.open("a") as f:
            f.write(user_input + "\n")
        readline.write_history_file(history_file)
    except OSError as exc:
        # History persistence is best-effort; log instead of failing the session.
        logger.debug("Failed to persist chat history to %s: %s", history_file, exc)


def _interactive_chat(
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
) -> None:
    """Handle interactive REPL mode for chat."""
    from secondbrain.conversation import ConversationStorage
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
        session_obj = _ensure_interactive_session(session, storage, cfg)

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
            except KeyboardInterrupt, EOFError:
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if _handle_slash_command(
                    user_input, session_obj, chat_history, history_file
                ):
                    break
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

            if show_sources:
                _print_chat_sources(result)

            # Save to history
            chat_history.append(user_input)
            _persist_chat_history(user_input, history_file)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
