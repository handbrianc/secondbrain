"""Unit tests for OpenAILLMProvider module.

Tests cover initialization, generation, error handling, and configuration
for the OpenAI LLM provider implementation.
"""

import os
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIError

from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.providers.factory import LLMProviderFactory
from secondbrain.rag.providers.openai import OpenAILLMProvider


class TestOpenAILLMProviderInit:
    """Tests for OpenAILLMProvider initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch.dict(
            os.environ,
            {"SECONDBRAIN_OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAILLMProvider()

            assert provider._model == "gpt-4o-mini"
            assert provider._temperature == 1.0
            assert provider._top_p == 0.95
            assert provider._max_tokens == 384000
            assert provider._timeout == 120
            assert provider._api_key == "test-key"

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        with patch.dict(
            os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}, clear=True
        ):
            provider = OpenAILLMProvider(
                model="gpt-4",
                temperature=0.7,
                max_tokens=1024,
                timeout=60,
            )

            assert provider._model == "gpt-4"
            assert provider._temperature == 0.7
            assert provider._max_tokens == 1024
            assert provider._timeout == 60

    def test_init_with_api_key_parameter(self):
        """Test initialization with API key as parameter."""
        provider = OpenAILLMProvider(api_key="direct-api-key")

        assert provider._api_key == "direct-api-key"

    def test_init_without_api_key_raises_error(self):
        """Test that initialization fails without API key."""
        # Ensure no API key in environment
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OpenAI API key required"):
                OpenAILLMProvider()

    def test_init_creates_clients(self):
        """Test that clients are created during initialization."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_sync:
                with patch(
                    "secondbrain.rag.providers.openai.AsyncOpenAI"
                ) as mock_async:
                    mock_sync.return_value = MagicMock()
                    mock_async.return_value = MagicMock()

                    provider = OpenAILLMProvider()

                    mock_sync.assert_called_once()
                    mock_async.assert_called_once()
                    assert hasattr(provider, "_client")
                    assert hasattr(provider, "_async_client")


class TestOpenAILLMProviderGenerate:
    """Tests for OpenAILLMProvider.generate() method."""

    def test_generate_with_default_params(self):
        """Test generation with default temperature and max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Test response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test prompt")

                assert response == "Test response"
                mock_client.chat.completions.create.assert_called_once()

    def test_generate_with_custom_temperature(self):
        """Test generation with custom temperature."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test", temperature=0.8)

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.8

    def test_generate_with_custom_max_tokens(self):
        """Test generation with custom max_tokens."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = provider.generate("Test", max_tokens=512)

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["max_tokens"] == 512

    def test_generate_forwards_repetition_penalty_when_enabled(self):
        """Test that repetition_penalty is forwarded via extra_body when > 1.0."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(repetition_penalty=1.2)
                provider.generate("Test")

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["extra_body"] == {"repetition_penalty": 1.2}

    def test_generate_omits_repetition_penalty_by_default(self):
        """Test that no extra_body is sent when repetition_penalty is disabled (1.0)."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                provider.generate("Test")

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["extra_body"] is None

    def test_generate_uses_default_temperature_when_not_specified(self):
        """Test that default temperature is used when not specified."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create.return_value = mock_response
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(temperature=0.5)
                provider.generate("Test")

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.5

    def test_generate_raises_service_unavailable_on_api_error(self):
        """Test that APIError is converted to ServiceUnavailableError."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                mock_request = MagicMock()
                mock_client.chat.completions.create.side_effect = APIError(
                    message="API Error", request=mock_request, body={}
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(ServiceUnavailableError):
                    provider.generate("Test prompt")


class TestOpenAILLMProviderAGenerate:
    """Tests for OpenAILLMProvider agenerate_async method."""

    @pytest.mark.asyncio
    async def test_agenerate_async_success(self):
        """Test successful async generation."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch(
                "secondbrain.rag.providers.openai.AsyncOpenAI"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Test response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = await provider.generate_async("Test prompt")

                assert response == "Test response"

    @pytest.mark.asyncio
    async def test_agenerate_async_with_custom_params(self):
        """Test async generation with custom parameters."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch(
                "secondbrain.rag.providers.openai.AsyncOpenAI"
            ) as mock_client_class:
                mock_response = MagicMock()
                mock_response.choices = [
                    MagicMock(message=MagicMock(content="Response"))
                ]
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()
                response = await provider.generate_async(
                    "Test", temperature=0.8, max_tokens=512
                )

                call_kwargs = mock_client.chat.completions.create.call_args[1]
                assert call_kwargs["temperature"] == 0.8
                assert call_kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_agenerate_async_raises_service_unavailable_on_connect_error(self):
        """Test that ConnectError raises ServiceUnavailableError."""
        import httpx

        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch(
                "secondbrain.rag.providers.openai.AsyncOpenAI"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=httpx.ConnectError("Connection failed")
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(
                    ServiceUnavailableError, match="OpenAI API unreachable"
                ):
                    await provider.generate_async("Test prompt")

    @pytest.mark.asyncio
    async def test_agenerate_async_raises_service_unavailable_on_api_error(self):
        """Test that APIError raises ServiceUnavailableError."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch(
                "secondbrain.rag.providers.openai.AsyncOpenAI"
            ) as mock_client_class:
                mock_client = MagicMock()
                mock_request = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=APIError(
                        message="API Error", request=mock_request, body={}
                    )
                )
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider()

                with pytest.raises(ServiceUnavailableError, match="OpenAI API error"):
                    await provider.generate_async("Test prompt")


