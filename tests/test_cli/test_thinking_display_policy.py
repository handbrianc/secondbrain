"""Reasoning display policy tests: collapsed default, opt-in live, flag wiring.

Task 3.1/3.2 of the ``fix-summary-fidelity`` change: reasoning is collapsed
by default (buffered, then rendered once as a fold or a one-line dark-gray
summary -- never streamed inline as answer content), full live reasoning is
opt-in, and the ``chat --show-thinking/--no-show-thinking`` flag wins over
the config value (which itself maps ``SECONDBRAIN_SHOW_THINKING``).
"""

from __future__ import annotations

import queue
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from secondbrain.cli import chat as chat_cmd
from secondbrain.cli import cli
from secondbrain.cli.chat_helpers import (
    _run_chat_with_spinner,
    _ThinkingStream,
    _wait_for_first_token,
)


class _FakePipeline:
    """Pipeline double that streams scripted (content, reasoning) chunks."""

    def __init__(self, chunks, result=None):
        self.chunks = list(chunks)
        self._result = result if result is not None else {"answer": "done"}
        self.chat_calls = []
        self.on_chunk = None

    def chat(self, query, session_obj, top_k=5, show_sources=False):
        self.chat_calls.append((query, session_obj, top_k, show_sources))
        for content, reasoning in self.chunks:
            self._on_chunk(content, reasoning)
        return dict(self._result)

    # The spinner attaches itself as pipeline._on_chunk; mirror that here.
    def _on_chunk(self, content, reasoning):
        pass


class TestCollapsedDefault:
    """Reasoning is collapsed unless explicitly opted in."""

    def test_default_collapsed_without_env(self, monkeypatch, capsys):
        monkeypatch.delenv("SECONDBRAIN_SHOW_THINKING", raising=False)
        stream = _ThinkingStream()
        assert stream.live_thinking is False
        stream.emit("", "secret chain of thought")
        # Buffered only: nothing streamed yet.
        assert stream._reasoning_buffer == ["secret chain of thought"]
        assert capsys.readouterr().out == ""
        stream.emit("Answer body", "")
        out = capsys.readouterr().out
        assert "\u25b8 Thinking: 23 chars (collapsed)" in out
        # The reasoning text itself never becomes answer content.
        assert "secret chain of thought" not in out
        assert "Answer body" in out

    def test_finish_collapses_reasoning_only_turn(self, monkeypatch, capsys):
        monkeypatch.delenv("SECONDBRAIN_SHOW_THINKING", raising=False)
        stream = _ThinkingStream()
        stream.emit("", "only thoughts")
        stream.finish()
        out = capsys.readouterr().out
        assert "Thinking:" in out
        assert "collapsed" in out
        assert "only thoughts" not in out

    def test_spinner_collapses_by_default(self, monkeypatch, capsys):
        monkeypatch.delenv("SECONDBRAIN_SHOW_THINKING", raising=False)
        pipeline = _FakePipeline([("", "hidden reasoning"), ("Answer text", None)])
        result = _run_chat_with_spinner(
            pipeline, "q", MagicMock(), top_k=3, show_sources=False
        )
        out = capsys.readouterr().out
        assert "collapsed" in out
        assert "hidden reasoning" not in out
        assert "Answer text" in out
        assert result == {"answer": "done"}


