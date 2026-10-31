"""Unit tests for chat support helpers: spinner, single-turn, interactive REPL."""

import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.cli.chat_helpers import (
    _intent_label,
    _interactive_chat,
    _run_chat_with_spinner,
    _single_turn_chat,
    _SpinnerGate,
    _ThinkingStream,
)
from secondbrain.rag.intent_parser import QueryIntent, StructuralIntentParser


class _FakeTty:
    """stdout double reporting isatty() so terminal-detection branches run."""

    def __init__(self):
        self.parts = []
        self.closed = False

    def isatty(self):
        return True

    def write(self, text):
        self.parts.append(text)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.parts)


class _FakePipeline:
    """Pipeline double that streams scripted (content, reasoning) chunks."""

    def __init__(self, chunks, result=None):
        self.chunks = list(chunks)
        self._result = result if result is not None else {"answer": "done"}
        self.chat_calls = []
        self.on_chunk = None

    def chat(self, query, session_obj, top_k=5, show_sources=False):
        self.chat_calls.append((query, session_obj, top_k, show_sources))
        self.on_chunk = self._on_chunk
        for content, reasoning in self.chunks:
            self._on_chunk(content, reasoning)
        return dict(self._result)

    # The spinner attaches itself as pipeline._on_chunk; mirror that here.
    def _on_chunk(self, content, reasoning):
        pass


def _run_spinner(pipeline, query="q"):
    return _run_chat_with_spinner(
        pipeline, query, MagicMock(), top_k=3, show_sources=False
    )


