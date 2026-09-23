"""Filter-semantics tests for ``QdrantVectorStorage`` document scans.

Uses Qdrant local mode (``QdrantClient(":memory:")``) — the real client, no
server. Asserts which chunks each filter combination returns, not just that a
call happened.
"""

from __future__ import annotations

from typing import Any

import pytest
from qdrant_client import QdrantClient

from secondbrain.storage.qdrant import QdrantVectorStorage

DIM = 4


@pytest.fixture()
def storage() -> QdrantVectorStorage:
    """A QdrantVectorStorage backed by a local-mode (in-memory) Qdrant."""
    instance = QdrantVectorStorage(collection_name="filter_tests")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def _doc(
    chunk_id: str,
    *,
    source: str = "book.pdf",
    page: int | None = 1,
    text: str = "hello",
    role: str = "body",
    element: str = "paragraph",
    section: str = "2.1",
    printed: int | str | None = None,
    section_id_missing: bool = False,
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "chunk_id": chunk_id,
        "source_file": source,
        "page_number": page,
        "chunk_text": text,
        "element_type": element,
        "chunk_role": role,
        "section_label": f"Section {section}",
        "section_id": None if section_id_missing else section,
        "file_type": "pdf",
        "embedding": [0.1, 0.2, 0.3, 0.4],
    }
    if printed is not None:
        doc["printed_page"] = printed
    return doc


def test_find_chunks_by_section_id_string(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("s21", section="2.1"),
            _doc("s22", section="2.2"),
            _doc("s21b", source="other.pdf", section="2.1"),
        ]
    )

    results = storage.find_chunks(source_file="book.pdf", section_id="2.1")

    assert [c["chunk_id"] for c in results] == ["s21"]


def test_find_chunks_section_id_int_coercion(storage: QdrantVectorStorage) -> None:
    """Stored section_id 3 is matched by both "3" and the bare int 3."""
    storage.store_batch(
        [
            _doc("int3", section="2.1"),
            _doc("int5", section="2.1"),
        ]
    )
    # Overwrite the section_id with an int payload (upsert by same chunk_id).
    storage.store({**_doc("int3", section="2.1"), "section_id": 3})
    storage.store({**_doc("int5", section="2.1"), "section_id": 5})

    assert [c["chunk_id"] for c in storage.find_chunks(section_id="3")] == ["int3"]
    assert [c["chunk_id"] for c in storage.find_chunks(section_id="5")] == ["int5"]


def test_find_chunks_by_printed_page(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("p7", printed=7),
            _doc("p9", printed=9),
        ]
    )

    assert [c["chunk_id"] for c in storage.find_chunks(printed_page=7)] == ["p7"]
    assert [c["chunk_id"] for c in storage.find_chunks(printed_page="7")] == ["p7"]


def test_find_chunks_page_number_scalar_and_list(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("p1", page=1),
            _doc("p2", page=2),
            _doc("p3", page=3),
        ]
    )

    assert [c["chunk_id"] for c in storage.find_chunks(page_number=2)] == ["p2"]
    assert [c["chunk_id"] for c in storage.find_chunks(page_number=[1, 3])] == [
        "p1",
        "p3",
    ]


def test_find_chunks_section_pattern_and_no_text(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("intro", section="2.1 Introduction"),
            _doc("deep", section="2.10 Advanced"),
            _doc("other", section="3.2 Misc"),
        ]
    )

    results = storage.find_chunks(section_id_pattern=r"^2\.1[0]?\s")
    # find_chunks does not sort; scroll order is client-dependent here.
    assert sorted(c["chunk_id"] for c in results) == ["deep", "intro"]

    bare = storage.find_chunks(section_id_pattern=r"^2\.1", with_text=False)
    assert sorted(c["chunk_id"] for c in bare) == ["deep", "intro"]
    assert all(c["chunk_text"] is None for c in bare)


def test_find_structural_chunks_element_or_role(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("h", role="heading", element="heading", page=1),
            _doc("b", role="body", element="paragraph", page=2),
            _doc("c", role="caption", element="paragraph", page=3),
        ]
    )

    by_element = storage.find_structural_chunks(element_types=["heading"])
    assert [c["chunk_id"] for c in by_element] == ["h"]

    by_role = storage.find_structural_chunks(chunk_roles=["caption"])
    assert [c["chunk_id"] for c in by_role] == ["c"]

    union = storage.find_structural_chunks(
        element_types=["paragraph"], chunk_roles=["heading"]
    )
    assert [c["chunk_id"] for c in union] == ["h", "b", "c"]


def test_find_structural_chunks_all_fallback_ordered(
    storage: QdrantVectorStorage,
) -> None:
    storage.store_batch(
        [
            _doc("late", page=4),
            _doc("early", page=1),
            _doc("mid", page=2),
        ]
    )

    results = storage.find_structural_chunks()
    assert [c["chunk_id"] for c in results] == ["early", "mid", "late"]


