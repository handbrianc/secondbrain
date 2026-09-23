"""Tests for OpenAIEmbeddingProvider and remaining MockEmbeddingProvider gaps.

All OpenAI SDK clients are patched at the provider module, so no test ever
touches the network. Error branches map: openai.APITimeoutError and
APIConnectionError and openai.APIError -> ServiceUnavailableError, anything
else -> RuntimeError (openai 3.x / httpx2 transport).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx2
import pytest
from openai import APIConnectionError, APIError, APITimeoutError

import secondbrain.embedding.providers.openai as openai_mod
from secondbrain.embedding.mock import (
    MockEmbeddingGenerator,
    MockEmbeddingProvider,
    MockLocalEmbeddingGenerator,
)
from secondbrain.exceptions import ServiceUnavailableError


def _api_error(message: str) -> APIError:
    """Build a real openai.APIError whose .message the provider reads."""
    return APIError(message=message, request=MagicMock(), body=None)


def _response(items: list[tuple[int, list[float]]]) -> MagicMock:
    """Fake embeddings response: list of (index, embedding) pairs."""
    response = MagicMock()
    data = []
    for index, embedding in items:
        item = MagicMock()
        item.index = index
        item.embedding = embedding
        data.append(item)
    response.data = data
    return response


def _make_provider(**overrides: Any) -> tuple[Any, MagicMock, MagicMock]:
    """Build OpenAIEmbeddingProvider with mocked OpenAI/AsyncOpenAI clients.

    Returns (provider, sync_client, async_client); both clients are MagicMocks.
    """
    kwargs: dict[str, Any] = {
        "model": "m",
        "api_key": "sk-test",
        "timeout": 30,
        "dimensions": None,
    }
    kwargs.update(overrides)
    with (
        patch("secondbrain.embedding.providers.openai.OpenAI") as mock_openai,
        patch("secondbrain.embedding.providers.openai.AsyncOpenAI") as mock_async,
    ):
        provider = openai_mod.OpenAIEmbeddingProvider(**kwargs)
        sync_client = mock_openai.return_value
        async_client = mock_async.return_value
    return provider, sync_client, async_client


_ERROR_CASES: list[tuple[Callable[[], Exception], type[Exception], str]] = [
    (
        lambda: APIConnectionError(request=MagicMock()),
        ServiceUnavailableError,
        "unreachable",
    ),
    (
        lambda: APITimeoutError(request=MagicMock()),
        ServiceUnavailableError,
        "timed out after 30s",
    ),
    (lambda: _api_error("quota exceeded"), ServiceUnavailableError, "quota exceeded"),
    (lambda: ValueError("bad payload"), RuntimeError, "failed: bad payload"),
]
_ERROR_IDS = ["connect", "timeout", "api-error", "unexpected"]


class TestOpenAIProviderInit:
    def test_init_with_explicit_api_key_and_base(self) -> None:
        """Explicit key/base are forwarded to both clients."""
        with (
            patch("secondbrain.embedding.providers.openai.OpenAI") as mock_openai,
            patch("secondbrain.embedding.providers.openai.AsyncOpenAI") as mock_async,
        ):
            provider = openai_mod.OpenAIEmbeddingProvider(
                model="text-embedding-3-small",
                api_key="sk-test",
                api_base="https://api.example.com/v1",
                timeout=7,
                dimensions=512,
            )

        assert provider._model == "text-embedding-3-small"
        assert provider._api_key == "sk-test"
        assert provider._dimensions == 512
        expected = {
            "timeout": httpx2.Timeout(7),
            "api_key": "sk-test",
            "base_url": "https://api.example.com/v1",
            "default_query": {"drop_params": "true"},
        }
        mock_openai.assert_called_once_with(**expected)
        mock_async.assert_called_once_with(**expected)

    def test_init_env_var_api_key(self) -> None:
        """api_key falls back to SECONDBRAIN_EMBEDDING_API_KEY."""
        with (
            patch("secondbrain.embedding.providers.openai.OpenAI"),
            patch("secondbrain.embedding.providers.openai.AsyncOpenAI"),
            patch.dict("os.environ", {"SECONDBRAIN_EMBEDDING_API_KEY": "sk-env"}),
        ):
            provider = openai_mod.OpenAIEmbeddingProvider()

        assert provider._api_key == "sk-env"

    def test_init_placeholder_when_no_key_anywhere(self) -> None:
        """With no env key, clients get the no-auth-placeholder sentinel."""
        with (
            patch("secondbrain.embedding.providers.openai.OpenAI") as mock_openai,
            patch("secondbrain.embedding.providers.openai.AsyncOpenAI") as mock_async,
            patch.dict("os.environ", {}, clear=True),
        ):
            provider = openai_mod.OpenAIEmbeddingProvider()

        assert provider._api_key is None
        expected = {"timeout": httpx2.Timeout(120), "api_key": "no-auth-placeholder"}
        mock_openai.assert_called_once_with(**expected)
        mock_async.assert_called_once_with(**expected)


class TestOpenAIGenerate:
    def test_happy_path_passes_dimensions_for_3_series(self) -> None:
        """Generate returns data[0].embedding; dimensions sent for 3-* models."""
        provider, sync_client, async_client = _make_provider(
            model="text-embedding-3-small", dimensions=512
        )
        sync_client.embeddings.create.return_value = _response([(0, [0.1, 0.2])])

        result = provider.generate("hello")

        assert result == [0.1, 0.2]
        sync_client.embeddings.create.assert_called_once_with(
            input="hello", model="text-embedding-3-small", dimensions=512
        )
        async_client.embeddings.create.assert_not_called()

    def test_dimensions_omitted_for_non_3_series_model(self) -> None:
        """Custom models must not receive the dimensions kwarg."""
        provider, sync_client, _ = _make_provider(
            model="custom-embedder", dimensions=512
        )
        sync_client.embeddings.create.return_value = _response([(0, [1.0])])

        provider.generate("hello")

        assert sync_client.embeddings.create.call_args.kwargs == {
            "input": "hello",
            "model": "custom-embedder",
        }

    @pytest.mark.parametrize(
        ("exc_factory", "expected", "match"),
        _ERROR_CASES,
        ids=_ERROR_IDS,
    )
    def test_error_branches(
        self,
        exc_factory: Callable[[], Exception],
        expected: type[Exception],
        match: str,
    ) -> None:
        """Each failure mode maps to its documented exception type."""
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = exc_factory()

        with pytest.raises(expected, match=match):
            provider.generate("hello")


class TestOpenAIGenerateBatch:
    def test_empty_input_returns_empty(self) -> None:
        """generate_batch([]) short-circuits to [] without an API call."""
        provider, sync_client, _ = _make_provider()

        assert provider.generate_batch([]) == []
        sync_client.embeddings.create.assert_not_called()

    def test_all_whitespace_returns_empty_vectors(self) -> None:
        """Whitespace-only inputs yield one empty vector per input."""
        provider, sync_client, _ = _make_provider()

        result = provider.generate_batch(["", "   ", "\t\n"])

        assert result == [[], [], []]
        sync_client.embeddings.create.assert_not_called()

    def test_blank_inputs_filtered_from_api_call(self) -> None:
        """Blank inputs are dropped from the API payload but keep output slots."""
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.return_value = _response([(0, [0.1])])

        result = provider.generate_batch(["a", "", "b"])

        assert result == [[0.1]]
        assert sync_client.embeddings.create.call_args.kwargs["input"] == ["a", "b"]

    def test_result_sorted_by_response_index(self) -> None:
        """Out-of-order API responses are reordered to match input order."""
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.return_value = _response(
            [(2, [0.3]), (0, [0.1]), (1, [0.2])]
        )

        result = provider.generate_batch(["a", "b", "c"])

        assert result == [[0.1], [0.2], [0.3]]

    def test_dimensions_passed_for_3_series_model(self) -> None:
        """generate_batch sends dimensions for text-embedding-3-* models."""
        provider, sync_client, _ = _make_provider(
            model="text-embedding-3-large", dimensions=1024
        )
        sync_client.embeddings.create.return_value = _response([(0, [0.1])])

        provider.generate_batch(["a"])

        assert sync_client.embeddings.create.call_args.kwargs["dimensions"] == 1024

    @pytest.mark.parametrize(
        ("exc_factory", "expected", "match"),
        _ERROR_CASES,
        ids=_ERROR_IDS,
    )
    def test_error_branches(
        self,
        exc_factory: Callable[[], Exception],
        expected: type[Exception],
        match: str,
    ) -> None:
        """Each failure mode maps to its documented exception type."""
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = exc_factory()

        with pytest.raises(expected, match=match):
            provider.generate_batch(["a", "b"])


class TestOpenAIGenerateAsync:
    async def test_happy_path(self) -> None:
        """generate_async awaits the async client and returns the embedding."""
        provider, _, async_client = _make_provider(
            model="text-embedding-3-small", dimensions=256
        )
        async_client.embeddings.create = AsyncMock(
            return_value=_response([(0, [0.5, 0.6])])
        )

        result = await provider.generate_async("hello")

        assert result == [0.5, 0.6]
        async_client.embeddings.create.assert_awaited_once_with(
            input="hello", model="text-embedding-3-small", dimensions=256
        )

    async def test_dimensions_omitted_for_non_3_series_model(self) -> None:
        """Async path also skips the dimensions kwarg for custom models."""
        provider, _, async_client = _make_provider(
            model="custom-embedder", dimensions=256
        )
        async_client.embeddings.create = AsyncMock(return_value=_response([(0, [1.0])]))

        await provider.generate_async("hello")

        assert async_client.embeddings.create.call_args.kwargs == {
            "input": "hello",
            "model": "custom-embedder",
        }

    @pytest.mark.parametrize(
        ("exc_factory", "expected", "match"),
        _ERROR_CASES,
        ids=_ERROR_IDS,
    )
    async def test_error_branches(
        self,
        exc_factory: Callable[[], Exception],
        expected: type[Exception],
        match: str,
    ) -> None:
        """Each failure mode maps to its documented exception type."""
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(side_effect=exc_factory())

        with pytest.raises(expected, match=match):
            await provider.generate_async("hello")


class TestOpenAIGenerateBatchAsync:
    async def test_empty_input_returns_empty(self) -> None:
        """generate_batch_async([]) short-circuits to [] without an API call."""
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock()

        assert await provider.generate_batch_async([]) == []
        async_client.embeddings.create.assert_not_called()

    async def test_all_whitespace_returns_empty_vectors(self) -> None:
        """Whitespace-only inputs yield one empty vector per input."""
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock()

        result = await provider.generate_batch_async(["", "  "])

        assert result == [[], []]
        async_client.embeddings.create.assert_not_called()

    async def test_result_sorted_by_response_index(self) -> None:
        """Out-of-order API responses are reordered to match input order."""
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(
            return_value=_response([(2, [0.3]), (0, [0.1]), (1, [0.2])])
        )

        result = await provider.generate_batch_async(["a", "b", "c"])

        assert result == [[0.1], [0.2], [0.3]]
        _, kwargs = async_client.embeddings.create.call_args
        assert kwargs["input"] == ["a", "b", "c"]

    async def test_dimensions_passed_for_3_series_model(self) -> None:
        """generate_batch_async sends dimensions for text-embedding-3-* models."""
        provider, _, async_client = _make_provider(
            model="text-embedding-3-large", dimensions=1024
        )
        async_client.embeddings.create = AsyncMock(return_value=_response([(0, [0.1])]))

        await provider.generate_batch_async(["a"])

        assert async_client.embeddings.create.call_args.kwargs["dimensions"] == 1024

    @pytest.mark.parametrize(
        ("exc_factory", "expected", "match"),
        _ERROR_CASES,
        ids=_ERROR_IDS,
    )
    async def test_error_branches(
        self,
        exc_factory: Callable[[], Exception],
        expected: type[Exception],
        match: str,
    ) -> None:
        """Each failure mode maps to its documented exception type."""
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = AsyncMock(side_effect=exc_factory())

        with pytest.raises(expected, match=match):
            await provider.generate_batch_async(["a", "b"])


class TestOpenAILifecycle:
    def test_validate_connection_true_on_success(self) -> None:
        """validate_connection returns True when models.list() succeeds."""
        provider, sync_client, _ = _make_provider()

        assert provider.validate_connection() is True
        sync_client.models.list.assert_called_once_with()

    def test_validate_connection_false_on_error(self) -> None:
        """validate_connection returns False when the client raises."""
        provider, sync_client, _ = _make_provider()
        sync_client.models.list.side_effect = OSError("connection refused")

        assert provider.validate_connection() is False

    def test_close_nulls_sync_client(self) -> None:
        """close() suppresses client errors and sets _client to None."""
        provider, sync_client, _ = _make_provider()
        sync_client.close.side_effect = RuntimeError("already closed")

        provider.close()

        assert provider._client is None

    async def test_aclose_closes_both_clients_and_clears_key(self) -> None:
        """aclose() closes both clients and clears the stored API key."""
        provider, sync_client, async_client = _make_provider()
        sync_client.close.side_effect = RuntimeError("boom")
        async_client.close = AsyncMock()

        await provider.aclose()

        assert provider._client is None
        assert provider._async_client is None
        assert provider._api_key is None
        sync_client.close.assert_called_once_with()
        async_client.close.assert_awaited_once()


class TestMockEmbeddingProviderGaps:
    """Covers remaining uncovered lines in secondbrain.embedding.mock."""

    def test_generate_truncates_for_small_dimension(self) -> None:
        """Dimension below the 32-byte hash shrinks via the truncate branch."""
        provider = MockEmbeddingProvider(dimension=16)

        result = provider.generate("hello")

        assert len(result) == 16

    async def test_generate_async_matches_sync(self) -> None:
        """generate_async returns exactly what generate returns."""
        provider = MockEmbeddingProvider(dimension=64)

        assert await provider.generate_async("hello") == provider.generate("hello")

    async def test_generate_batch_async_delegates_to_batch(self) -> None:
        """generate_batch_async delegates to generate_batch."""
        provider = MockEmbeddingProvider(dimension=64)

        result = await provider.generate_batch_async(["a", "b"])

        assert result == provider.generate_batch(["a", "b"])
        assert all(len(emb) == 64 for emb in result)

    def test_validate_connection_always_true(self) -> None:
        """validate_connection is True regardless of the force flag."""
        provider = MockEmbeddingProvider()

        assert provider.validate_connection() is True
        assert provider.validate_connection(force=True) is True

    def test_close_is_noop_and_repeatable(self) -> None:
        """close() does nothing and can be called repeatedly."""
        provider = MockEmbeddingProvider()

        assert provider.close() is None
        provider.close()

    def test_aliases_point_at_provider_class(self) -> None:
        """Backward-compat aliases bind to MockEmbeddingProvider."""
        assert MockEmbeddingGenerator is MockEmbeddingProvider
        assert MockLocalEmbeddingGenerator is MockEmbeddingProvider
