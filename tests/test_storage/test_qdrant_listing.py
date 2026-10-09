"""Branch tests for ``QdrantVectorStorage`` listing, facets, and deletes.

Covers the read/metadata branches not exercised by the roundtrip tests:
``list_chunks`` filters and pagination (the in-process offset slice and the
scroll-loop limit break), the facet→scroll fallback in ``list_source_files``,
empty ``has_existing_hashes``, ``get_source_chunks`` limit/no-text, and the
``delete_by_chunk_id`` / ``delete_all`` paths.
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
    instance = QdrantVectorStorage(collection_name="listing_tests")
    instance._client = QdrantClient(":memory:")
    instance._dimensions = DIM
    return instance


def _doc(
    chunk_id: str,
    *,
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


class TestListChunks:
    """list_chunks filters, pagination, and offset slicing."""

    def test_no_filters_returns_all_chunks(self, storage: QdrantVectorStorage) -> None:
        """Without filters the scroll filter is None and every chunk returns."""
        storage.store_batch([_doc("c1", source="a.pdf"), _doc("c2", source="b.pdf")])

        chunks = storage.list_chunks()

        assert {c["chunk_id"] for c in chunks} == {"c1", "c2"}

    def test_source_filter_matches_text_tokens(
        self, storage: QdrantVectorStorage
    ) -> None:
        """Default source filtering uses MatchText (full-text token match).

        MatchText tokenizes the query and the stored value, so a filter matches
        sources containing the whole token — ``beta`` matches ``beta.pdf`` but
        not ``beta2.pdf`` (no true substring prefixing).
        """
        storage.store_batch(
            [
                _doc("a1", source="alpha.pdf"),
                _doc("b1", source="beta.pdf"),
                _doc("b2", source="beta2.pdf"),
            ]
        )

        alpha = storage.list_chunks(source_filter="alpha")
        beta = storage.list_chunks(source_filter="beta")

        assert {c["source_file"] for c in alpha} == {"alpha.pdf"}
        assert {c["source_file"] for c in beta} == {"beta.pdf"}

    def test_source_exact_match(self, storage: QdrantVectorStorage) -> None:
        """use_prefix_match=False switches to an exact keyword match."""
        storage.store_batch(
            [
                _doc("a1", source="alpha.pdf"),
                _doc("a2", source="alpha2.pdf"),
            ]
        )

        chunks = storage.list_chunks(source_filter="alpha.pdf", use_prefix_match=False)

        assert {c["chunk_id"] for c in chunks} == {"a1"}

    def test_chunk_id_filter(self, storage: QdrantVectorStorage) -> None:
        """chunk_id narrows the listing to exactly that chunk."""
        storage.store_batch([_doc("c1"), _doc("c2")])

        chunks = storage.list_chunks(chunk_id="c2")

        assert [c["chunk_id"] for c in chunks] == ["c2"]

    def test_offset_and_limit_pagination(self, storage: QdrantVectorStorage) -> None:
        """Disjoint pages cover the collection; the scroll loop stops at limit."""
        storage.store_batch(
            [_doc(f"c{i}") for i in range(1, 5)]  # 4 chunks
        )

        page0 = storage.list_chunks(limit=2, offset=0)
        page1 = storage.list_chunks(limit=2, offset=2)

        ids0 = {c["chunk_id"] for c in page0}
        ids1 = {c["chunk_id"] for c in page1}
        assert len(ids0) == 2
        assert len(ids1) == 2
        assert ids0.isdisjoint(ids1)
        assert ids0 | ids1 == {"c1", "c2", "c3", "c4"}

    def test_offset_beyond_total_returns_empty(
        self, storage: QdrantVectorStorage
    ) -> None:
        """An offset past the end selects nothing."""
        storage.store_batch([_doc("c1"), _doc("c2")])

        assert storage.list_chunks(limit=2, offset=10) == []


class TestListSourceFilesFallback:
    """The facet→scroll-and-dedupe fallback for list_source_files."""

    @pytest.mark.parametrize("exc_type", [AttributeError, TypeError])
    def test_falls_back_to_scroll_when_facet_unsupported(
        self,
        storage: QdrantVectorStorage,
        monkeypatch: pytest.MonkeyPatch,
        exc_type: type[Exception],
    ) -> None:
        """A facet-incapable client still yields distinct sorted sources."""

        def broken_facet(**kwargs: Any) -> Any:
            raise exc_type("facet unsupported")

        monkeypatch.setattr(storage._client, "facet", broken_facet)
        storage.store_batch(
            [
                _doc("c1", source="b.pdf"),
                _doc("c2", source="a.pdf"),
                _doc("c3", source="b.pdf"),
            ]
        )

        assert storage.list_source_files() == ["a.pdf", "b.pdf"]


class TestHashesAndSourceChunks:
    """has_existing_hashes and get_source_chunks branches."""

    def test_has_existing_hashes_empty_input_returns_empty(
        self, storage: QdrantVectorStorage
    ) -> None:
        """An empty hash list short-circuits to an empty set."""
        assert storage.has_existing_hashes([]) == set()

    def test_get_source_chunks_limit_truncates_after_page_sort(
        self, storage: QdrantVectorStorage
    ) -> None:
        """Limit keeps the first page-ordered chunks only."""
        storage.store_batch(
            [
                _doc("p3", page=3),
                _doc("p1", page=1),
                _doc("p2", page=2),
            ]
        )

        chunks = storage.get_source_chunks("a.pdf", limit=2)

        assert [c["chunk_id"] for c in chunks] == ["p1", "p2"]

    def test_get_source_chunks_without_text_drops_payload_text(
        self, storage: QdrantVectorStorage
    ) -> None:
        """with_text=False strips chunk_text from the returned payload."""
        storage.store(_doc("c1", text="secret"))

        stripped = storage.get_source_chunks("a.pdf", with_text=False)

        assert [c["chunk_id"] for c in stripped] == ["c1"]
        assert all(c["chunk_text"] is None for c in stripped)

        full = storage.get_source_chunks("a.pdf")
        assert full[0]["chunk_text"] == "secret"


class TestDeleteBranches:
    """delete_by_chunk_id and delete_all (the Filter(must=[]) path)."""

    def test_delete_by_chunk_id_removes_single_chunk(
        self, storage: QdrantVectorStorage
    ) -> None:
        """Deleting by chunk_id removes exactly one point; repeat deletes 0."""
        storage.store_batch([_doc("c1"), _doc("c2")])

        assert storage.delete_by_chunk_id("c1") == 1
        assert storage.count_chunks() == 1
        assert storage.delete_by_chunk_id("c1") == 0

    def test_delete_all_removes_everything_and_is_repeatable(
        self, storage: QdrantVectorStorage
    ) -> None:
        """delete_all uses the empty-filter path and returns the removed count."""
        storage.store_batch([_doc("c1", source="a.pdf"), _doc("c2", source="b.pdf")])

        assert storage.delete_all() == 2
        assert storage.count_chunks() == 0
        assert storage.delete_all() == 0
