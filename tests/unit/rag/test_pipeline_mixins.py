"""Unit tests for cohesive RAG pipeline helper mixins.

Covers the small, self-contained helpers extracted into the pipeline's
``_mixins`` module: context formatting, chunk deduplication, and section-label
inference. These are pure/state-light helpers, so the tests construct a minimal
``RAGPipeline`` via the public constructor with mocks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from secondbrain.rag.pipeline import RAGPipeline


def _make_pipeline(config_overrides: dict[str, Any] | None = None) -> RAGPipeline:
    searcher = MagicMock()
    llm = MagicMock()
    pipeline = RAGPipeline(searcher=searcher, llm_provider=llm, top_k=5)
    cfg = pipeline._config
    for key, value in (config_overrides or {}).items():
        setattr(cfg, key, value)
    return pipeline


class TestFormatContext:
    def test_empty_chunks_returns_empty_string(self) -> None:
        assert _make_pipeline()._format_context([]) == ""

    def test_basic_chunk_formatting(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {"chunk_text": "Hello", "source_file": "doc.pdf", "page": 1},
        ]
        out = pipeline._format_context(chunks)
        assert "Source: doc.pdf (page 1)" in out
        assert "Hello" in out

    def test_max_chars_truncates(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {"chunk_text": "aaaa", "source_file": "a.pdf", "page": 1},
            {"chunk_text": "bbbb", "source_file": "b.pdf", "page": 1},
        ]
        # A tiny budget lets at most the first chunk fit.
        out = pipeline._format_context(chunks, max_chars=30)
        assert "a.pdf" in out
        assert "b.pdf" not in out

    def test_long_chunk_truncates_with_ellipsis(self) -> None:
        pipeline = _make_pipeline({"rag_chunk_preview_chars": 5})
        chunks = [{"chunk_text": "1234567890", "source_file": "d.pdf", "page": 1}]
        out = pipeline._format_context(chunks)
        assert "..." in out
        assert "12345" in out

    def test_heading_tag_and_label(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Chapter 3: Setup",
                "source_file": "d.pdf",
                "page": 1,
                "chunk_role": "heading",
            },
        ]
        out = pipeline._format_context(chunks)
        assert "heading" in out
        assert "Chapter 3" in out


class TestDedupeByTextHash:
    def test_removes_duplicates_keeps_order(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {"chunk_text": "same content here"},
            {"chunk_text": "different content"},
            {"chunk_text": "same content here"},
        ]
        deduped = pipeline._dedupe_by_text_hash(chunks)
        assert len(deduped) == 2
        assert deduped[0]["chunk_text"] == "same content here"
        assert deduped[1]["chunk_text"] == "different content"

    def test_empty_input(self) -> None:
        assert _make_pipeline()._dedupe_by_text_hash([]) == []


class TestInferSectionLabel:
    def test_non_heading_returns_none(self) -> None:
        pipeline = _make_pipeline()
        assert pipeline._infer_section_label("text", "body") is None

    def test_heading_without_label_returns_none(self) -> None:
        pipeline = _make_pipeline()
        assert pipeline._infer_section_label("plain text", "heading") is None

    def test_heading_with_label(self) -> None:
        pipeline = _make_pipeline()
        label = pipeline._infer_section_label("Chapter 3: Setup", "heading")
        assert label is not None
        assert "Chapter 3" in label