def _stream_chunk(
    content: str | None = None, reasoning: str | None = None
) -> SimpleNamespace:
    """Build a fake OpenAI-compatible streaming response chunk."""
    delta = SimpleNamespace(content=content, reasoning_content=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _distinct_reasoning(target_chars: int) -> str:
    """Build long, genuinely-distinct reasoning text (not a degenerate loop)."""
    random.seed(7)
    vocab = [
        "convolution",
        "filter",
        "kernel",
        "stride",
        "padding",
        "pooling",
        "relu",
        "dropout",
        "cnn",
        "imagenet",
        "layer",
        "activation",
        "vector",
        "attention",
        "transformer",
        "encoder",
        "decoder",
        "feature",
        "map",
        "downsampling",
        "weight",
        "sharing",
        "sparse",
        "connectivity",
        "momentum",
        "batch",
    ]
    parts: list[str] = []
    total = 0
    while total < target_chars:
        sentence = (
            " ".join(random.sample(vocab, 9))
            + f". attribute {len(parts)} measurement {random.randrange(1_000_000)}. "
        )
        parts.append(sentence)
        total += len(sentence)
    return "".join(parts)


class TestOpenAILLMProviderStreamReasoningCap:
    """Tests for the client-side reasoning budget in stream_chat."""

    def test_stream_chat_halts_runaway_reasoning_with_fallback(self):
        """When reasoning exceeds the budget with no answer, halt and emit fallback."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                chunks = [
                    _stream_chunk(reasoning="let me re-read the table again ")
                    for _ in range(50)
                ]
                mock_client.chat.completions.create.return_value = chunks
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=50)
                emitted: list[tuple[str, str | None]] = []
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: emitted.append((c, r)),
                )

                assert "reasoning budget" in result
                assert result == emitted[-1][0]

    def test_stream_chat_preserves_content_when_reasoning_capped(self):
        """When reasoning is capped after content started, keep the produced content."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                chunks = [
                    _stream_chunk(content="Here is the answer. "),
                    _stream_chunk(reasoning="x" * 100),
                ]
                mock_client.chat.completions.create.return_value = chunks
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=50)
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: None,
                )

                assert result == "Here is the answer. "
                assert "reasoning budget" not in result

    def test_stream_chat_within_reasoning_budget_returns_normally(self):
        """Reasoning under the budget does not halt the stream."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                chunks = [
                    _stream_chunk(reasoning="brief thought "),
                    _stream_chunk(content="final answer"),
                ]
                mock_client.chat.completions.create.return_value = chunks
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=8000)
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: None,
                )

                assert result == "final answer"

    def test_stream_chat_detects_near_exact_repetition_loop_early(self):
        """A repeating-reasoning loop is halted by the detector, well below the ceiling."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                phrase = "let me re-read the exact line from the prompt again "
                reasoning = phrase * 400  # ~20k chars of periodic (degenerate) reasoning
                chunks = [
                    _stream_chunk(reasoning=reasoning[i : i + 40])
                    for i in range(0, len(reasoning), 40)
                ]
                chunks.append(_stream_chunk(content="never reached"))
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=24000)
                emitted: list[tuple[str, str | None]] = []
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: emitted.append((c, r)),
                )

                reasoning_forwarded = sum(len(r) for _, r in emitted if r)
                assert "reasoning budget" in result
                assert reasoning_forwarded < 24000
                assert "never reached" not in "".join(
                    c for c, _ in emitted if c
                )

    def test_stream_chat_allows_long_distinct_reasoning(self):
        """Legitimate long reasoning (> the old 8k cap) must complete, not be cut."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                reasoning = _distinct_reasoning(12000)
                chunks = [
                    _stream_chunk(reasoning=reasoning[i : i + 40])
                    for i in range(0, len(reasoning), 40)
                ]
                chunks.append(_stream_chunk(content="FULL SUMMARY"))
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=24000)
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: None,
                )

                assert "reasoning budget" not in result
                assert result == "FULL SUMMARY"

    def test_stream_chat_halts_content_phase_spiral_early(self):
        """A content-channel self-correction spiral is halted instead of dangling."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                clean = _distinct_reasoning(1200)  # legit prose before the spiral
                spiral_unit = (
                    "Actually no the text says one percent wait it says two percent "
                )
                full = clean + spiral_unit * 250  # ~13k chars, mostly near-exact repeat
                chunks = [
                    _stream_chunk(content=full[i : i + 40])
                    for i in range(0, len(full), 40)
                ]
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=24000)
                emitted: list[tuple[str, str | None]] = []
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: emitted.append((c, r)),
                )

                content_forwarded = sum(len(c) for c, _ in emitted if c)
                assert "reasoning budget" not in result
                # The stream was terminated well before the ~13k chars of spiral.
                assert content_forwarded < len(full)

    def test_stream_chat_content_loop_preserves_clean_prefix(self):
        """On a content loop the returned answer is a bounded prefix, not the whole spiral."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                clean = _distinct_reasoning(2000)
                full = clean + ("rechecking the exact figure over and over again no " * 200)
                chunks = [
                    _stream_chunk(content=full[i : i + 40])
                    for i in range(0, len(full), 40)
                ]
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(max_reasoning_chars=24000)
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: None,
                )

                assert "reasoning budget" not in result
                assert len(result) < len(full)

    def test_stream_chat_answer_length_cap_stops_runaway(self):
        """Even a varied-runaway (no near-exact windows) is cut by the answer-length cap."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                # Distinct, non-repeating content far longer than the 8k answer cap:
                # the window-loop detector cannot fire, so only the length cap bounds it.
                content = _distinct_reasoning(20000)
                chunks = [
                    _stream_chunk(content=content[i : i + 40])
                    for i in range(0, len(content), 40)
                ]
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(
                    max_reasoning_chars=24000, max_answer_chars=8000
                )
                emitted: list[tuple[str, str | None]] = []
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: emitted.append((c, r)),
                )

                content_forwarded = sum(len(c) for c, _ in emitted if c)
                assert "reasoning budget" not in result
                # It ran past the window-detector cutoff (~4-5k) up to the 8k cap,
                # proving the length cap (not repetition detection) bounded it.
                assert 7000 <= content_forwarded <= 9000
                assert len(result) < len(content)

    def test_stream_chat_answer_cap_trims_at_sentence_boundary(self):
        """A capped answer stops at the last sentence end, never mid-word."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_client_class:
                mock_client = MagicMock()
                content = (
                    "Alpha beta gamma. Delta epsilon zeta. Eta theta iota. "
                    "Kappa lambda mu nu omitted here. "
                ) + ("Q" * 500)
                chunks = [
                    _stream_chunk(content=content[i : i + 40])
                    for i in range(0, len(content), 40)
                ]
                mock_client.chat.completions.create.return_value = iter(chunks)
                mock_client_class.return_value = mock_client

                provider = OpenAILLMProvider(
                    max_reasoning_chars=24000, max_answer_chars=120
                )
                result = provider.stream_chat(
                    messages=[{"role": "user", "content": "hi"}],
                    on_chunk=lambda c, r: None,
                )

                assert "Q" not in result, "capped answer must drop the unpunctuated tail"
                assert result.rstrip().endswith("."), "capped answer must end at a sentence"

    def test_stream_chat_cap_disabled_by_default(self):
        """max_reasoning_chars defaults to 0 (disabled) so reasoning is never capped."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            provider = OpenAILLMProvider()
            assert provider._max_reasoning_chars == 0


