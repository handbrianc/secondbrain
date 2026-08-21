"""Tests for ``secondbrain.storage.qdrant.QdrantVectorStorage``.

Uses ``QdrantClient(":memory:")`` — Qdrant's in-process local mode that runs the
real Qdrant API without a server. This exercises the actual client, catching API
drift (e.g. ``query_points`` vs ``search``) that pure-mock tests would miss.
"""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage
from secondbrain.types import _validate_search_result

DIM = 4


@pytest.fixture()
def storage() -> QdrantVectorStorage:
    """A QdrantVectorStorage backed by a local-mode (in-memory) Qdrant."""
    instance = QdrantVectorStorage(collection_name="test_coll")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def _doc(chunk_id: str, source: str = "a.pdf", page: int = 1, text: str = "hello",
         chapter_id: int = 1):
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
        "chapter_id": chapter_id,
        "section_id": "1.1",
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }


def test_store_then_search_roundtrip(storage: QdrantVectorStorage) -> None:
    """Store + search returns the chunk with a score, passing the runtime gate."""
    storage.store(_doc("c1"))

    results = list(storage.search([0.1, 0.2, 0.3, 0.4], top_k=5))

    assert len(results) == 1
    _validate_search_result(dict(results[0]))
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["chunk_text"] == "hello"
    assert (results[0].get("score") or 0) > 0


def test_search_respects_source_filter(storage: QdrantVectorStorage) -> None:
    """Search applies the source_file payload filter."""
    storage.store_batch([_doc("c1", source="a.pdf"), _doc("c2", source="b.pdf")])

    results = list(storage.search([0.1, 0.2, 0.3, 0.4], top_k=5, source_filter="b"))

    assert [r["source_file"] for r in results] == ["b.pdf"]


def test_store_batch_returns_count(storage: QdrantVectorStorage) -> None:
    """store_batch returns the number of documents."""
    assert storage.store_batch([_doc("c1"), _doc("c2")]) == 2


def test_list_source_files_distinct(storage: QdrantVectorStorage) -> None:
    """list_source_files returns distinct source_file values."""
    storage.store_batch([_doc("c1", source="a.pdf"), _doc("c2", source="a.pdf"),
                         _doc("c3", source="b.pdf")])

    assert storage.list_source_files() == ["a.pdf", "b.pdf"]


def test_has_existing_hashes(storage: QdrantVectorStorage) -> None:
    """has_existing_hashes returns the subset already present."""
    storage.store(_doc("c1"))

    assert storage.has_existing_hashes(["hash-c1", "missing"]) == {"hash-c1"}


def test_find_chunks_by_chapter_id_coerces_int(storage: QdrantVectorStorage) -> None:
    """find_chunks matches a str chapter_id against an int stored payload."""
    storage.store_batch([
        _doc("c1", source="a.pdf", chapter_id=1),
        _doc("c2", source="b.pdf", chapter_id=2),
    ])

    assert [c["chunk_id"] for c in storage.find_chunks(chapter_id="1")] == ["c1"]


def test_get_source_chunks_ordered_by_page(storage: QdrantVectorStorage) -> None:
    """get_source_chunks returns a source's chunks ordered by page."""
    storage.store_batch([
        _doc("c1", source="a.pdf", page=2),
        _doc("c2", source="a.pdf", page=1),
    ])

    pages = [c["page_number"] for c in storage.get_source_chunks("a.pdf")]
    assert pages == [1, 2]


def test_delete_by_source_and_stats(storage: QdrantVectorStorage) -> None:
    """delete_by_source removes only that source; get_stats reflects it."""
    storage.store_batch([_doc("c1", source="a.pdf"), _doc("c2", source="b.pdf")])

    assert storage.delete_by_source("a.pdf") == 1
    stats = storage.get_stats()
    assert stats["total_chunks"] == 1
    assert stats["unique_sources"] == 1
    assert stats["database"] == "qdrant"


def test_validate_connection_without_server_is_false() -> None:
    """A fresh storage with no reachable server validates False, never raises."""
    instance = QdrantVectorStorage(url="http://localhost:1", collection_name="x")
    assert instance.validate_connection(force=True) is False
