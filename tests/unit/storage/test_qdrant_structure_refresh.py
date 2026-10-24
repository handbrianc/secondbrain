"""Unit tests for qdrant payload-index + structural refresh (task 9, design §7).

Runs against ``QdrantClient(":memory:")`` (real client API, no server), the
same pattern as ``tests/test_storage/test_qdrant_storage.py``.
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models

from secondbrain.storage import structure_sqlite
from secondbrain.storage.qdrant import (
    _INDEXED_FIELDS,
    _REFRESH_BATCH_SIZE,
    QdrantVectorStorage,
)
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)

pytestmark = pytest.mark.unit

DIM = 4
SOURCE = "/tmp/book.pdf"


@pytest.fixture()
def storage() -> QdrantVectorStorage:
    instance = QdrantVectorStorage(collection_name="test_refresh")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def section_tree(source_file: str = SOURCE) -> DocumentStructure:
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            StructureNode(
                node_id="ch05",
                kind="chapter",
                level=1,
                number="5",
                title="Installing",
                page_start=5,
                page_end=12,
                heading_path="Chapter 5 — Installing",
            ),
            StructureNode(
                node_id="sec05.02",
                parent_id="ch05",
                kind="section",
                level=2,
                number="5.2",
                title="Setup",
                page_start=7,
                page_end=9,
                heading_path="Chapter 5 — Installing > 5.2 Setup",
            ),
        ],
        sources={"outline": True},
    )


def _legacy_doc(chunk_id: str, page: int, text: str) -> dict[str, Any]:
    """A pre-annotation point payload (no structural keys)."""
    return {
        "chunk_id": chunk_id,
        "source_file": SOURCE,
        "page_number": page,
        "chunk_text": text,
        "chunk_role": "body",
        "element_type": "body",
        "embedding": [0.1] * DIM,
    }


def _fresh_doc(chunk_id: str, page: int, text: str) -> dict[str, Any]:
    """A freshly annotated point (already carries node_id → must be skipped)."""
    return {**_legacy_doc(chunk_id, page, text), "node_id": "sec05.02"}


def _payloads(storage: QdrantVectorStorage) -> dict[str, dict[str, Any]]:
    assert storage._client is not None
    records, _ = storage._client.scroll(
        collection_name=storage.collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="source_file", match=models.MatchValue(value=SOURCE)
                )
            ]
        ),
        limit=100,
        with_payload=True,
    )
    return {
        (payload := dict(record.payload or {}))["chunk_id"]: payload
        for record in records
    }


class TestIndexProvisioning:
    def test_chunk_role_is_indexed(self) -> None:
        assert "chunk_role" in _INDEXED_FIELDS

    def test_index_creation_is_idempotent(self, storage: QdrantVectorStorage) -> None:
        storage._ensure_collection()
        storage._ensure_collection()  # second call must not raise
        assert storage._collection_ready is True

    def test_failing_index_creation_does_not_fail_setup(
        self, storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert storage._client is not None

        def explode(**kwargs: Any) -> None:
            raise RuntimeError("server rejected the index")

        monkeypatch.setattr(storage._client, "create_payload_index", explode)
        storage._collection_ready = False
        storage._ensure_collection()  # degrades to payload-without-index
        assert storage._collection_ready is True


class TestRefreshStructuralPayload:
    def test_annotates_legacy_points_and_skips_annotated_ones(
        self, storage: QdrantVectorStorage
    ) -> None:
        storage.store_batch(
            [
                _legacy_doc("legacy-1", 7, "5.2 Setup " + "prose " * 40),
                _legacy_doc("legacy-2", 11, "more prose " * 40),
                _fresh_doc("fresh-1", 8, "already annotated prose " * 40),
            ]
        )

        refreshed = storage.refresh_structural_payload(SOURCE, section_tree())

        assert refreshed == 2  # the fresh point is excluded by is_empty
        payloads = _payloads(storage)
        assert payloads["legacy-1"]["node_id"] == "sec05.02"
        assert payloads["legacy-1"]["section_id"] == "5.2"
        assert payloads["legacy-1"]["section_label"] == "Setup"
        assert payloads["legacy-1"]["chapter_id"] == "5"
        assert payloads["legacy-2"]["node_id"] == "ch05"  # page 11 → chapter
        assert payloads["legacy-2"]["section_id"] == "5"
        # The fresh point keeps its payload (including its vector) untouched.
        assert payloads["fresh-1"]["node_id"] == "sec05.02"
        assert "section_label" not in payloads["fresh-1"]

    def test_refresh_survives_and_preserves_vectors(
        self, storage: QdrantVectorStorage
    ) -> None:
        storage.store_batch([_legacy_doc("legacy-1", 7, "5.2 Setup " + "prose " * 40)])
        vector_before = self._stored_vector(storage, "legacy-1")

        storage.refresh_structural_payload(SOURCE, section_tree())

        assert self._stored_vector(storage, "legacy-1") == vector_before

    def test_points_without_a_matching_node_are_left_refreshable(
        self, storage: QdrantVectorStorage
    ) -> None:
        storage.store_batch([_legacy_doc("orphan", 1, "front matter " * 40)])
        refreshed = storage.refresh_structural_payload(SOURCE, section_tree())
        assert refreshed == 0
        payloads = _payloads(storage)
        assert "node_id" not in payloads["orphan"]  # stays refreshable

    def test_lazy_structure_load_via_store(
        self,
        storage: QdrantVectorStorage,
        tmp_path: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        try:
            store.save_structure(section_tree())
            monkeypatch.setattr(
                structure_sqlite,
                "StructureStore",
                lambda *a, **k: store,
            )
            storage.store_batch([_legacy_doc("legacy-1", 7, "5.2 Setup " + "p " * 40)])
            refreshed = storage.refresh_structural_payload(SOURCE)
            assert refreshed == 1
            assert _payloads(storage)["legacy-1"]["node_id"] == "sec05.02"
        finally:
            store.close()

    def test_lazy_load_failure_yields_zero(
        self, storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_store(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("sqlite unavailable")

        monkeypatch.setattr(structure_sqlite, "StructureStore", broken_store)
        storage.store_batch([_legacy_doc("legacy-1", 7, "5.2 Setup " + "p " * 40)])
        assert storage.refresh_structural_payload(SOURCE) == 0

    def test_other_sources_are_never_touched(
        self, storage: QdrantVectorStorage
    ) -> None:
        other = {**_legacy_doc("other-doc", 7, "5.2 Setup " + "p " * 40)}
        other["source_file"] = "/tmp/other.pdf"
        storage.store_batch(
            [other, _legacy_doc("legacy-1", 7, "5.2 Setup " + "p " * 40)]
        )

        storage.refresh_structural_payload(SOURCE, section_tree())

        payloads = _payloads(storage) | self._other_payloads(storage)
        assert "node_id" not in payloads["other-doc"]
        assert payloads["legacy-1"]["node_id"] == "sec05.02"

    def test_client_errors_degrade_to_partial_count(
        self, storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage.store_batch([_legacy_doc("legacy-1", 7, "5.2 Setup " + "p " * 40)])
        exploding_client = MagicMock(wraps=storage._client)
        exploding_client.scroll.side_effect = RuntimeError("server gone")
        storage._client = exploding_client

        assert storage.refresh_structural_payload(SOURCE, section_tree()) == 0

    def test_repeating_scroll_pages_do_not_loop_forever(
        self, storage: QdrantVectorStorage, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A stalled cursor (skipped points keep matching) must terminate."""
        storage._ensure_collection()  # warm before swapping in the fake client
        record = models.Record(
            id="00000000-0000-0000-0000-000000000001",
            vector=[0.1] * DIM,
            payload={"chunk_id": "orphan", "source_file": SOURCE, "page_number": 1},
        )
        stalled_client = MagicMock()
        stalled_client.scroll.return_value = ([record], "cursor-forever")
        storage._client = stalled_client

        assert storage.refresh_structural_payload(SOURCE, section_tree()) == 0
        # Round 1 processes the page; round 2 sees only already-seen ids and
        # breaks instead of looping on points that stay is_empty forever.
        assert stalled_client.scroll.call_count == 2

    def test_batch_size_is_bounded(self) -> None:
        assert _REFRESH_BATCH_SIZE == 256

    @staticmethod
    def _stored_vector(storage: QdrantVectorStorage, chunk_id: str) -> Any:
        assert storage._client is not None
        records, _ = storage._client.scroll(
            collection_name=storage.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="chunk_id", match=models.MatchValue(value=chunk_id)
                    )
                ]
            ),
            limit=1,
            with_vectors=True,
        )
        assert records
        return cast(list[float], records[0].vector)

    @staticmethod
    def _other_payloads(storage: QdrantVectorStorage) -> dict[str, dict[str, Any]]:
        assert storage._client is not None
        records, _ = storage._client.scroll(
            collection_name=storage.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_file",
                        match=models.MatchValue(value="/tmp/other.pdf"),
                    )
                ]
            ),
            limit=100,
            with_payload=True,
        )
        return {
            (payload := dict(record.payload or {}))["chunk_id"]: payload
            for record in records
        }