class TestRunChatWithSpinner:
    def test_streams_content_and_returns_result(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline([("Hello ", None), ("world", None)])
        result = _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert "Hello " in out
        assert "world" in out
        assert result == {"answer": "done"}
        assert pipeline.chat_calls == [("q", pipeline.chat_calls[0][1], 3, False)]

    def test_chat_receives_session_and_kwargs(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline([("hi", None)])
        session_obj = MagicMock()
        _run_chat_with_spinner(
            pipeline, "question", session_obj, top_k=7, show_sources=True
        )
        assert pipeline.chat_calls[0][0] == "question"
        assert pipeline.chat_calls[0][1] is session_obj
        assert pipeline.chat_calls[0][2] == 7
        assert pipeline.chat_calls[0][3] is True

    def test_show_thinking_disabled_buffers_then_collapses(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        pipeline = _FakePipeline(
            [("reason one ", "thinking..."), ("Answer text", None)]
        )
        result = _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert "Thinking:" in out
        assert "collapsed" in out
        assert "Answer text" in out
        assert result == {"answer": "done"}

    def test_show_thinking_live_streams_reasoning(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline([("step one ", "reason"), ("Final", None)])
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert "Thinking:" in out
        assert "reason" in out
        assert "Final" in out

    def test_iterm_app_folds_reasoning_block(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        fake = _FakeTty()
        monkeypatch.setattr(sys, "stdout", fake)
        pipeline = _FakePipeline([("silent reasoning", "hidden"), ("Answer", None)])
        _run_spinner(pipeline)
        out = fake.getvalue()
        # OSC-1337 fold markers must be present around the reasoning text.
        assert "\x1b]1337;" in out
        assert "hidden" in out
        assert "Answer" in out

    def test_wt_session_uses_osc133(self, monkeypatch):
        monkeypatch.delenv("TERM_PROGRAM", raising=False)
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        monkeypatch.setenv("WT_SESSION", "some-guid")
        fake = _FakeTty()
        monkeypatch.setattr(sys, "stdout", fake)
        pipeline = _FakePipeline([("wt reasoning", "hidden"), ("Answer", None)])
        _run_spinner(pipeline)
        out = fake.getvalue()
        assert "\x1b]133;C\x07" in out
        assert "\x1b]133;D\x07" in out
        assert "Answer" in out

    def test_non_streaming_result_answer_fallback(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        # No chunks pushed at all -> answer printed from result dict.
        pipeline = _FakePipeline([], result={"answer": "fallback answer"})
        result = _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert "fallback answer" in out
        assert result == {"answer": "fallback answer"}

    def test_pipeline_exception_is_propagated(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")

        class _ExplodingPipeline(_FakePipeline):
            def chat(self, query, session_obj, top_k=5, show_sources=False):
                self.chat_calls.append((query, session_obj, top_k, show_sources))
                raise RuntimeError("boom")

        pipeline = _ExplodingPipeline([])
        with pytest.raises(RuntimeError, match="boom"):
            _run_spinner(pipeline)

    def test_trailing_newline_after_content(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline([("answer body", None)])
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert out.rstrip("\n").endswith("answer body") or "answer body" in out
        assert out.endswith("\n")


class TestSingleTurnChat:
    def _patches(self, mock_pipeline):
        storage = MagicMock()
        storage.__enter__ = MagicMock(return_value=storage)
        storage.__exit__ = MagicMock(return_value=False)
        return [
            patch("secondbrain.conversation.ConversationStorage", return_value=storage),
            patch("secondbrain.conversation.ConversationSession"),
            patch("secondbrain.search.Searcher"),
            patch(
                "secondbrain.rag.providers.LLMProviderFactory.create_from_config",
                return_value=MagicMock(),
            ),
            patch("secondbrain.rag.RAGPipeline", return_value=mock_pipeline),
            patch(
                "secondbrain.rag.factory.create_query_rewriter",
                return_value=MagicMock(),
            ),
            patch("secondbrain.rag.intent_parser.StructuralIntentParser"),
        ]

    def test_single_turn_invokes_pipeline_and_prints_sources(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        mock_pipeline.chat.return_value = {
            "answer": "single turn answer",
            "sources": [
                {
                    "source_file": "book.pdf",
                    "page": 3,
                    "score": 0.9417,
                    "chunk_text": "x" * 250,
                }
            ],
        }
        patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            _single_turn_chat(
                query="what?",
                session="sess-1",
                top_k=4,
                temperature=0.2,
                model=None,
                show_sources=True,
            )
        out = capsys.readouterr().out
        assert "single turn answer" in out
        assert "Sources:" in out
        assert "book.pdf" in out
        # Each source line carries the similarity score, 4-decimal formatted
        # like cli/display.py's search output.
        assert "score: 0.9417" in out
        # Long chunk text is truncated to 200 chars + ellipsis.
        assert "..." in out
        assert mock_pipeline.chat.call_count == 1


class TestInteractiveChat:
    def _patches(self, mock_pipeline):
        storage = MagicMock()
        storage.__enter__ = MagicMock(return_value=storage)
        storage.__exit__ = MagicMock(return_value=False)
        session = MagicMock()
        session.is_empty = True
        session.message_count = 0
        return (
            storage,
            session,
            [
                patch(
                    "secondbrain.conversation.ConversationStorage", return_value=storage
                ),
                patch(
                    "secondbrain.conversation.ConversationSession",
                    **{
                        "create.return_value": session,
                        "load.return_value": None,
                    },
                ),
                patch("secondbrain.search.Searcher"),
                patch(
                    "secondbrain.rag.providers.LLMProviderFactory.create_from_config",
                    return_value=MagicMock(),
                ),
                patch("secondbrain.rag.RAGPipeline", return_value=mock_pipeline),
                patch(
                    "secondbrain.rag.factory.create_query_rewriter",
                    return_value=MagicMock(),
                ),
                patch("secondbrain.rag.intent_parser.StructuralIntentParser"),
            ],
        )

    def test_repl_quits_on_slash_quit(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        _storage, _session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=["/quit"]):
                _interactive_chat(
                    session="repl-sess",
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=False,
                )
        out = capsys.readouterr().out
        assert "Interactive Chat" in out
        assert "Goodbye!" in out
        mock_pipeline.chat.assert_not_called()

    def test_repl_runs_one_query_then_quit(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        mock_pipeline.chat.return_value = {"answer": "repl answer"}
        _storage, _session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=["what is up?", "/quit"]):
                _interactive_chat(
                    session=None,
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=False,
                )
        out = capsys.readouterr().out
        assert "repl answer" in out
        assert "Goodbye!" in out
        assert mock_pipeline.chat.call_count == 1

    def test_repl_help_and_clear(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        _storage, session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=["/help", "/clear", "/quit"]):
                _interactive_chat(
                    session="s",
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=False,
                )
        out = capsys.readouterr().out
        assert "Commands:" in out
        assert "Conversation history cleared" in out
        session.clear_history.assert_called_once()
        mock_pipeline.chat.assert_not_called()

    def test_repl_prints_sources_with_similarity_scores(self, monkeypatch, capsys):
        """Interactive-path source lines render the similarity score too."""
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        mock_pipeline.chat.return_value = {
            "answer": "repl answer",
            "sources": [
                {
                    "source_file": "notes.md",
                    "page": 2,
                    "score": 0.51234,
                    "chunk_text": "retrieved chunk body",
                }
            ],
        }
        _storage, _session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=["what is up?", "/quit"]):
                _interactive_chat(
                    session="s",
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=True,
                )
        out = capsys.readouterr().out
        assert "Sources:" in out
        assert "notes.md" in out
        assert "retrieved chunk body" in out
        # 4-decimal score formatting, consistent with cli/display.py:51.
        assert "score: 0.5123" in out
        assert mock_pipeline.chat.call_count == 1

    def test_repl_unknown_command_and_empty_input(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        _storage, _session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=["/nope", "", "/quit"]):
                _interactive_chat(
                    session="s",
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=False,
                )
        out = capsys.readouterr().out
        assert "Unknown command: /nope" in out
        assert "Goodbye!" in out
        mock_pipeline.chat.assert_not_called()

    def test_repl_eof_exits_cleanly(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        mock_pipeline = MagicMock()
        _storage, _session, patches = self._patches(mock_pipeline)
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            with patch("builtins.input", side_effect=EOFError):
                _interactive_chat(
                    session="s",
                    top_k=3,
                    temperature=0.2,
                    model=None,
                    show_sources=False,
                )
        out = capsys.readouterr().out
        assert "Goodbye!" in out


class TestThinkingStreamSeparators:
    """Reasoning elements separate from each other; the answer boundary holds.

    fix-summary-window-truncation F2: a reasoning emission arriving after a
    previous thinking element has closed gets a preceding blank-line
    separator, consecutive map-window groups (progress marker + thinking)
    render as distinct collapsed elements, and reasoning never glues into
    the answer stream.
    """

    def test_consecutive_collapsed_elements_get_separator(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        pipeline = _FakePipeline(
            [
                ("", "· window 1/50\n"),
                ("", "window one thinking"),
                ("", "· window 2/50\n"),
                ("", "the second window thinks here"),
                ("Answer A", None),
                ("Answer B", None),
            ]
        )
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        # One collapsed element per reasoning group...
        assert out.count("▸ Thinking:") == 2
        assert "▸ Thinking: 19 chars (collapsed)" in out
        assert "▸ Thinking: 29 chars (collapsed)" in out
        # ...separated from the closed previous element by a blank line...
        assert "· window 1/50\n\n\n▸ Thinking: 19 chars (collapsed)" in out
        assert "· window 2/50\n\n\n▸ Thinking: 29 chars (collapsed)" in out
        # ...with the progress markers as their own collapsed lines.
        assert "· window 1/50" in out
        assert "· window 2/50" in out
        assert "(collapsed)\n· window 2/50" in out
        # No reasoning glues into the answer stream.
        assert "window one thinking" not in out
        assert "the second window thinks here" not in out
        assert "Answer A" in out
        assert "Answer B" in out

    def test_first_thinking_element_renders_without_separator(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        pipeline = _FakePipeline([("", "only thinking"), ("Answer", None)])
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        # The first element renders exactly as before the change.
        assert out.startswith("\n▸ Thinking: 13 chars (collapsed)")
        assert "\n\n\n▸" not in out
        assert "Answer" in out

    def test_stream_direct_emits_separate_elements(self, monkeypatch, capsys):
        """Drive the renderer directly: a marker closes the open element."""
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        stream = _ThinkingStream()
        stream.emit("", "· window 1/50\n")
        stream.emit("", "window one thinking")
        stream.emit("", "· window 2/50\n")
        stream.emit("", "window two thinking")
        stream.emit("Answer", "")
        stream.finish()
        out = capsys.readouterr().out
        assert out.count("▸ Thinking:") == 2
        # Each marker closes the previous window's thinking element, which
        # then renders blank-line separated before the next marker.
        assert "· window 1/50\n\n\n▸ Thinking: 19 chars (collapsed)" in out
        assert "· window 2/50\n\n\n▸ Thinking: 19 chars (collapsed)" in out
        # The answer starts separated after the last element.
        assert "(collapsed)\nAnswer" in out
        assert "window one thinking" not in out
        assert "window two thinking" not in out

    def test_live_reasoning_elements_get_separator(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline(
            [
                ("", "first run"),
                ("Answer", None),
                ("", "second run"),
                ("More", None),
            ]
        )
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert out.count("▸ Thinking:") == 2
        # The second live run starts separated from the closed first one
        # instead of gluing onto the answer text.
        assert "\nAnswer\n▸ Thinking:" in out
        assert "More" in out

    def test_answer_boundary_fires_exactly_once(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline(
            [
                ("", "thought one"),
                ("", "thought two"),
                ("A", None),
                ("B", None),
                ("C", None),
            ]
        )
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        # Banner newline, the single answer-boundary newline, and the
        # trailing newline -- the boundary never fires per content chunk.
        assert out.count("\n") == 3
        assert "▸ Thinking:\n" in out
        assert "\nABC\n" in out

    def test_progress_marker_renders_in_live_mode(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline(
            [("", "· window 1/50\n"), ("", "window thinking"), ("Answer", None)]
        )
        _run_spinner(pipeline)
        out = capsys.readouterr().out
        assert "· window 1/50" in out
        assert "window thinking" in out
        assert "Answer" in out
        # marker line, separator, banner, answer boundary, trailing newline
        assert out.count("\n") == 5
        assert "· window 1/50\n\n▸ Thinking:" in out


class _FakeStatus:
    """Spinner double recording stop/start transitions."""

    def __init__(self):
        self.started = False
        self.stop_calls = 0
        self.start_calls = 0

    def stop(self):
        self.stop_calls += 1
        self.started = False

    def start(self):
        self.start_calls += 1
        self.started = True


class TestSpinnerGate:
    """Thread-safe spinner pause/resume (fix 3.2).

    With an active spinner the pause suppresses frames and the resume
    restores them; without one both are no-ops -- no exceptions, no
    deadlock, and no resurrected spinner after the lift.
    """

    def test_pause_suppresses_and_resume_restores_active_spinner(self):
        status = _FakeStatus()
        gate = _SpinnerGate()
        gate.bind(status)
        with gate.pause():
            # Frames are suppressed while the write runs...
            assert status.stop_calls == 1
            assert not status.started
        # ...and restored afterwards, exactly once.
        assert status.started
        assert status.start_calls == 1
        assert status.stop_calls == 1

    def test_nested_pauses_refcount_single_stop_start(self):
        status = _FakeStatus()
        gate = _SpinnerGate()
        gate.bind(status)
        with gate.pause():
            with gate.pause():
                assert status.stop_calls == 1
            # The inner resume must not resurrect while the outer pause holds.
            assert not status.started
        assert status.started
        assert status.start_calls == 1

    def test_pause_is_noop_without_active_spinner(self):
        gate = _SpinnerGate()
        with gate.pause():
            pass

    def test_pause_is_noop_after_unbind(self):
        status = _FakeStatus()
        gate = _SpinnerGate()
        gate.bind(status)
        gate.unbind()
        stops = status.stop_calls
        with gate.pause():
            pass
        assert status.stop_calls == stops
        assert status.start_calls == 0

    def test_unbind_during_pause_never_resurrects_spinner(self):
        status = _FakeStatus()
        gate = _SpinnerGate()
        gate.bind(status)
        with gate.pause():
            # The spinner lifts (unbind) while a pause is still held...
            gate.unbind()
            assert not status.started
        # ...so the late resume must not restart it over the answer.
        assert status.start_calls == 0
        assert not status.started

    def test_pause_swallows_display_errors(self):
        class _BrokenStatus:
            def stop(self):
                raise RuntimeError("dead display")

            def start(self):
                raise RuntimeError("dead display")

        gate = _SpinnerGate()
        gate.bind(_BrokenStatus())
        # stop/resume failures are logged and swallowed: no exception, no
        # deadlock, the chat write completes either way.
        with gate.pause():
            pass

    def test_gate_wraps_real_rich_status(self, capsys):
        from rich.console import Console

        console = Console()
        status = console.status("[bold cyan]Thinking...", spinner="dots")
        gate = _SpinnerGate()
        gate.bind(status)
        with status:
            assert status._live.is_started
            with gate.pause():
                assert not status._live.is_started
            assert status._live.is_started
        assert not status._live.is_started


class TestIntentLabel:
    """Intent progress label carries the parsed target (fix 3.3)."""

    def test_broad_coverage_label_with_chapter_target(self):
        decision = StructuralIntentParser().parse("tell me everything about chapter 15")
        assert decision.intent is QueryIntent.BROAD_COVERAGE
        assert decision.target == "15"
        assert _intent_label(decision) == "broad coverage · chapter 15"

    def test_broad_coverage_label_without_target(self):
        decision = StructuralIntentParser().parse("tell me everything about proxmox")
        assert decision.intent is QueryIntent.BROAD_COVERAGE
        assert decision.target is None
        assert _intent_label(decision) == "broad coverage"

    def test_unknown_intent_renders_general_query(self):
        decision = StructuralIntentParser().parse("what is the capital of france")
        assert decision.intent is QueryIntent.UNKNOWN
        assert _intent_label(decision) == "general query"

    def test_section_enumerate_does_not_inherit_target_label(self):
        decision = StructuralIntentParser().parse("list sections in chapter 4.5.6")
        # The parsed section target must not leak into a non-coverage label.
        assert decision.intent is QueryIntent.SECTION_ENUMERATE
        assert _intent_label(decision) == "section enumerate"

    def test_chapter_enumerate_label_unchanged(self):
        decision = StructuralIntentParser().parse("list all chapters")
        assert decision.intent is QueryIntent.CHAPTER_ENUMERATE
        assert _intent_label(decision) == "chapter enumerate"
