"""Advanced tests for ``MockVectorStorage`` uncovered paths.

Covers structural/filtered reads (``find_structural_chunks``,
``get_body_chunks``, ``count_chunks``), pagination, text search delegation,
prefix deletion, stats/facets, and stub properties.
"""

from __future__ import annotations

from typing import Any

from secondbrain.storage.mock import MockVectorStorage


def _chunk(
    chunk_id: str,
    *,
    source: str = "book1.pdf",
    page: int | None = 1,
    role: str = "body",
    element: str = "paragraph",
    text: str = "body text",
    section: str | None = "2.1",
    printed: int | None = None,
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "chunk_id": chunk_id,
        "source_file": source,
        "page_number": page,
        "chunk_text": text,
        "element_type": element,
        "chunk_role": role,
        "section_id": section,
        "printed_page": printed,
    }
    if embedding is not None:
        chunk["embedding"] = embedding
    return {k: v for k, v in chunk.items() if v is not None}


class _Embedder:
    """Deterministic text-to-vector stub for ``search_by_text``."""

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def generate(self, text: str) -> list[float]:
        return self._vectors[text]


def test_cosine_similarity_edge_cases() -> None:
    storage = MockVectorStorage()
    assert storage._calculate_cosine_similarity([], [1.0]) == 0.0
    assert storage._calculate_cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_ensure_index_is_noop() -> None:
    storage = MockVectorStorage()
    storage.ensure_index()
    assert storage.count() == 0


def test_search_skips_chunks_without_embedding() -> None:
    storage = MockVectorStorage()
    storage.store({"chunk_id": "with-vec", "embedding": [1.0, 0.0]})
    storage.store({"chunk_id": "no-vec"})

    results = storage.search([1.0, 0.0], top_k=5)

    assert [r["chunk_id"] for r in results] == ["with-vec"]


def test_search_by_text_without_embedder_returns_empty() -> None:
    storage = MockVectorStorage()
    storage.store(_chunk("c1", embedding=[1.0, 0.0]))

    assert storage.search_by_text("anything", embed_gen=None) == []


def test_search_by_text_embeds_and_applies_filters() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("apple", source="a.pdf", embedding=[1.0, 0.0, 0.0]),
            _chunk("banana", source="b.pdf", embedding=[0.0, 1.0, 0.0]),
        ]
    )
    embedder = _Embedder({"aligned": [1.0, 0.0, 0.0], "unrelated": [0.0, 0.0, 1.0]})

    results = storage.search_by_text(
        "aligned", embed_gen=embedder, top_k=2, threshold=0.5
    )
    assert [r["chunk_id"] for r in results] == ["apple"]

    scoped = storage.search_by_text(
        "aligned", embed_gen=embedder, top_k=2, source_filter="b.pdf"
    )
    assert [r["chunk_id"] for r in scoped] == ["banana"]

    strict = storage.search_by_text(
        "unrelated", embed_gen=embedder, top_k=2, threshold=0.5
    )
    assert strict == []


def test_get_chunk_found_and_missing() -> None:
    storage = MockVectorStorage()
    stored = _chunk("c1")
    storage.store(stored)

    assert storage.get_chunk("c1") == stored
    assert storage.get_chunk("missing") is None


def test_delete_by_prefix_removes_matching_ids_only() -> None:
    storage = MockVectorStorage()
    storage.store_batch([_chunk("doc1-a"), _chunk("doc1-b"), _chunk("doc2-a")])

    assert storage.delete_by_prefix("doc1") == 2
    assert storage.get_chunk_ids() == ["doc2-a"]
    assert storage.delete_by_prefix("nope") == 0


def test_list_chunks_source_filter_and_pagination() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("a1", source="a.pdf"),
            _chunk("b1", source="b.pdf"),
            _chunk("a2", source="a.pdf"),
            _chunk("a3", source="a.pdf"),
        ]
    )

    assert [c["chunk_id"] for c in storage.list_chunks(limit=2, offset=1)] == [
        "b1",
        "a2",
    ]
    assert [c["chunk_id"] for c in storage.list_chunks(source_filter="a.pdf")] == [
        "a1",
        "a2",
        "a3",
    ]
    assert [
        c["chunk_id"] for c in storage.list_chunks(source_filter="a.pdf", offset=2)
    ] == ["a3"]


def test_paginate_reports_pages_and_count() -> None:
    storage = MockVectorStorage()
    storage.store_batch([_chunk(f"c{i}", source="a.pdf") for i in range(5)])
    storage.store(_chunk("x", source="b.pdf"))

    page1 = storage.paginate(page=1, page_size=2)
    assert [c["chunk_id"] for c in page1["items"]] == ["c0", "c1"]
    assert page1["total"] == 6
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert page1["total_pages"] == 3

    last = storage.paginate(page=3, page_size=2)
    assert len(last["items"]) == 2

    beyond = storage.paginate(page=4, page_size=2)
    assert beyond["items"] == []

    scoped = storage.paginate(page=1, page_size=2, source_filter="b.pdf")
    assert scoped["total"] == 1
    assert [c["chunk_id"] for c in scoped["items"]] == ["x"]
    assert storage.count() == 6


