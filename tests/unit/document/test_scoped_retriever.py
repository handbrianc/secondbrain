"""ScopedRetriever scope-filter behavior tests."""

from typing import Any

import pytest

from secondbrain.document.scoped_retriever import (
    ScopedRetriever,
    _apply_scope_filter,
    _matches_filter,
)


class TestHeadingScope:
    def test_keeps_structural_element_types(self) -> None:
        results = [
            {"element_type": "heading", "chunk_text": "h"},
            {"element_type": "toc_entry", "chunk_text": "t"},
            {"element_type": "body", "chunk_text": "b"},
            {"element_type": "navigation", "chunk_text": "n"},
            {"element_type": "caption", "chunk_text": "c"},
        ]

        kept = _apply_scope_filter(results, "heading")

        assert kept == [
            {"element_type": "heading", "chunk_text": "h"},
            {"element_type": "toc_entry", "chunk_text": "t"},
        ]

    def test_falls_back_to_chunk_role(self) -> None:
        results = [{"chunk_role": "heading"}, {"chunk_role": "body"}]

        kept = _apply_scope_filter(results, "heading")

        assert kept == [{"chunk_role": "heading"}]

    def test_reads_metadata_mappings(self) -> None:
        results = [
            {"metadata": {"element_type": "toc_entry"}},
            {"metadata": {"chunk_role": "body"}},
        ]

        kept = _apply_scope_filter(results, "heading")

        assert kept == [{"metadata": {"element_type": "toc_entry"}}]

    def test_keeps_legacy_roleless_chunks(self) -> None:
        results = [{"chunk_text": "legacy"}, {"metadata": {}}]

        kept = _apply_scope_filter(results, "heading")

        assert kept == results

    def test_payload_wins_over_metadata(self) -> None:
        results = [{"element_type": "body", "metadata": {"element_type": "heading"}}]

        kept = _apply_scope_filter(results, "heading")

        assert kept == []


class TestSectionScopes:
    def test_numeric_scope_prefix_matching(self) -> None:
        results = [
            {"section_id": "3.9", "chunk_text": "a"},
            {"section_id": "3.9.1", "chunk_text": "b"},
            {"section_id": "4.0", "chunk_text": "c"},
            {"chunk_text": "legacy"},
        ]

        kept = _apply_scope_filter(results, "3.9")

        assert kept == [
            {"section_id": "3.9", "chunk_text": "a"},
            {"section_id": "3.9.1", "chunk_text": "b"},
            {"chunk_text": "legacy"},
        ]

    def test_wildcard_scope_matches_children(self) -> None:
        results = [
            {"section_id": "4.1"},
            {"section_id": "4.10"},
            {"section_id": "5.1"},
        ]

        kept = _apply_scope_filter(results, "4.*")

        assert [c["section_id"] for c in kept] == ["4.1", "4.10"]

    def test_empty_scope_passthrough(self) -> None:
        results = [{"section_id": "3.9"}]

        assert _apply_scope_filter(results, "") == results


class TestMatchesFilter:
    def test_in_operator(self) -> None:
        filt = {"element_type": {"$in": ["heading", "toc_entry"]}}

        assert _matches_filter({"element_type": "heading"}, filt) is True
        assert _matches_filter({"element_type": "toc_entry"}, filt) is True
        assert _matches_filter({"element_type": "body"}, filt) is False

    def test_regex_operator_scopes_by_prefix(self) -> None:
        filt = {"section_id": {"$regex": r"^3\.9(?:\.|$)"}}

        assert _matches_filter({"section_id": "3.9"}, filt) is True
        assert _matches_filter({"section_id": "3.9.1"}, filt) is True
        assert _matches_filter({"section_id": "4.0"}, filt) is False

    def test_missing_field_fails_closed(self) -> None:
        filt = {"section_id": {"$eq": "3.9"}}

        assert _matches_filter({}, filt) is False


class _FakeSearcher:
    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results

    def search(self, query: str, *, top_k: int, **kwargs: Any) -> list[dict[str, Any]]:
        return self.results

    async def search_async(
        self, query: str, *, top_k: int, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return self.results


class TestScopedRetrieverIntegration:
    def test_search_applies_heading_scope(self) -> None:
        inner = _FakeSearcher([{"element_type": "heading"}, {"element_type": "body"}])
        retriever = ScopedRetriever(inner=inner)

        out = retriever.search("q", top_k=5, scope="heading")

        assert out == [{"element_type": "heading"}]

    @pytest.mark.asyncio
    async def test_search_async_applies_numeric_scope(self) -> None:
        inner = _FakeSearcher([{"section_id": "3.9"}, {"section_id": "4.0"}])
        retriever = ScopedRetriever(inner=inner)

        out = await retriever.search_async("q", top_k=5, scope="3.9")

        assert out == [{"section_id": "3.9"}]

    def test_no_scope_passthrough(self) -> None:
        inner = _FakeSearcher([{"x": 1}])
        retriever = ScopedRetriever(inner=inner)

        assert retriever.search("q", top_k=3) == [{"x": 1}]
