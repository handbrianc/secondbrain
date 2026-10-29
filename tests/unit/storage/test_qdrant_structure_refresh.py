"""Unit tests for qdrant payload-index + structural refresh (task 9, design §7).

Runs against ``QdrantClient(":memory:")`` (real client API, no server), the
same pattern as ``tests/test_storage/test_qdrant_storage.py``. The refresh
itself follows design D3 of ``fix-chunk-heading-context``: payload-only
scroll, reading-order reconstruction on ``(page_number, page_pos)``, ONE
ordered annotate pass, and diff-gated writes — batched ``set_payload`` by
explicit point ids plus targeted ``delete_payload`` for stale annotation
keys the fresh annotation no longer carries.
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


def shared_page_tree(source_file: str = SOURCE) -> DocumentStructure:
    """Two chapters plus a section, all sharing page 11 (sibling ambiguity)."""
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
                page_end=11,
                heading_path="Chapter 5 — Installing",
            ),
            StructureNode(
                node_id="ch06",
                kind="chapter",
                level=1,
                number="6",
                title="Operations",
                page_start=11,
                page_end=20,
                heading_path="Chapter 6 — Operations",
            ),
            StructureNode(
                node_id="sec06.01",
                parent_id="ch06",
                kind="section",
                level=2,
                number="6.1",
                title="Maintenance",
                page_start=11,
                page_end=12,
                heading_path="Chapter 6 — Operations > 6.1 Maintenance",
            ),
        ],
        sources={"outline": True},
    )


def unnumbered_tree(source_file: str = SOURCE) -> DocumentStructure:
    """One chapter without a section number.

    Fresh annotations under it carry no ``section_id``/``section_label``
    and fall back to the node id for ``chapter_id`` — the shape an older
    tree's stale extras can never match.
    """
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            StructureNode(
                node_id="chFM",
                kind="chapter",
                level=1,
                number=None,
                title="Front Matter",
                page_start=1,
                page_end=12,
                heading_path="Front Matter",
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
    """A partially annotated point (``node_id`` only, no other keys).

    Under full-set, diff-gated refresh semantics (design D3) this point is
    REWRITTEN to the complete annotation — its stored annotation differs
    from the fresh one. It models a legacy partial annotation from an
    older tree.
    """
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
    def test_audio_refresh_uses_and_preserves_chunk_time_bounds(
        self, storage: QdrantVectorStorage
    ) -> None:
        tree = DocumentStructure(
            source_file=SOURCE,
            nodes=[
                StructureNode(
                    node_id="seg01",
                    kind="segment",
                    level=1,
                    title="Opening",
                    heading_path="Segment 01",
                    t_start=0.0,
                    t_end=30.0,
                ),
                StructureNode(
                    node_id="seg02",
                    kind="segment",
                    level=1,
                    title="Discussion",
                    heading_path="Segment 02",
                    t_start=30.0,
                    t_end=60.0,
                ),
            ],
            sources={"audio": True},
        )
        storage.store_batch(
            [
                {
                    **_legacy_doc("audio", 1, "discussion transcript"),
                    "t_start": 35.0,
                    "t_end": 45.0,
                }
            ]
        )

        assert storage.refresh_structural_payload(SOURCE, tree) == 1
        payload = _payloads(storage)["audio"]
        assert payload["node_id"] == "seg02"
        assert payload["chapter_id"] == "seg02"
        assert payload["heading_path"] == "Segment 02"
        assert (payload["t_start"], payload["t_end"]) == (35.0, 45.0)
        chunk = storage._payload_to_chunk(payload)
        assert chunk["node_id"] == "seg02"
        assert (chunk["t_start"], chunk["t_end"]) == (35.0, 45.0)

    def test_annotates_legacy_points_and_completes_partial_annotations(
        self, storage: QdrantVectorStorage
    ) -> None:
        """Legacy points gain keys; a partially annotated point is completed.

        The refresh reads the document's full point set and writes only
        where the stored annotation is missing or differs (design D3):
        ``fresh-1`` carries only ``node_id`` and is rewritten to the full
        annotation. A second refresh finds every stored annotation already
        correct and writes nothing (idempotent).
        """
        storage.store_batch(
            [
                _legacy_doc("legacy-1", 7, "5.2 Setup " + "prose " * 40),
                _legacy_doc("legacy-2", 11, "more prose " * 40),
                _fresh_doc("fresh-1", 8, "already annotated prose " * 40),
            ]
        )

        refreshed = storage.refresh_structural_payload(SOURCE, section_tree())

        assert refreshed == 3  # the partial point is completed, not skipped
        payloads = _payloads(storage)
        assert payloads["legacy-1"]["node_id"] == "sec05.02"
        assert payloads["legacy-1"]["section_id"] == "5.2"
        assert payloads["legacy-1"]["section_label"] == "Setup"
        assert payloads["legacy-1"]["chapter_id"] == "5"
        assert payloads["legacy-2"]["node_id"] == "ch05"  # page 11 → chapter
        assert payloads["legacy-2"]["section_id"] == "5"
        # The partial point keeps its node_id and gains the remaining keys.
        assert payloads["fresh-1"]["node_id"] == "sec05.02"
        assert payloads["fresh-1"]["section_label"] == "Setup"

        # Idempotent: every stored annotation now matches — nothing written.
        assert storage.refresh_structural_payload(SOURCE, section_tree()) == 0

    def test_stale_annotation_keys_are_deleted(
        self, storage: QdrantVectorStorage
    ) -> None:
        """Stale extras from an older tree are removed via delete_payload.

        ``set_payload`` cannot delete keys, so a point carrying annotation
        keys the fresh annotation no longer has (here ``section_id`` /
        ``section_label`` / ``t_start`` under an unnumbered chapter) needs
        the targeted delete pass (design D3); without it the diff gate sees
        a permanent difference and repeated refreshes never converge.
        """
        storage.store_batch(
            [
                {
                    **_legacy_doc("stale-extra", 3, "front matter prose " * 40),
                    "section_id": "9.9",
                    "section_label": "Ghost",
                    "t_start": 3.2,
                },
                {
                    **_legacy_doc("correct", 4, "front matter prose " * 40),
                    "node_id": "chFM",
                    "heading_path": "Front Matter",
                    "chapter_id": "chFM",
                },
            ]
        )

        refreshed = storage.refresh_structural_payload(SOURCE, unnumbered_tree())

        # The stale-extra point needs both a set and a delete pass but is
        # counted once; the already-correct point is a no-op.
        assert refreshed == 1
        payloads = _payloads(storage)
        assert payloads["stale-extra"]["node_id"] == "chFM"
        assert payloads["stale-extra"]["chapter_id"] == "chFM"
        assert "section_id" not in payloads["stale-extra"]
        assert "section_label" not in payloads["stale-extra"]
        assert "t_start" not in payloads["stale-extra"]
        assert payloads["correct"]["node_id"] == "chFM"

        # Converged: a second refresh writes nothing.
        assert storage.refresh_structural_payload(SOURCE, unnumbered_tree()) == 0

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

    def test_refresh_reconstructs_reading_order(
        self, storage: QdrantVectorStorage
    ) -> None:
        """A body point stored before its heading gains the heading's node.

        Stored order is not reading order; the old stateless per-batch
        annotate left such body points unannotated forever (same-page
        bail-out). The refresh sorts on ``(page_number, page_pos)`` first,
        so the body point lands after the anchored heading and inherits it
        (design D3).
        """
        storage.store_batch(
            [
                {
                    **_legacy_doc("body", 11, "prose after the operations heading"),
                    "page_pos": 1,
                },
                {
                    **_legacy_doc("heading", 11, "Chapter 6 Operations prose"),
                    "page_pos": 0,
                },
            ]
        )

        refreshed = storage.refresh_structural_payload(SOURCE, shared_page_tree())

        assert refreshed == 2
        payloads = _payloads(storage)
        assert payloads["heading"]["node_id"] == "ch06"  # anchor
        assert payloads["body"]["node_id"] == "ch06"  # sticky inheritance
        assert payloads["body"]["heading_path"] == "Chapter 6 — Operations"

    def test_refresh_scrolls_payload_only_and_batches_set_payload(
        self, storage: QdrantVectorStorage
    ) -> None:
        """The collect pass paginates; writes are id-batched set_payloads."""
        storage.store_batch(
            [
                _legacy_doc(f"legacy-{index}", 7, "5.2 Setup " + "prose " * 40)
                for index in range(600)
            ]
        )
        recording = MagicMock(wraps=storage._client)
        storage._client = recording

        refreshed = storage.refresh_structural_payload(SOURCE, section_tree())

        assert refreshed == 600
        assert recording.upsert.call_count == 0  # no vector round-trip
        scroll_calls = recording.scroll.call_args_list
        assert len(scroll_calls) > 1, "the collect pass must paginate"
        for call in scroll_calls:
            assert call.kwargs["with_payload"] is True
            assert call.kwargs["with_vectors"] is False  # payload-only read
        set_calls = recording.set_payload.call_args_list
        assert set_calls
        written = [pid for call in set_calls for pid in call.kwargs["points"]]
        assert len(written) == 600  # every refreshed point written exactly once
        assert len(set(written)) == 600
        assert all(
            len(call.kwargs["points"]) <= _REFRESH_BATCH_SIZE for call in set_calls
        )
        records, _ = storage._client.scroll(
            collection_name=storage.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_file", match=models.MatchValue(value=SOURCE)
                    )
                ]
            ),
            limit=1000,
            with_payload=True,
        )
        payload = next(
            dict(r.payload or {})
            for r in records
            if r.payload.get("chunk_id") == "legacy-0"
        )
        assert payload["node_id"] == "sec05.02"
        assert payload["section_id"] == "5.2"

    def test_set_payload_failure_degrades_to_partial_count(
        self, storage: QdrantVectorStorage
    ) -> None:
        """A failed write batch keeps the partial count; failures stay refreshable."""
        storage.store_batch(
            [
                _legacy_doc("sec-a", 7, "5.2 Setup " + "p " * 40),
                _legacy_doc("sec-b", 8, "5.2 Setup " + "p " * 40),
                _legacy_doc("chapter", 11, "prose " * 40),
            ]
        )
        client = storage._client
        recording = MagicMock(wraps=client)
        real_set_payload = client.set_payload
        batch_sizes: list[int] = []

        def flaky_set_payload(**kwargs: Any) -> Any:
            batch_sizes.append(len(kwargs["points"]))
            if len(batch_sizes) == 2:
                raise RuntimeError("write gone")
            return real_set_payload(**kwargs)

        recording.set_payload.side_effect = flaky_set_payload
        storage._client = recording

        refreshed = storage.refresh_structural_payload(SOURCE, section_tree())

        # Group 1 (the two 5.2 points on pages 7-8) wrote; group 2 (the
        # page-11 chapter point) failed → partial count 2. The failed point
        # keeps its unannotated payload, so the next refresh's diff gate
        # rewrites exactly it.
        assert refreshed == 2
        assert batch_sizes == [2, 1]
        payloads = _payloads(storage)
        assert payloads["sec-a"]["node_id"] == "sec05.02"
        assert payloads["sec-b"]["node_id"] == "sec05.02"
        assert "node_id" not in payloads["chapter"]

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
