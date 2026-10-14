"""Tests for LLM provider token-usage logging.

Each provider logs one structured record per completed generation with
``model``, ``prompt_tokens``, ``completion_tokens`` and ``total_tokens``
fields, per the archived conversational-RAG performance-monitoring claim.
These tests assert on the emitted log records (message text carries the
fields) and that generation results are unchanged.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from secondbrain.rag.providers.anthropic import AnthropicLLMProvider
from secondbrain.rag.providers.mock import (
    MOCK_COMPLETION_TOKENS,
    MOCK_PROMPT_TOKENS,
    MOCK_TOTAL_TOKENS,
    MockLLMProvider,
)
from secondbrain.rag.providers.openai import OpenAILLMProvider

API_KEY_ENV = {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}
OPENAI_KEY_ENV = {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}


def _usage_records(caplog, operation: str) -> list:
    """Return log records whose message is the provider's token-usage line."""
    needle = f"{operation} token usage:"
    return [r for r in caplog.records if needle in r.getMessage()]


def _parse_fields(message: str) -> dict[str, str]:
    """Extract the key=value fields from a token-usage log line."""
    fields: dict[str, str] = {}
    for part in message.split(": ", 1)[1].split(" "):
        if "=" in part:
            key, _, value = part.partition("=")
            fields[key] = value
    return fields


