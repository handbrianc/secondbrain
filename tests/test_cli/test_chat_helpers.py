"""Unit tests for chat support helpers: spinner, single-turn, interactive REPL."""

import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from secondbrain.cli.chat_helpers import (
    _interactive_chat,
    _run_chat_with_spinner,
    _single_turn_chat,
)


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
