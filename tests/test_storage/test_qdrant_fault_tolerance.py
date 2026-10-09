"""Failure-path tests for ``QdrantVectorStorage``.

Wraps the real in-memory Qdrant client with a proxy that consults the
``FailureInjector`` (the same machinery the chaos suite uses) so connection
errors and timeouts surface inside storage operations without a live server.
Asserts the storage contract under faults: exceptions propagate unswallowed,
``validate_connection`` reports ``False`` instead of raising, and lazily
provisioned collections are re-attempted on the next operation (recovery).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage
from secondbrain.utils.failure_injector import (
    FailureInjector,
    FailureType,
    InjectedConnectionError,
    InjectedTimeoutError,
)

DIM = 4


@pytest.fixture()
def storage() -> QdrantVectorStorage:
    """A QdrantVectorStorage backed by a local-mode (in-memory) Qdrant."""
    instance = QdrantVectorStorage(collection_name="fault_tests")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


class _FaultyClient:
    """Proxy over a Qdrant client that injects failures into named operations.

    Each intercepted operation first asks the injector whether it should fail
    (raising the injector's typed error) and otherwise delegates to the real
    client. Non-intercepted attributes are transparent pass-throughs.
    """

    def __init__(
        self,
        inner: Any,
        injector: FailureInjector,
        fail_on: set[str],
        failure_type: FailureType,
        message: str,
    ) -> None:
        self._inner = inner
        self._injector = injector
        self._fail_on = frozenset(fail_on)
        self._failure_type = failure_type
        self._message = message

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name not in self._fail_on or not callable(attr):
            return attr

        def operation(*args: Any, **kwargs: Any) -> Any:
            if self._injector.should_fail(self._failure_type):
                self._injector.raise_failure(self._failure_type, self._message)
            return attr(*args, **kwargs)

        return operation


def _doc(
    chunk_id: str,
    source: str = "a.pdf",
    page: int = 1,
    text: str = "hello",
) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "source_file": source,
        "page_number": page,
        "chunk_text": text,
        "element_type": "paragraph",
        "chunk_role": "body",
        "section_label": "Chapter 1",
        "file_type": "pdf",
        "text_hash": f"hash-{chunk_id}",
        "chapter_id": 1,
        "section_id": "1.1",
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }


class TestInjectedConnectionErrors:
    """Connection failures surface as the original error, never swallowed."""

    def test_store_surfaces_injected_connection_error(
        self, storage: QdrantVectorStorage, failure_injector: FailureInjector
    ) -> None:
        """An upsert hit by an injected connection error propagates it intact."""
        storage._client = _FaultyClient(
            storage._client,
            failure_injector,
            {"upsert"},
            FailureType.CONNECTION_ERROR,
            "qdrant unreachable",
        )

        with failure_injector.inject_connection_error(
            error_message="qdrant unreachable"
        ):
            with pytest.raises(InjectedConnectionError, match="qdrant unreachable"):
                storage.store(_doc("c1"))

        # The injection is gone: the same call now succeeds (recovery).
        assert storage.store(_doc("c1"))

    def test_scroll_read_surfaces_injected_connection_error(
        self, storage: QdrantVectorStorage, failure_injector: FailureInjector
    ) -> None:
        """Reads (scroll) propagate injected connection errors too."""
        storage._client = _FaultyClient(
            storage._client,
            failure_injector,
            {"scroll"},
            FailureType.CONNECTION_ERROR,
            "qdrant read failed",
        )
        storage.store(_doc("c1"))

        with failure_injector.inject_connection_error(
            error_message="qdrant read failed"
        ):
            with pytest.raises(InjectedConnectionError, match="qdrant read failed"):
                storage.list_chunks()

    def test_flaky_upserts_recover_after_repeat_count_is_exhausted(
        self, storage: QdrantVectorStorage, failure_injector: FailureInjector
    ) -> None:
        """The injector's repeat_count bounds the failures; the next store wins."""
        storage._client = _FaultyClient(
            storage._client,
            failure_injector,
            {"upsert"},
            FailureType.CONNECTION_ERROR,
            "qdrant flaky",
        )
        failure_injector.inject(
            FailureType.CONNECTION_ERROR, repeat_count=2, error_message="qdrant flaky"
        )

        attempts: list[str] = []
        for attempt in range(3):
            try:
                storage.store(_doc(f"c{attempt}"))
                attempts.append("ok")
            except InjectedConnectionError:
                attempts.append("fail")

        assert attempts == ["fail", "fail", "ok"]
        results = storage.search([0.1, 0.2, 0.3, 0.4], top_k=10)
        assert [r["chunk_id"] for r in results] == ["c2"]


class TestInjectedTimeouts:
    """Timeouts surface as InjectedTimeoutError carrying the timeout value."""

    def test_search_surfaces_injected_timeout(
        self, storage: QdrantVectorStorage, failure_injector: FailureInjector
    ) -> None:
        """A query_points hit by an injected timeout propagates it intact."""
        storage._client = _FaultyClient(
            storage._client,
            failure_injector,
            {"query_points"},
            FailureType.TIMEOUT,
            "qdrant query timed out",
        )
        storage.store(_doc("c1"))

        with failure_injector.inject_timeout(
            timeout_value=2.0, error_message="qdrant query timed out"
        ):
            with pytest.raises(
                InjectedTimeoutError, match="qdrant query timed out"
            ) as excinfo:
                storage.search([0.1, 0.2, 0.3, 0.4])

        assert excinfo.value.timeout_value == 2.0

        # Injection ended: the search finds the seeded chunk again.
        results = storage.search([0.1, 0.2, 0.3, 0.4], top_k=5)
        assert [r["chunk_id"] for r in results] == ["c1"]


class TestConnectionState:
    """validate_connection never raises; TTL caches both success and failure."""

    def test_validate_connection_false_under_injection_then_recovers(
        self, storage: QdrantVectorStorage, failure_injector: FailureInjector
    ) -> None:
        """Injected probe failure reports False (no raise); recovery reports True."""
        storage._client = _FaultyClient(
            storage._client,
            failure_injector,
            {"get_collections"},
            FailureType.CONNECTION_ERROR,
            "qdrant unreachable",
        )

        with failure_injector.inject_connection_error(
            error_message="qdrant unreachable"
        ):
            assert storage.validate_connection(force=True) is False
            # Failure results are also TTL-cached.
            assert storage.validate_connection() is False

        assert storage.validate_connection(force=True) is True

    def test_validate_connection_ttl_skips_probe_until_expiry(
        self,
        storage: QdrantVectorStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A cached result suppresses probing until the TTL elapses."""
        now = [1000.0]
        monkeypatch.setattr("secondbrain.storage.qdrant.time.monotonic", lambda: now[0])
        probes: list[int] = []
        real_get_collections = storage._client.get_collections

        def counting_get_collections() -> Any:
            probes.append(1)
            return real_get_collections()

        monkeypatch.setattr(
            storage._client, "get_collections", counting_get_collections
        )

        assert storage.validate_connection() is True
        assert storage.validate_connection() is True  # served from cache
        assert len(probes) == 1

        now[0] += 61.0  # past _CONNECTION_TTL
        assert storage.validate_connection() is True  # re-probes
        assert len(probes) == 2

    def test_validate_connection_failure_cached_until_forced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreachable server caches False until force=True re-probes."""
        instance = QdrantVectorStorage(url="http://localhost:1", collection_name="x")

        assert instance.validate_connection() is False
        assert instance.validate_connection() is False  # cached failure
        assert instance.validate_connection(force=True) is False  # re-probed

    async def test_validate_connection_async_reports_reachability(self) -> None:
        """The async wrapper mirrors the sync probe without raising."""
        reachable = QdrantVectorStorage(collection_name="async_probe")
        reachable._client = QdrantClient(":memory:")
        reachable._dimensions = DIM
        assert await reachable.validate_connection_async(force=True) is True

        unreachable = QdrantVectorStorage(
            url="http://localhost:1", collection_name="async_probe"
        )
        assert await unreachable.validate_connection_async(force=True) is False


class TestProvisioningRecovery:
    """Lazy provisioning is retried when it fails; nothing is swallowed."""

    def test_provisioning_failure_propagates_and_is_retried(
        self,
        storage: QdrantVectorStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """First provisioning failure raises and stays unready; retry succeeds."""
        real_get_collections = storage._client.get_collections
        state = {"calls": 0}

        def flaky_get_collections() -> Any:
            state["calls"] += 1
            if state["calls"] == 1:
                raise ConnectionError("qdrant unreachable")
            return real_get_collections()

        monkeypatch.setattr(storage._client, "get_collections", flaky_get_collections)

        with pytest.raises(ConnectionError, match="qdrant unreachable"):
            storage.store(_doc("c1"))
        assert storage._collection_ready is False

        # Next operation re-attempts provisioning and succeeds.
        assert storage.store(_doc("c1"))
        assert storage._collection_ready is True
        results = storage.search([0.1, 0.2, 0.3, 0.4])
        assert [r["chunk_id"] for r in results] == ["c1"]


class TestLifecycle:
    """Lifecycle edge cases around close and empty batches."""

    def test_close_swallows_client_close_errors(
        self,
        storage: QdrantVectorStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failing client.close() is logged, not raised; client is dropped."""

        def broken_close() -> None:
            raise RuntimeError("close failed")

        monkeypatch.setattr(storage._client, "close", broken_close)

        storage.close()

        assert storage._client is None
        storage.close()  # idempotent no-op after the client is dropped

    def test_store_batch_empty_returns_zero_without_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty batch short-circuits before any client interaction."""
        instance = QdrantVectorStorage(collection_name="empty_batch")

        def explode(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("client must not be touched for empty batch")

        monkeypatch.setattr(
            "secondbrain.storage.qdrant.QdrantClient", MagicMock(side_effect=explode)
        )

        assert instance.store_batch([]) == 0
