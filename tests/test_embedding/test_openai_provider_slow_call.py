"""Slow-call WARNING tests for the OpenAI embedding provider call sites.

Spec (service-observability, Slow-call WARNING logging): a slow embedding
API call emits a WARNING naming the operation, target (model) and elapsed
time through the real provider method, with the OpenAI clients mocked. The
threshold is set to a tiny value via SECONDBRAIN_SLOW_CALL_SECONDS so no
test waits on real latency.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import secondbrain.embedding.providers.openai as openai_mod

SLOW_CALL_LOGGER = "secondbrain.logging.slow_call"


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


def _slow_call_records(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.name == SLOW_CALL_LOGGER]


@pytest.fixture
def tiny_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slow-call threshold of 10 ms: any deliberate stall exceeds it."""
    monkeypatch.setenv("SECONDBRAIN_SLOW_CALL_SECONDS", "0.01")


def _slow_sync_create(
    items: list[tuple[int, list[float]]],
) -> Callable[..., MagicMock]:
    def create(**kwargs: Any) -> MagicMock:
        time.sleep(0.05)
        return _response(items)

    return create


def _slow_async_create(
    items: list[tuple[int, list[float]]],
) -> AsyncMock:
    async def create(**kwargs: Any) -> MagicMock:
        await asyncio.sleep(0.05)
        return _response(items)

    return AsyncMock(side_effect=create)


class TestEmbeddingSlowCall:
    def test_generate_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = _slow_sync_create([(0, [0.1, 0.2])])

        with caplog.at_level(logging.WARNING):
            embedding = provider.generate("hello")

        assert embedding == [0.1, 0.2]
        records = _slow_call_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "operation=embedding.generate" in message
        assert "target=m" in message
        assert "elapsed=" in message

    def test_generate_batch_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = _slow_sync_create(
            [(0, [0.1]), (1, [0.2])]
        )

        with caplog.at_level(logging.WARNING):
            embeddings = provider.generate_batch(["a", "b"])

        assert embeddings == [[0.1], [0.2]]
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=embedding.generate_batch" in message

    async def test_generate_async_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = _slow_async_create([(0, [0.3])])

        with caplog.at_level(logging.WARNING):
            embedding = await provider.generate_async("hello")

        assert embedding == [0.3]
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=embedding.generate_async" in message

    async def test_generate_batch_async_over_threshold_warns(
        self, tiny_threshold: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        provider, _, async_client = _make_provider()
        async_client.embeddings.create = _slow_async_create([(0, [0.4]), (1, [0.5])])

        with caplog.at_level(logging.WARNING):
            embeddings = await provider.generate_batch_async(["a", "b"])

        assert embeddings == [[0.4], [0.5]]
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=embedding.generate_batch_async" in message

    def test_fast_generate_stays_silent(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Default (10 s) threshold: an instant mock emits no warning."""
        monkeypatch.delenv("SECONDBRAIN_SLOW_CALL_SECONDS", raising=False)
        provider, sync_client, _ = _make_provider()
        sync_client.embeddings.create.side_effect = lambda **kwargs: _response(
            [(0, [0.1])]
        )

        with caplog.at_level(logging.WARNING):
            embedding = provider.generate("hello")

        assert embedding == [0.1]
        assert not _slow_call_records(caplog)