def test_get_all_chunks_and_ids_preserve_order() -> None:
    storage = MockVectorStorage()
    storage.store_batch([_chunk("c1"), _chunk("c2"), _chunk("c3")])

    assert [c["chunk_id"] for c in storage.get_all_chunks()] == ["c1", "c2", "c3"]
    assert storage.get_chunk_ids() == ["c1", "c2", "c3"]

    storage.delete("c2")
    storage.store(_chunk("c2"))

    assert storage.get_chunk_ids() == ["c1", "c3", "c2"]


def test_get_stats_reflects_state() -> None:
    storage = MockVectorStorage()
    storage.store_batch([_chunk("c1"), _chunk("c2")])
    storage.initialize()

    stats = storage.get_stats()
    assert stats == {"total_chunks": 2, "total_ids": 2, "initialized": True}


def test_list_source_files_distinct_in_insertion_order() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("c1", source="b.pdf"),
            _chunk("c2", source="a.pdf"),
            _chunk("c3", source="b.pdf"),
        ]
    )
    storage.store({"chunk_id": "c4", "source_file": 42, "page_number": 1})

    assert storage.list_source_files() == ["b.pdf", "a.pdf"]


def test_find_structural_chunks_matches_element_or_role() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("h1", role="heading", element="heading", page=1),
            _chunk("b1", role="body", element="paragraph", page=2),
            _chunk("t1", role="toc_entry", element="paragraph", page=3),
        ]
    )

    assert [
        c["chunk_id"] for c in storage.find_structural_chunks(element_types=["heading"])
    ] == ["h1"]
    assert [
        c["chunk_id"] for c in storage.find_structural_chunks(chunk_roles=["toc_entry"])
    ] == ["t1"]
    assert [
        c["chunk_id"]
        for c in storage.find_structural_chunks(
            element_types=["heading"], chunk_roles=["toc_entry"]
        )
    ] == ["h1", "t1"]


def test_find_structural_chunks_all_fallback_ordered_and_copied() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("p9", page=9),
            _chunk("p2", page=2),
            _chunk("p5", page=5),
        ]
    )

    results = storage.find_structural_chunks()
    assert [c["page_number"] for c in results] == [2, 5, 9]

    results[0]["page_number"] = 999
    stored = storage.get_chunk("p2")
    assert stored is not None
    assert stored["page_number"] == 2


def test_find_structural_chunks_source_prefix_and_limit() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("b1", source="book1.pdf", page=3),
            _chunk("b2", source="book1.pdf", page=1),
            _chunk("b3", source="book1.pdf", page=5),
            _chunk("o1", source="book2.pdf", page=2),
        ]
    )

    scoped = storage.find_structural_chunks(source_prefix="book1")
    assert [c["chunk_id"] for c in scoped] == ["b2", "b1", "b3"]

    limited = storage.find_structural_chunks(source_prefix="book1", limit=2)
    assert [c["chunk_id"] for c in limited] == ["b2", "b1"]


def test_get_body_chunks_filters_role_and_page_floor() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("a-p1", source="s.pdf", page=1),
            _chunk("a-p3", source="s.pdf", page=3),
            _chunk("a-p5", source="s.pdf", page=5),
            _chunk("a-head", source="s.pdf", page=3, role="heading"),
            _chunk("b-p4", source="t.pdf", page=4),
        ]
    )

    all_body = storage.get_body_chunks("s.pdf")
    assert [c["chunk_id"] for c in all_body] == ["a-p1", "a-p3", "a-p5"]

    from_page3 = storage.get_body_chunks("s.pdf", page_gte=3)
    assert [c["chunk_id"] for c in from_page3] == ["a-p3", "a-p5"]


def test_get_body_chunks_limit_and_text_strip() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("a-p1", source="s.pdf", page=1, text="one"),
            _chunk("a-p3", source="s.pdf", page=3, text="three"),
            _chunk("a-nopage", source="s.pdf", page=None, text="loose"),
        ]
    )

    limited = storage.get_body_chunks("s.pdf", limit=2)
    assert [c["chunk_id"] for c in limited] == ["a-nopage", "a-p1"]
    assert limited[0]["chunk_text"] == "loose"

    stripped = storage.get_body_chunks("s.pdf", page_gte=1, with_text=False)
    assert [c["chunk_id"] for c in stripped] == ["a-p1", "a-p3"]
    assert all("chunk_text" not in c for c in stripped)


def test_count_chunks_filter_matrix() -> None:
    storage = MockVectorStorage()
    storage.store_batch(
        [
            _chunk("a1", source="a.pdf", page=1),
            _chunk("a2", source="a.pdf", page=2),
            _chunk("a3", source="a.pdf", page=3, role="heading"),
            _chunk("b1", source="b.pdf", page=4),
        ]
    )

    assert storage.count_chunks() == 4
    assert storage.count_chunks(source_file="a.pdf") == 3
    assert storage.count_chunks(chunk_role="body") == 3
    assert storage.count_chunks(source_file="a.pdf", chunk_role="body") == 2
    assert storage.count_chunks(source_file="missing.pdf") == 0


def test_stub_properties_are_stable_across_accesses() -> None:
    storage = MockVectorStorage()

    assert storage.collection is storage.collection
    assert storage.db is storage.db
    assert storage.client is storage.client
