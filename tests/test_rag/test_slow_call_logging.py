"""Slow-call WARNING tests for the LLM provider call sites.

Spec (service-observability, Slow-call WARNING logging): a slow LLM call
emits a WARNING naming the operation and elapsed time through the real
provider method, with the HTTP client stubbed. The threshold is set to a tiny
value via SECONDBRAIN_SLOW_CALL_SECONDS so no test waits on real latency.
"""

import logging
import time
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from secondbrain.rag.providers.anthropic import AnthropicLLMProvider
from secondbrain.rag.providers.openai import OpenAILLMProvider

SLOW_CALL_LOGGER = "secondbrain.logging.slow_call"


@pytest.fixture
def tiny_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slow-call threshold of 10 ms: any deliberate stall exceeds it."""
    monkeypatch.setenv("SECONDBRAIN_SLOW_CALL_SECONDS", "0.01")


def _stall(seconds: float) -> Callable[[], None]:
    def stall() -> None:
        time.sleep(seconds)

    return stall


def _stub_openai_client(provider: OpenAILLMProvider, create: Callable) -> None:
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _stub_openai_async_client(provider: OpenAILLMProvider, create: Callable) -> None:
    provider._async_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )


def _stub_anthropic_client(provider: AnthropicLLMProvider, create: Callable) -> None:
    provider._client = SimpleNamespace(messages=SimpleNamespace(create=create))


def _openai_response() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
        usage=None,
    )


def _anthropic_response() -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text="ok")], usage=None)


def _slow_call_records(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.name == SLOW_CALL_LOGGER]


class TestOpenAIProviderSlowCall:
    def test_generate_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = OpenAILLMProvider(api_key="test-key")

        def slow_create(**kwargs):
            time.sleep(0.05)
            return _openai_response()

        _stub_openai_client(provider, slow_create)

        with caplog.at_level(logging.WARNING):
            answer = provider.generate("hi")

        assert answer == "ok"
        records = _slow_call_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "operation=llm.generate" in message
        assert "target=gpt-4o-mini" in message
        assert "elapsed=" in message

    async def test_generate_async_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = OpenAILLMProvider(api_key="test-key")

        async def slow_create(**kwargs):
            time.sleep(0.05)
            return _openai_response()

        _stub_openai_async_client(provider, slow_create)

        with caplog.at_level(logging.WARNING):
            answer = await provider.generate_async("hi")

        assert answer == "ok"
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=llm.generate_async" in message

    def test_stream_chat_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = OpenAILLMProvider(api_key="test-key")
        chunks: list[str] = []

        def slow_stream(**kwargs):
            time.sleep(0.05)
            return iter(())

        _stub_openai_client(provider, slow_stream)

        with caplog.at_level(logging.WARNING):
            answer = provider.stream_chat(
                [{"role": "user", "content": "hi"}],
                lambda text, reasoning: chunks.append(text),
            )

        assert answer == ""
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=llm.stream_chat" in message
        assert "target=gpt-4o-mini" in message

    def test_fast_generate_stays_silent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Default (10 s) threshold: an instant stub emits no warning."""
        monkeypatch.delenv("SECONDBRAIN_SLOW_CALL_SECONDS", raising=False)
        provider = OpenAILLMProvider(api_key="test-key")
        _stub_openai_client(provider, lambda **kwargs: _openai_response())

        with caplog.at_level(logging.WARNING):
            answer = provider.generate("hi")

        assert answer == "ok"
        assert not _slow_call_records(caplog)


class TestAnthropicProviderSlowCall:
    def test_generate_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = AnthropicLLMProvider(api_key="test-key")

        def slow_create(**kwargs):
            time.sleep(0.05)
            return _anthropic_response()

        _stub_anthropic_client(provider, slow_create)

        with caplog.at_level(logging.WARNING):
            answer = provider.generate("hi")

        assert answer == "ok"
        records = _slow_call_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "operation=llm.generate" in message
        assert "target=claude-3-sonnet-20240229" in message

    async def test_agenerate_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = AnthropicLLMProvider(api_key="test-key")

        async def slow_create(**kwargs):
            time.sleep(0.05)
            return _anthropic_response()

        provider._async_client = SimpleNamespace(
            messages=SimpleNamespace(create=slow_create)
        )

        with caplog.at_level(logging.WARNING):
            answer = await provider.agenerate("hi")

        assert answer == "ok"
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=llm.generate_async" in message

    def test_stream_chat_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider = AnthropicLLMProvider(api_key="test-key")

        def slow_stream(**kwargs):
            time.sleep(0.05)
            return iter(())

        _stub_anthropic_client(provider, slow_stream)

        with caplog.at_level(logging.WARNING):
            answer = provider.stream_chat(
                [{"role": "user", "content": "hi"}],
                lambda text, reasoning: None,
            )

        assert answer == ""
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=llm.stream_chat" in message
