"""Chat support helpers: spinner, single-turn, and interactive chat."""

import contextlib
import logging
import os
import queue
import readline
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
from rich.console import Console
from rich.status import Status

from secondbrain.config import config

if TYPE_CHECKING:
    from secondbrain.rag.intent_parser import IntentDecision

logger = logging.getLogger(__name__)

console = Console(markup=True)

# Escape sequences used to fold buffered reasoning into collapsible terminal
# blocks (iTerm2 OSC-1337, Windows Terminal OSC-133 C/D).
_OSC1337 = "\x1b]1337;"
_OSC133 = "\x1b]133;"
_BEL = "\x07"
_GRAY_ON = "\x1b[38;2;128;128;128m"
_RESET = "\x1b[0m"

# The bounded map pass forwards one-line progress markers ("· window i/N")
# on the reasoning channel ahead of each summary window's stream
# (fix-summary-window-truncation D5).  The renderer treats such a marker as
# its own collapsed progress line and closes the thinking element before it,
# so consecutive windows render as distinct elements instead of gluing
# together.
_PROGRESS_MARKER_PREFIX = "·"


class _ThinkingStream:
    """Terminal output renderer for chat streaming with reasoning support.

    Encapsulates the terminal-capability detection (iTerm2 OSC-1337 and
    Windows Terminal OSC-133 fold protocols) and the reasoning/content
    emission state machine used by :func:`_run_chat_with_spinner`.

    Display policy: reasoning is collapsed by default -- buffered and
    rendered once as a fold or a one-line dark-gray summary, never streamed
    inline before the answer.  Full live reasoning text is opt-in only (the
    ``show_thinking`` argument, backed by the ``--show-thinking`` chat flag
    and ``SECONDBRAIN_SHOW_THINKING``).
    """

    def __init__(self, show_thinking: bool | None = None) -> None:
        """Resolve the reasoning display policy and reset stream state.

        Args:
            show_thinking: Opt-in full-text reasoning streaming.  ``None``
                falls back to a lenient read of ``SECONDBRAIN_SHOW_THINKING``
                (the environment is read directly rather than through the
                cached config, so tests and late env changes are honoured);
                unset means the collapsed default.
        """
        if show_thinking is None:
            raw = os.environ.get("SECONDBRAIN_SHOW_THINKING", "").strip().lower()
            show_thinking = raw not in ("", "0", "false", "no", "off")
        # Reasoning stays visibly distinct from the answer either way:
        # collapsed, it is buffered and emitted once as a dark-gray fold or
        # summary line; opted in, it streams live in dark gray under a
        # "▸ Thinking:" banner.  It is never written as plain answer content.
        #   - Fold-capable terminals (iTerm2 OSC-1337, Windows Terminal OSC-133
        #     C/D): reasoning is buffered and emitted once as a foldable block.
        #   - Other terminals (Ghostty, Linux, ...): reasoning buffers and
        #     collapses to a single dark-gray summary line.
        is_tty = sys.stdout.isatty()
        self._is_iterm = os.environ.get("TERM_PROGRAM") == "iTerm.app" and is_tty
        self._is_wt = bool(os.environ.get("WT_SESSION")) and is_tty
        self.live_thinking = show_thinking
        self._reasoning_buffer: list[str] = []
        self._live_started = False
        # Whether the last live reasoning write left an unterminated line
        # (reasoning deltas carry no newlines), so a following progress
        # marker can close the line instead of gluing onto it.
        self._live_line_open = False
        # Whether a reasoning element (fold block, collapsed summary, live
        # reasoning run, or progress marker) has already been rendered, so a
        # later reasoning emission starts with a separating blank line
        # instead of gluing onto the previous element or onto answer text.
        self._thinking_emitted = False
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
        self._separate_thinking_elements()
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
        self._thinking_emitted = True

    def _separate_thinking_elements(self) -> None:
        """Write a separating blank line before a later reasoning element.

        A reasoning emission that arrives after a previous thinking element
        has closed (a fold block, collapsed summary, live reasoning run, or
        progress marker was already rendered) starts on a separated element,
        so consecutive reasoning blocks -- e.g. one per map window -- stay
        visually distinct instead of gluing together.  The first element of
        a stream renders exactly as before.
        """
        if self._thinking_emitted:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def _stream_thinking_live(self, reasoning: str) -> None:
        """Stream a reasoning delta live in dark gray."""
        if not self._live_started:
            self._separate_thinking_elements()
            console.print("\u25b8 Thinking:", style="#808080")
            self._live_started = True
            self._thinking_emitted = True
        # stdout is block-buffered on pipes and line-buffered (not delta-
        # buffered) on TTYs; reasoning arrives as many tiny deltas with no
        # newlines, so without an explicit flush it sits in the buffer until
        # the answer phase flushes -- i.e. the entire thinking phase renders
        # as one burst at the end instead of streaming live.
        sys.stdout.write(f"{_GRAY_ON}{reasoning}{_RESET}")
        sys.stdout.flush()
        self._live_line_open = not reasoning.endswith("\n")

    def _is_progress_marker(self, reasoning: str) -> bool:
        """Return whether a reasoning delta is a one-line progress marker."""
        return reasoning.startswith(_PROGRESS_MARKER_PREFIX) and reasoning.endswith(
            "\n"
        )

    def _render_progress_marker(self, marker: str) -> None:
        """Render a reasoning-channel progress marker as its own element.

        Any buffered thinking element flushes first (closing the previous
        window's element), then the marker renders as a one-line collapsed
        element in dark gray; the reasoning that follows starts a fresh
        element.  Markers are reasoning-channel progress -- they never touch
        the answer/content stream.
        """
        self._flush_buffered_thinking()
        if self.live_thinking and self._live_line_open:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._live_line_open = False
        console.print(marker.rstrip("\n"), style="#808080")
        self._thinking_emitted = True

    def _separate_before_answer(self) -> None:
        """Terminate a live reasoning stream before the answer is written."""
        if self._live_started:
            sys.stdout.write("\n")
            sys.stdout.flush()
            self._live_started = False
            self._live_line_open = False

    def emit(self, content: str, reasoning: str) -> None:
        """Emit one (content, reasoning) chunk from the stream queue.

        Args:
            content: Answer text delta (may be empty).
            reasoning: Thinking/reasoning delta (may be empty).
        """
        if reasoning:
            if self._is_progress_marker(reasoning):
                self._render_progress_marker(reasoning)
            elif self.live_thinking:
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