def test_find_structural_chunks_prefix_and_limit(storage: QdrantVectorStorage) -> None:
    """Prefix must scope results; limit truncates the page-ordered list."""
    storage.store_batch(
        [
            _doc("b2", source="book2.pdf", page=1),
            _doc("b1a", source="book1.pdf", page=3),
            _doc("b1b", source="book1.pdf", page=2),
            _doc("b1h", source="book1.pdf", page=0, role="heading"),
        ]
    )

    scoped = storage.find_structural_chunks(
        source_prefix="book1", element_types=["paragraph"]
    )
    assert [c["chunk_id"] for c in scoped] == ["b1h", "b1b", "b1a"]

    limited = storage.find_structural_chunks(
        source_prefix="book1", element_types=["paragraph"], limit=2
    )
    assert [c["chunk_id"] for c in limited] == ["b1h", "b1b"]

    from_other = storage.find_structural_chunks(
        source_prefix="book2", element_types=["paragraph"]
    )
    assert [c["chunk_id"] for c in from_other] == ["b2"]


def test_find_structural_chunks_unfiltered_returns_everything(
    storage: QdrantVectorStorage,
) -> None:
    """No filters at all: scroll_filter is None (the all-fallback path)."""
    storage.store_batch(
        [
            _doc("late", page=4),
            _doc("early", page=1),
            _doc("mid", page=2),
        ]
    )

    results = storage.find_structural_chunks()
    assert [c["chunk_id"] for c in results] == ["early", "mid", "late"]


def test_get_body_chunks_page_gte_range_filter(storage: QdrantVectorStorage) -> None:
    """page_gte builds a Range filter: pages >= N, applied before limit."""
    storage.store_batch(
        [
            _doc("p1", page=1),
            _doc("p3", page=3),
            _doc("p5", page=5),
            _doc("head", page=3, role="heading"),
        ]
    )

    from3 = storage.get_body_chunks("book.pdf", page_gte=3)
    assert [c["chunk_id"] for c in from3] == ["p3", "p5"]

    limited = storage.get_body_chunks("book.pdf", page_gte=1, limit=2)
    assert [c["chunk_id"] for c in limited] == ["p1", "p3"]


def test_get_body_chunks_excludes_other_roles_and_sources(
    storage: QdrantVectorStorage,
) -> None:
    storage.store_batch(
        [
            _doc("b1", page=1),
            _doc("head", page=2, role="heading"),
            _doc("other", source="elsewhere.pdf", page=2),
        ]
    )

    assert [c["chunk_id"] for c in storage.get_body_chunks("book.pdf")] == ["b1"]


def test_get_body_chunks_strips_text(storage: QdrantVectorStorage) -> None:
    storage.store(_doc("b1", text="secret"))

    stripped = storage.get_body_chunks("book.pdf", with_text=False)
    assert [c["chunk_id"] for c in stripped] == ["b1"]
    assert all(c["chunk_text"] is None for c in stripped)

    full = storage.get_body_chunks("book.pdf")
    assert full[0]["chunk_text"] == "secret"


def test_count_chunks_filters(storage: QdrantVectorStorage) -> None:
    storage.store_batch(
        [
            _doc("a1", source="a.pdf", page=1),
            _doc("a2", source="a.pdf", page=2),
            _doc("ah", source="a.pdf", page=3, role="heading"),
            _doc("b1", source="b.pdf", page=1),
        ]
    )

    assert storage.count_chunks() == 4
    assert storage.count_chunks(source_file="a.pdf") == 3
    assert storage.count_chunks(chunk_role="heading") == 1
    assert storage.count_chunks(source_file="a.pdf", chunk_role="body") == 2
    assert storage.count_chunks(source_file="nope.pdf") == 0


def test_get_stats_shape(storage: QdrantVectorStorage) -> None:
    storage.store_batch([_doc("a1", source="a.pdf"), _doc("b1", source="b.pdf")])

    stats = storage.get_stats()
    assert stats["total_chunks"] == 2
    assert stats["unique_sources"] == 2
    assert stats["database"] == "qdrant"
    assert stats["collection"] == "filter_tests"


def test_validate_connection_ttl_cache(storage: QdrantVectorStorage) -> None:
    """Second non-forced call reuses the TTL-cached result without probing."""
    storage.validate_connection()
    assert storage._conn_valid is True
    assert storage.validate_connection() is True
    assert storage.validate_connection(force=True) is True


def test_context_manager_closes_client() -> None:
    instance = QdrantVectorStorage(collection_name="ctx")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM

    with instance as entered:
        assert entered is instance

    assert instance._client is None


def test_search_async_and_store_batch_async(storage: QdrantVectorStorage) -> None:
    import asyncio

    count = asyncio.run(storage.store_batch_async([_doc("a1"), _doc("a2")]))
    assert count == 2

    results = asyncio.run(storage.search_async([0.1, 0.2, 0.3, 0.4], top_k=5))
    assert len(results) == 2