class TestLLMProviderFactoryReasoningCap:
    """Tests that the factory forwards llm_max_reasoning_chars to the provider."""

    def test_create_from_config_forwards_max_reasoning_chars(self):
        mock_config = MagicMock()
        mock_config.llm_provider = "openai"
        mock_config.llm_model = "deepseek-chat"
        mock_config.llm_temperature = 0.3
        mock_config.llm_top_p = 0.95
        mock_config.llm_max_tokens = 384000
        mock_config.llm_timeout = 120
        mock_config.openai_api_key = "k"
        mock_config.openai_base_url = None
        mock_config.llm_repetition_penalty = 1.0
        mock_config.llm_max_reasoning_chars = 9999
        mock_config.llm_stream_idle_timeout_seconds = 120
        mock_config.llm_max_answer_chars = 8000

        with patch("secondbrain.rag.providers.openai.OpenAILLMProvider") as mock_cls:
            LLMProviderFactory.create_from_config(mock_config)
            mock_cls.assert_called_once()
            assert mock_cls.call_args.kwargs["max_reasoning_chars"] == 9999
            assert mock_cls.call_args.kwargs["stream_idle_timeout_seconds"] == 120
            assert mock_cls.call_args.kwargs["max_answer_chars"] == 8000


class TestOpenAILLMProviderStreamIdleTimeout:
    """Tests for the bounded idle-timeout on streams."""

    def test_init_defaults_to_unlimited_read(self):
        """stream_idle_timeout_seconds defaults to 0 -> httpx read is unlimited."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_sync:
                with patch(
                    "secondbrain.rag.providers.openai.AsyncOpenAI"
                ) as mock_async:
                    mock_sync.return_value = MagicMock()
                    mock_async.return_value = MagicMock()
                    OpenAILLMProvider()
                    assert (
                        mock_sync.call_args.kwargs["timeout"].read is None
                    )

    def test_init_applies_idle_timeout_to_read(self):
        """A configured idle timeout is applied as the httpx read timeout."""
        with patch.dict(os.environ, {"SECONDBRAIN_OPENAI_API_KEY": "test-key"}):
            with patch("secondbrain.rag.providers.openai.OpenAI") as mock_sync:
                with patch(
                    "secondbrain.rag.providers.openai.AsyncOpenAI"
                ) as mock_async:
                    mock_sync.return_value = MagicMock()
                    mock_async.return_value = MagicMock()
                    OpenAILLMProvider(stream_idle_timeout_seconds=120)
                    assert (
                        mock_sync.call_args.kwargs["timeout"].read == 120
                    )