class TestOptInLive:
    """Explicit opt-in restores full live reasoning text in dark gray."""

    def test_env_opt_in_streams_live(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        stream = _ThinkingStream()
        assert stream.live_thinking is True
        stream.emit("", "live thought")
        out = capsys.readouterr().out
        assert "Thinking:" in out
        assert "live thought" in out
        stream.emit("Answer", "")
        out = capsys.readouterr().out
        assert "Answer" in out

    def test_spinner_opt_in_streams_live(self, capsys):
        pipeline = _FakePipeline([("", "visible reasoning"), ("Answer text", None)])
        _run_chat_with_spinner(
            pipeline,
            "q",
            MagicMock(),
            top_k=3,
            show_sources=False,
            show_thinking=True,
        )
        out = capsys.readouterr().out
        assert "visible reasoning" in out
        assert "Answer text" in out

    def test_param_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        assert _ThinkingStream(show_thinking=False).live_thinking is False
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        assert _ThinkingStream(show_thinking=True).live_thinking is True

    @pytest.mark.parametrize(
        "value,live",
        [
            ("0", False),
            ("false", False),
            ("no", False),
            ("off", False),
            ("OFF", False),
            ("1", True),
            ("true", True),
            ("yes", True),
            ("on", True),
            (" 1 ", True),
        ],
    )
    def test_lenient_env_parse(self, monkeypatch, value, live):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", value)
        assert _ThinkingStream().live_thinking is live


class TestFirstTokenBuffering:
    """The waiter must not pre-buffer the token the renderer will buffer."""

    def test_reasoning_first_token_not_prebuffered(self, monkeypatch):
        monkeypatch.delenv("SECONDBRAIN_SHOW_THINKING", raising=False)
        stream = _ThinkingStream()
        chunk_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        done_event = threading.Event()
        done_event.set()
        chunk_queue.put(("", "delta one"))
        token = _wait_for_first_token(chunk_queue, done_event)
        assert token == ("", "delta one")
        # Regression: the token is buffered exactly once -- by emit() below,
        # not once here and once there (which doubled the collapsed count).
        assert stream._reasoning_buffer == []
        stream.emit(*token)
        assert stream._reasoning_buffer == ["delta one"]


class TestShowThinkingConfigField:
    """SECONDBRAIN_SHOW_THINKING maps onto the config field."""

    def test_env_maps_to_config_field(self, monkeypatch):
        from secondbrain.config import Config

        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        assert Config().show_thinking is True
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "0")
        assert Config().show_thinking is False
        monkeypatch.delenv("SECONDBRAIN_SHOW_THINKING")
        assert Config().show_thinking is False


class TestChatFlagWiring:
    """The chat flag resolves over config and reaches both chat modes."""

    @pytest.fixture
    def calls(self, monkeypatch) -> dict[str, dict[str, Any]]:
        recorded: dict[str, dict[str, Any]] = {}

        def _fake_single(**kwargs):
            recorded["single"] = kwargs

        def _fake_interactive(**kwargs):
            recorded["interactive"] = kwargs

        monkeypatch.setattr(chat_cmd, "_single_turn_chat", _fake_single)
        monkeypatch.setattr(chat_cmd, "_interactive_chat", _fake_interactive)
        cfg = MagicMock()
        cfg.show_thinking = True
        monkeypatch.setattr(chat_cmd, "config", lambda: cfg)
        return recorded

    def test_flag_true_reaches_single_turn(self, calls):
        result = CliRunner().invoke(cli, ["chat", "some question", "--show-thinking"])
        assert result.exit_code == 0
        assert calls["single"]["show_thinking"] is True

    def test_flag_false_beats_config(self, calls):
        result = CliRunner().invoke(
            cli, ["chat", "some question", "--no-show-thinking"]
        )
        assert result.exit_code == 0
        assert calls["single"]["show_thinking"] is False

    def test_config_used_when_flag_omitted(self, calls):
        result = CliRunner().invoke(cli, ["chat", "some question"])
        assert result.exit_code == 0
        assert calls["single"]["show_thinking"] is True

    def test_interactive_mode_receives_flag(self, calls):
        result = CliRunner().invoke(cli, ["chat", "--show-thinking"])
        assert result.exit_code == 0
        assert calls["interactive"]["show_thinking"] is True

    def test_config_false_default_flows_through(self, monkeypatch):
        recorded: dict[str, dict[str, Any]] = {}
        monkeypatch.setattr(
            chat_cmd,
            "_single_turn_chat",
            lambda **kwargs: recorded.update(single=kwargs),
        )
        cfg = MagicMock()
        cfg.show_thinking = False
        monkeypatch.setattr(chat_cmd, "config", lambda: cfg)
        result = CliRunner().invoke(cli, ["chat", "some question"])
        assert result.exit_code == 0
        assert recorded["single"]["show_thinking"] is False


class TestSpinnerShowThinkingKwarg:
    """_run_chat_with_spinner forwards the policy to the renderer."""

    def test_kwarg_false_forces_collapsed_despite_env(self, monkeypatch, capsys):
        monkeypatch.setenv("SECONDBRAIN_SHOW_THINKING", "1")
        pipeline = _FakePipeline([("", "leaked reasoning"), ("Answer text", None)])
        _run_chat_with_spinner(
            pipeline,
            "q",
            MagicMock(),
            top_k=3,
            show_sources=False,
            show_thinking=False,
        )
        out = capsys.readouterr().out
        assert "collapsed" in out
        assert "leaked reasoning" not in out
        assert "Answer text" in out
