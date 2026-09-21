"""Coverage extension tests for AnthropicLLMProvider.

Targets uncovered branches: sync generate() error mapping, async generate()
generic error handler, configuration properties, and streaming paths
(sync and async) including error branches.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import APIConnectionError, APIError

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.providers.anthropic import AnthropicLLMProvider

API_KEY_ENV = {"SECONDBRAIN_ANTHROPIC_API_KEY": "test-key"}
CLOSED_MESSAGE = "has been closed"


def _stream_event(text: str | None = None, thinking: str | None = None):
    """Build a content_block_delta stream event with the requested delta."""
    event = MagicMock()
    event.type = "content_block_delta"
    if text is not None:
        event.delta.text = text
    else:
        del event.delta.text
    if thinking is not None:
        event.delta.thinking = thinking
    else:
        del event.delta.thinking
    return event


def _non_delta_event():
    """Build a stream event that is not a content_block_delta."""
    event = MagicMock()
    event.type = "message_start"
    del event.delta
    return event


def _chunks_of(on_chunk: MagicMock) -> list[tuple[str, str | None]]:
    """Extract (text, thinking) tuples recorded by a streaming callback."""
    return [(call.args[0], call.args[1]) for call in on_chunk.call_args_list]


class TestGenerateErrorMapping:
    """Tests for sync generate() exception conversion."""

    def test_generate_api_connection_error_raises_service_unavailable(self):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = APIConnectionError(
                    request=MagicMock()
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(
                    ServiceUnavailableError, match="Anthropic API unreachable"
                ):
                    provider.generate("Test")

    def test_generate_unexpected_error_raises_runtime_error(self):
        """Test that a non-API exception raises RuntimeError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = ValueError("boom")
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(RuntimeError, match="Generation failed"):
                    provider.generate("Test")

    def test_generate_empty_content_returns_empty_string(self):
        """Test that an empty content list maps to an empty string."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = []
                mock_client = MagicMock()
                mock_client.messages.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                response = provider.generate("Test")

                assert response == ""


class TestAgenerateErrorMapping:
    """Tests for async agenerate() exception conversion."""

    @pytest.mark.asyncio
    async def test_agenerate_unexpected_error_raises_runtime_error(self):
        """Test that a non-API exception raises RuntimeError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=ValueError("boom"))
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(RuntimeError, match="Async generation failed"):
                    await provider.agenerate("Test")

    @pytest.mark.asyncio
    async def test_agenerate_empty_content_returns_empty_string(self):
        """Test that an empty content list maps to an empty string."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.content = []
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                response = await provider.agenerate("Test")

                assert response == ""


class TestProviderProperties:
    """Tests for configuration property accessors."""

    def test_properties_return_constructor_values(self):
        """Test that properties expose the configured values."""
        with patch.dict(os.environ, API_KEY_ENV):
            with (
                patch("secondbrain.rag.providers.anthropic.Anthropic"),
                patch("secondbrain.rag.providers.anthropic.AsyncAnthropic"),
            ):
                provider = AnthropicLLMProvider(
                    model="claude-custom",
                    temperature=0.3,
                    max_tokens=2048,
                    timeout=45,
                )

                assert provider.model == "claude-custom"
                assert provider.temperature == 0.3
                assert provider.max_tokens == 2048
                assert provider.timeout == 45


class TestStreamChat:
    """Tests for sync stream_chat()."""

    def test_stream_chat_streams_text_and_thinking(self):
        """Test streaming collects text deltas and fires callback."""
        events = [
            _stream_event(text="Hello "),
            _non_delta_event(),
            _stream_event(text="world", thinking="reason"),
            _stream_event(thinking="more"),
        ]
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = iter(events)
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                on_chunk = MagicMock()

                result = provider.stream_chat(
                    [{"role": "user", "content": "Test"}], on_chunk
                )

        assert result == "Hello world"
        assert _chunks_of(on_chunk) == [
            ("Hello ", None),
            ("world", None),
            ("", "reason"),
            ("", "more"),
        ]
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["messages"] == [{"role": "user", "content": "Test"}]

    def test_stream_chat_uses_custom_params(self):
        """Test streaming passes overrides through to the client."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.return_value = iter(
                    [_stream_event(text="ok")]
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                provider.stream_chat(
                    [{"role": "user", "content": "Test"}],
                    MagicMock(),
                    temperature=0.2,
                    max_tokens=99,
                )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["max_tokens"] == 99
        assert call_kwargs["top_p"] == 0.95

    def test_stream_chat_after_close_raises_runtime_error(self):
        """Test that stream_chat raises RuntimeError after close()."""
        provider = AnthropicLLMProvider(api_key="test-key")
        provider.close()

        with pytest.raises(RuntimeError, match=CLOSED_MESSAGE):
            provider.stream_chat([{"role": "user", "content": "Test"}], MagicMock())

    def test_stream_chat_connection_error_raises_service_unavailable(self):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = APIConnectionError(
                    request=MagicMock()
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                on_chunk = MagicMock()

                with pytest.raises(
                    ServiceUnavailableError, match="Anthropic API unreachable"
                ):
                    provider.stream_chat(
                        [{"role": "user", "content": "Test"}], on_chunk
                    )

    def test_stream_chat_api_error_raises_service_unavailable(self):
        """Test that APIError raises ServiceUnavailableError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = APIError(
                    message="API Error", request=MagicMock(), body={}
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(
                    ServiceUnavailableError, match="Anthropic API error"
                ):
                    provider.stream_chat(
                        [{"role": "user", "content": "Test"}], MagicMock()
                    )

    def test_stream_chat_unexpected_error_raises_runtime_error(self):
        """Test that a non-API exception raises RuntimeError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.Anthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create.side_effect = ValueError("boom")
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(RuntimeError, match="Streaming failed"):
                    provider.stream_chat(
                        [{"role": "user", "content": "Test"}], MagicMock()
                    )


class TestStreamChatAsync:
    """Tests for async stream_chat_async()."""

    def _async_stream_client(self, events: list) -> MagicMock:
        """Build a mocked AsyncAnthropic client streaming the given events."""

        async def _event_stream():
            for event in events:
                yield event

        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=_event_stream())
        return mock_client

    @pytest.mark.asyncio
    async def test_stream_chat_async_streams_text_and_thinking(self):
        """Test async streaming collects text deltas and fires callback."""
        events = [
            _stream_event(text="alpha"),
            _non_delta_event(),
            _stream_event(text="beta", thinking="why"),
            _stream_event(thinking="because"),
        ]
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = self._async_stream_client(events)
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                on_chunk = MagicMock()

                result = await provider.stream_chat_async(
                    [{"role": "user", "content": "Test"}], on_chunk
                )

        assert result == "alphabeta"
        assert _chunks_of(on_chunk) == [
            ("alpha", None),
            ("beta", None),
            ("", "why"),
            ("", "because"),
        ]
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["messages"] == [{"role": "user", "content": "Test"}]

    @pytest.mark.asyncio
    async def test_stream_chat_async_custom_params(self):
        """Test async streaming passes overrides through to the client."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = self._async_stream_client([_stream_event(text="ok")])
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()
                await provider.stream_chat_async(
                    [{"role": "user", "content": "Test"}],
                    AsyncMock(),
                    temperature=0.4,
                    max_tokens=77,
                )

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.4
        assert call_kwargs["max_tokens"] == 77

    @pytest.mark.asyncio
    async def test_stream_chat_async_after_aclose_raises_runtime_error(self):
        """Test that stream_chat_async raises RuntimeError after aclose()."""
        provider = AnthropicLLMProvider(api_key="test-key")
        await provider.aclose()

        with pytest.raises(RuntimeError, match=CLOSED_MESSAGE):
            await provider.stream_chat_async(
                [{"role": "user", "content": "Test"}], AsyncMock()
            )

    @pytest.mark.asyncio
    async def test_stream_chat_async_connection_error_raises_service_unavailable(
        self,
    ):
        """Test that APIConnectionError raises ServiceUnavailableError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(
                    side_effect=APIConnectionError(request=MagicMock())
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(
                    ServiceUnavailableError, match="Async streaming failed"
                ):
                    await provider.stream_chat_async(
                        [{"role": "user", "content": "Test"}], AsyncMock()
                    )

    @pytest.mark.asyncio
    async def test_stream_chat_async_api_error_raises_service_unavailable(self):
        """Test that APIError raises ServiceUnavailableError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(
                    side_effect=APIError(
                        message="API Error", request=MagicMock(), body={}
                    )
                )
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(
                    ServiceUnavailableError, match="Async streaming error"
                ):
                    await provider.stream_chat_async(
                        [{"role": "user", "content": "Test"}], AsyncMock()
                    )

    @pytest.mark.asyncio
    async def test_stream_chat_async_unexpected_error_raises_runtime_error(self):
        """Test that a non-API exception raises RuntimeError."""
        with patch.dict(os.environ, API_KEY_ENV):
            with patch(
                "secondbrain.rag.providers.anthropic.AsyncAnthropic"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.messages.create = AsyncMock(side_effect=ValueError("boom"))
                mock_client_class.return_value = mock_client

                provider = AnthropicLLMProvider()

                with pytest.raises(RuntimeError, match="Async streaming failed"):
                    await provider.stream_chat_async(
                        [{"role": "user", "content": "Test"}], AsyncMock()
                    )