class _SpinnerGate:
    """Thread-safe pause/resume for the chat spinner's live display.

    While the Rich spinner animates, any line the chat loop writes can
    interleave with its frames.  The gate wraps the active
    :class:`rich.status.Status`: :meth:`pause` stops the live display (the
    refresh thread stops, the spinner line is erased) for the duration of an
    emission, and leaving the context restarts it.  Both directions are
    no-ops when no spinner is bound, and a resume never resurrects a spinner
    whose context has already closed, so a first token racing a pause
    degrades to today's interleaving rather than leaving a spinner running
    over the answer.  Failures of an already-dead display are logged and
    swallowed: pausing must never break or hang the chat.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status: Status | None = None
        self._depth = 0
        self._paused = False

    def bind(self, status: Status) -> None:
        """Attach the gate to a spinner that is about to start."""
        with self._lock:
            self._status = status
            self._depth = 0
            self._paused = False

    def unbind(self) -> None:
        """Detach the gate; later pause/resume calls become no-ops.

        Idempotently stops the display as well, in case a racing resume
        restarted it after the spinner's own context had exited.
        """
        with self._lock:
            status = self._status
            self._status = None
            self._depth = 0
            self._paused = False
        if status is not None:
            try:
                status.stop()
            except Exception as exc:
                logger.debug("Failed to stop chat spinner on unbind: %s", exc)

    @contextlib.contextmanager
    def pause(self) -> Iterator[None]:
        """Suppress spinner frames until the enclosing write completes.

        Nested pauses are refcounted: only the outermost pause stops the
        display and only the last exit restarts it.
        """
        with self._lock:
            self._depth += 1
            status = self._status
            suppress = self._depth == 1 and status is not None and not self._paused
            if suppress:
                self._paused = True
        if suppress and status is not None:
            try:
                status.stop()
            except Exception as exc:
                logger.debug("Failed to pause chat spinner: %s", exc)
        try:
            yield
        finally:
            with self._lock:
                self._depth = max(self._depth - 1, 0)
                status = self._status
                restore = self._depth == 0 and self._paused and status is not None
                if restore:
                    self._paused = False
            if restore and status is not None:
                try:
                    status.start()
                except Exception as exc:
                    logger.debug("Failed to resume chat spinner: %s", exc)


def _wait_for_first_token(
    chunk_queue: queue.Queue[tuple[str, str]],
    done_event: threading.Event,
    gate: _SpinnerGate | None = None,
) -> tuple[str, str] | None:
    """Block under the spinner until the first streamed token arrives.

    Args:
        chunk_queue: Queue fed by the background chat thread.
        done_event: Set by the background thread when it terminates.
        gate: Spinner pause gate bound to the status for as long as the
            spinner is active, so the chat loop can suppress frames around
            its emissions; unbound (no-op) once the spinner lifts.

    Returns
    -------
        The first (content, reasoning) token, or ``None`` when the chat
        finished without streaming anything.
    """
    first_token: tuple[str, str] | None = None
    status = console.status("[bold cyan]Thinking...", spinner="dots")
    if gate is not None:
        gate.bind(status)
    try:
        with status:
            while first_token is None:
                try:
                    token = chunk_queue.get(timeout=0.1)
                except queue.Empty:
                    if done_event.is_set():
                        break
                    continue
                # Any token (including a reasoning-only one) lifts the spinner so
                # a thinking-model chat is never stuck on "Thinking..." while it
                # reasons in the background.  The token is replayed through
                # ``stream.emit()`` below -- which buffers collapsed reasoning --
                # so it must not be pre-buffered here: that would count the same
                # delta twice in the collapsed fold.
                first_token = token
    finally:
        if gate is not None:
            gate.unbind()
    return first_token


def _drain_chunk_queue(
    chunk_queue: queue.Queue[tuple[str, str]],
    done_event: threading.Event,
    stream: _ThinkingStream,
    gate: _SpinnerGate | None = None,
) -> None:
    """Stream remaining (content, reasoning) chunks until the chat is done.

    Args:
        chunk_queue: Queue fed by the background chat thread.
        done_event: Set by the background thread when it terminates.
        stream: Renderer used to emit each chunk.
        gate: Spinner pause gate taken around each emission so spinner
            frames never interleave with written lines (a no-op when the
            spinner is not active).
    """
    while not done_event.is_set() or not chunk_queue.empty():
        try:
            chunk = chunk_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if gate is None:
            stream.emit(*chunk)
        else:
            with gate.pause():
                stream.emit(*chunk)


def _run_chat_with_spinner(
    pipeline: Any,
    query: str,
    session_obj: Any,
    top_k: int,
    show_sources: bool,
    show_thinking: bool | None = None,
) -> dict[str, Any]:
    """Run chat with a Rich spinner that animates until streaming starts.

    Uses a background thread so the spinner can animate while the LLM
    generates its first response token.  All output is routed through a
    ``queue.Queue`` to avoid interleaving with Rich's Live display.
    The spinner is written to stderr so it never pollutes stdout.

    Args:
        pipeline: Pipeline whose ``chat`` runs in the background thread and
            whose ``_on_chunk`` callback feeds the queue.
        query: The user's question.
        session_obj: Active conversation session.
        top_k: Retrieval breadth passed through to the pipeline.
        show_sources: Whether the caller prints source chunks afterwards.
        show_thinking: Reasoning display policy forwarded to
            :class:`_ThinkingStream` (``None`` = its lenient env default).
    """
    chunk_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    done_event = threading.Event()
    gate = _SpinnerGate()

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

    stream = _ThinkingStream(show_thinking=show_thinking)
    first_token = _wait_for_first_token(chunk_queue, done_event, gate)
    if first_token is not None:
        with gate.pause():
            stream.emit(*first_token)
    _drain_chunk_queue(chunk_queue, done_event, stream, gate)
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


def _intent_label(decision: IntentDecision) -> str:
    """Render the "Detected intent" progress label for a parsed decision.

    Broad-coverage decisions append the parsed chapter target ("broad
    coverage · chapter 15") so live progress shows what the coverage run
    targets; other intents and target-less decisions render the bare label
    as before.
    """
    from secondbrain.rag.intent_parser import broad_coverage_target_label

    if decision.intent.name == "UNKNOWN":
        return "general query"
    label = decision.intent.name.lower().replace("_", " ")
    target = broad_coverage_target_label(decision)
    if target:
        label = f"{label} · {target}"
    return label


def _single_turn_chat(
    query: str,
    session: str | None,
    top_k: int,
    temperature: float,
    model: str | None,
    show_sources: bool,
    show_thinking: bool | None = None,
) -> None:
    """Handle single-turn chat with a query.

    Shows a thinking spinner until the first response token arrives,
    then streams subsequent tokens directly to the terminal.

    Args:
        query: The user's question.
        session: Session ID to use or create (``None`` = new session).
        top_k: Retrieval breadth.
        temperature: LLM sampling temperature.
        model: LLM model override.
        show_sources: Whether to print retrieved sources.
        show_thinking: Reasoning display policy forwarded to the renderer.
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
        f"\u25b6 Detected intent: {_intent_label(intent_result)}",
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
        show_thinking=show_thinking,
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
    show_thinking: bool | None = None,
) -> None:
    """Handle interactive REPL mode for chat.

    Args:
        session: Session ID to resume (``None`` = new session).
        top_k: Retrieval breadth.
        temperature: LLM sampling temperature.
        model: LLM model override.
        show_sources: Whether to print retrieved sources.
        show_thinking: Reasoning display policy forwarded to the renderer.
    """
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
                f"\u25b6 Detected intent: {_intent_label(intent_result)}",
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
                show_thinking=show_thinking,
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