class TestOpenAIGenerateUsageLogging:
    """OpenAI generate()/agenerate() log usage from the response."""

    def _provider_with_response(
        self, usage: object | None
    ) -> tuple[OpenAILLMProvider, MagicMock]:
        provider = OpenAILLMProvider(api_key="direct-key")
        client = MagicMock()
        response = SimpleNamespace(
            usage=usage,
            choices=[SimpleNamespace(message=SimpleNamespace(content="the answer"))],
        )
        client.chat.completions.create.return_value = response
        provider._client = client
        return provider, client

    def test_generate_logs_usage_fields(self, caplog):
        provider, _client = self._provider_with_response(
            SimpleNamespace(prompt_tokens=120, completion_tokens=45, total_tokens=165)
        )
        with caplog.at_level(10):
            result = provider.generate("hello")
        assert result == "the answer"
        records = _usage_records(caplog, "completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["model"] == "gpt-4o-mini"
        assert fields["prompt_tokens"] == "120"
        assert fields["completion_tokens"] == "45"
        assert fields["total_tokens"] == "165"

    def test_generate_without_usage_logs_nothing(self, caplog):
        provider, _client = self._provider_with_response(None)
        with caplog.at_level(10):
            provider.generate("hello")
        assert _usage_records(caplog, "completion") == []

    @pytest.mark.asyncio
    async def test_agenerate_logs_usage_fields(self, caplog):
        provider = OpenAILLMProvider(api_key="direct-key")
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=7, completion_tokens=3, total_tokens=10
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content="async answer"))],
        )
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=response)
        provider._async_client = client
        with caplog.at_level(10):
            result = await provider.agenerate("hello")
        assert result == "async answer"
        records = _usage_records(caplog, "completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["prompt_tokens"] == "7"
        assert fields["completion_tokens"] == "3"
        assert fields["total_tokens"] == "10"


class TestOpenAIStreamUsageLogging:
    """OpenAI stream_chat() logs usage when the server streams a usage chunk."""

    def _provider_with_stream(self, chunks: list):
        provider = OpenAILLMProvider(api_key="direct-key")
        client = MagicMock()
        client.chat.completions.create.return_value = iter(chunks)
        provider._client = client
        return provider

    @staticmethod
    def _chunk(content: str, usage: object | None = None):
        delta = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)

    def test_stream_logs_usage_from_final_chunk(self, caplog):
        usage = SimpleNamespace(
            prompt_tokens=50, completion_tokens=80, total_tokens=130
        )
        chunks = [
            self._chunk("Hel", None),
            self._chunk("lo.", None),
            self._chunk("", usage),
        ]
        provider = self._provider_with_stream(chunks)
        with caplog.at_level(10):
            result = provider.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert result == "Hello."
        records = _usage_records(caplog, "streaming completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["prompt_tokens"] == "50"
        assert fields["completion_tokens"] == "80"
        assert fields["total_tokens"] == "130"

    def test_stream_without_usage_chunk_logs_nothing(self, caplog):
        chunks = [self._chunk("answer", None), self._chunk("", None)]
        provider = self._provider_with_stream(chunks)
        with caplog.at_level(10):
            result = provider.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert result == "answer"
        assert _usage_records(caplog, "streaming completion") == []


class TestAnthropicGenerateUsageLogging:
    """Anthropic generate()/agenerate() log input/output token usage."""

    def _provider_with_response(self, usage: object | None) -> AnthropicLLMProvider:
        provider = AnthropicLLMProvider(api_key="direct-key")
        client = MagicMock()
        response = SimpleNamespace(
            usage=usage,
            content=[SimpleNamespace(text="claude says hi")],
        )
        client.messages.create.return_value = response
        provider._client = client
        return provider

    def test_generate_logs_usage_fields(self, caplog):
        provider = self._provider_with_response(
            SimpleNamespace(input_tokens=64, output_tokens=128)
        )
        with caplog.at_level(10):
            result = provider.generate("hello")
        assert result == "claude says hi"
        records = _usage_records(caplog, "completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["model"] == "claude-3-sonnet-20240229"
        assert fields["prompt_tokens"] == "64"
        assert fields["completion_tokens"] == "128"
        # Anthropic reports no total; the provider derives input + output.
        assert fields["total_tokens"] == "192"

    def test_generate_without_usage_logs_nothing(self, caplog):
        provider = self._provider_with_response(None)
        with caplog.at_level(10):
            provider.generate("hello")
        assert _usage_records(caplog, "completion") == []

    @pytest.mark.asyncio
    async def test_agenerate_logs_usage_fields(self, caplog):
        provider = AnthropicLLMProvider(api_key="direct-key")
        response = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=5, output_tokens=7),
            content=[SimpleNamespace(text="async")],
        )
        client = MagicMock()
        client.messages.create = AsyncMock(return_value=response)
        provider._async_client = client
        with caplog.at_level(10):
            result = await provider.agenerate("hello")
        assert result == "async"
        records = _usage_records(caplog, "completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["prompt_tokens"] == "5"
        assert fields["completion_tokens"] == "7"
        assert fields["total_tokens"] == "12"


class TestAnthropicStreamUsageLogging:
    """Anthropic stream_chat() accumulates usage across stream events."""

    @staticmethod
    def _delta_event(text: str | None = None, thinking: str | None = None):
        event = SimpleNamespace(type="content_block_delta")
        if text is not None:
            event.delta = SimpleNamespace(text=text)
        elif thinking is not None:
            event.delta = SimpleNamespace(text=None, thinking=thinking)
        return event

    def _stream_provider(self, events: list) -> AnthropicLLMProvider:
        provider = AnthropicLLMProvider(api_key="direct-key")
        client = MagicMock()
        client.messages.create.return_value = iter(events)
        provider._client = client
        return provider

    def test_stream_logs_usage_from_events(self, caplog):
        events = [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=31, output_tokens=0)
                ),
            ),
            self._delta_event(text="Hello "),
            self._delta_event(text="world."),
            SimpleNamespace(
                type="message_delta", usage=SimpleNamespace(output_tokens=9)
            ),
        ]
        provider = self._stream_provider(events)
        with caplog.at_level(10):
            result = provider.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert result == "Hello world."
        records = _usage_records(caplog, "streaming completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["prompt_tokens"] == "31"
        assert fields["completion_tokens"] == "9"
        assert fields["total_tokens"] == "40"

    def test_stream_without_usage_events_logs_nothing(self, caplog):
        provider = self._stream_provider([self._delta_event(text="answer")])
        with caplog.at_level(10):
            result = provider.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert result == "answer"
        assert _usage_records(caplog, "streaming completion") == []

    @pytest.mark.asyncio
    async def test_stream_async_logs_usage(self, caplog):
        provider = AnthropicLLMProvider(api_key="direct-key")
        events = [
            SimpleNamespace(
                type="message_start",
                message=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=8, output_tokens=0)
                ),
            ),
            self._delta_event(text="done"),
            SimpleNamespace(
                type="message_delta", usage=SimpleNamespace(output_tokens=4)
            ),
        ]

        async def _event_stream():
            for event in events:
                yield event

        client = MagicMock()
        client.messages.create = AsyncMock(return_value=_event_stream())
        provider._async_client = client
        with caplog.at_level(10):
            result = await provider.stream_chat_async(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert result == "done"
        records = _usage_records(caplog, "streaming completion")
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["prompt_tokens"] == "8"
        assert fields["completion_tokens"] == "4"
        assert fields["total_tokens"] == "12"


class TestMockProviderUsageLogging:
    """Mock provider reports fixed usage so offline runs stay observable."""

    def test_generate_logs_fixed_usage(self, caplog):
        provider = MockLLMProvider(default_response="mock reply")
        with caplog.at_level(10):
            result = provider.generate("some prompt")
        assert "mock reply" in result
        records = [r for r in caplog.records if "token usage" in r.getMessage()]
        assert len(records) == 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["model"] == "mock"
        assert fields["prompt_tokens"] == str(MOCK_PROMPT_TOKENS)
        assert fields["completion_tokens"] == str(MOCK_COMPLETION_TOKENS)
        assert fields["total_tokens"] == str(MOCK_TOTAL_TOKENS)

    def test_response_map_match_logs_fixed_usage(self, caplog):
        provider = MockLLMProvider(response_map={"pricing": "pricing answer"})
        with caplog.at_level(10):
            result = provider.generate("what is the pricing")
        assert result == "pricing answer"
        records = [r for r in caplog.records if "token usage" in r.getMessage()]
        assert len(records) == 1

    def test_stream_chat_logs_usage_once(self, caplog):
        provider = MockLLMProvider(default_response="streamed mock answer")
        with caplog.at_level(10):
            result = provider.stream_chat(
                messages=[{"role": "user", "content": "hi"}],
                on_chunk=lambda content, reasoning: None,
            )
        assert "streamed mock answer" in result
        records = [r for r in caplog.records if "token usage" in r.getMessage()]
        assert len(records) == 1
        assert str(MOCK_TOTAL_TOKENS) in records[0].getMessage()


class TestRAGPipelineUsageLogging:
    """Each RAG response logs token usage through its provider."""

    def test_query_logs_token_usage_via_mock_provider(self, caplog):
        from secondbrain.rag.pipeline import RAGPipeline

        searcher = MagicMock()
        searcher.search.return_value = [
            {"chunk_text": "Some relevant context", "source_file": "a.pdf", "page": 1}
        ]
        pipeline = RAGPipeline(
            searcher=searcher,
            llm_provider=MockLLMProvider(default_response="A grounded answer."),
            top_k=5,
        )
        with caplog.at_level(10):
            result = pipeline.query("What is the pricing?")
        assert result["answer"]
        records = [r for r in caplog.records if "token usage" in r.getMessage()]
        assert len(records) >= 1
        fields = _parse_fields(records[0].getMessage())
        assert fields["model"] == "mock"
        assert fields["total_tokens"] == str(MOCK_TOTAL_TOKENS)
