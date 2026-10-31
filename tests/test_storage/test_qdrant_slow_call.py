"""Slow-call WARNING tests for the Qdrant storage call sites.

Spec (service-observability, Slow-call WARNING logging): a slow Qdrant
search/upsert emits a WARNING naming the operation, target (collection) and
elapsed time through the real ``QdrantVectorStorage`` methods. The backend is
the in-memory Qdrant client (no external server); the client methods are
wrapped with a deliberate stall and the threshold set to a tiny value via
SECONDBRAIN_SLOW_CALL_SECONDS.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage

SLOW_CALL_LOGGER = "secondbrain.logging.slow_call"


@pytest.fixture
def storage() -> Any:
    """QdrantVectorStorage backed by an in-memory Qdrant client."""
    instance = QdrantVectorStorage(collection_name="slow_call_tests")
    instance._client = QdrantClient(":memory:")
    yield instance
    instance.close()


def _stall_wrap(method: Callable, seconds: float) -> Callable:
    """Wrap a client method with a deliberate stall before the real call."""

    def wrapped(**kwargs: Any) -> Any:
        time.sleep(seconds)
        return method(**kwargs)

    return wrapped


def _slow_call_records(caplog: pytest.LogCaptureFixture) -> list:
    return [r for r in caplog.records if r.name == SLOW_CALL_LOGGER]


class TestQdrantSlowCall:
    def test_search_over_threshold_warns(
        self,
        storage: Any,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_SLOW_CALL_SECONDS", "0.01")
        monkeypatch.setattr(
            storage._client,
            "query_points",
            _stall_wrap(storage._client.query_points, 0.05),
        )

        with caplog.at_level(logging.WARNING):
            results = storage.search([0.0] * storage._dimensions, top_k=3)

        assert results == []
        records = _slow_call_records(caplog)
        assert len(records) == 1
        message = records[0].getMessage()
        assert "operation=qdrant.search" in message
        assert "target=slow_call_tests" in message
        assert "elapsed=" in message

    def test_store_over_threshold_warns(
        self,
        storage: Any,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("SECONDBRAIN_SLOW_CALL_SECONDS", "0.01")
        monkeypatch.setattr(
            storage._client,
            "upsert",
            _stall_wrap(storage._client.upsert, 0.05),
        )
        document = {
            "chunk_id": "11111111-1111-1111-1111-111111111111",
            "text": "stall probe",
            "embedding": [0.0] * storage._dimensions,
        }

        with caplog.at_level(logging.WARNING):
            count = storage.store_batch([document])

        assert count == 1
        message = _slow_call_records(caplog)[0].getMessage()
        assert "operation=qdrant.upsert" in message
        assert "target=slow_call_tests" in message

    def test_fast_search_stays_silent(
        self,
        storage: Any,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Default (10 s) threshold: an in-memory search emits no warning."""
        monkeypatch.delenv("SECONDBRAIN_SLOW_CALL_SECONDS", raising=False)

        with caplog.at_level(logging.WARNING):
            results = storage.search([0.0] * storage._dimensions, top_k=3)

        assert results == []
        assert not _slow_call_records(caplog)
