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

    def test_chunk_with_heading_path_gets_label(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Snapshot mode stores VM state.",
                "source_file": "doc.pdf",
                "page": 12,
                "chunk_role": "body",
                "heading_path": "Chapter 16 > Backup Modes > snapshot mode",
            },
        ]
        out = pipeline._format_context(chunks)
        assert (
            "Source: doc.pdf (page 12 [body, Chapter 16 > Backup Modes > snapshot mode])"
            in out
        )

    def test_heading_path_appended_after_role_and_label(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Chapter 3: Setup",
                "source_file": "d.pdf",
                "page": 1,
                "chunk_role": "heading",
                "heading_path": "Part I > Installation",
            },
        ]
        out = pipeline._format_context(chunks)
        # Tag order: chunk_role, inferred section label, heading path last.
        assert "[heading, Chapter 3:: Setup, Part I > Installation]" in out

    def test_chunk_without_heading_path_unchanged(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {"chunk_text": "Hello", "source_file": "doc.pdf", "page": 1},
        ]
        # Byte-identical to the pre-heading-path format.
        assert pipeline._format_context(chunks) == "Source: doc.pdf (page 1)\nHello\n"

    def test_empty_and_none_heading_path_unchanged(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Hello",
                "source_file": "doc.pdf",
                "page": 1,
                "heading_path": "",
            },
            {
                "chunk_text": "World",
                "source_file": "doc.pdf",
                "page": 2,
                "heading_path": None,
            },
        ]
        assert pipeline._format_context(chunks) == (
            "Source: doc.pdf (page 1)\nHello\n\n\nSource: doc.pdf (page 2)\nWorld\n"
        )

    def test_labels_are_per_chunk(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "VM snapshot text",
                "source_file": "doc.pdf",
                "page": 12,
                "chunk_role": "body",
                "heading_path": "Chapter 16 > Backup > VM > snapshot mode",
            },
            {
                "chunk_text": "Container snapshot text",
                "source_file": "doc.pdf",
                "page": 40,
                "chunk_role": "body",
                "heading_path": "Chapter 16 > Backup > Containers > snapshot mode",
            },
            {
                "chunk_text": "Unlabeled text",
                "source_file": "doc.pdf",
                "page": 41,
            },
        ]
        out = pipeline._format_context(chunks)
        assert (
            "Source: doc.pdf (page 12 [body, Chapter 16 > Backup > VM > snapshot mode])"
            in out
        )
        assert (
            "Source: doc.pdf (page 40 [body, Chapter 16 > Backup > Containers > snapshot mode])"
            in out
        )
        assert "Source: doc.pdf (page 41)\nUnlabeled text\n" in out

    def test_heading_path_counts_toward_max_chars(self) -> None:
        pipeline = _make_pipeline()
        heading_path = "Chapter 16 — Backup and Restore > Backup Modes > snapshot mode"
        chunks = [
            {
                "chunk_text": "first",
                "source_file": "a.pdf",
                "page": 1,
                "chunk_role": "body",
                "heading_path": heading_path,
            },
            {"chunk_text": "second", "source_file": "b.pdf", "page": 2},
        ]
        first_entry = f"Source: a.pdf (page 1 [body, {heading_path}])\nfirst\n"
        # The labeled entry alone fits the budget; the next chunk must not be
        # added — the label's length participates in the accounting.
        out = pipeline._format_context(chunks, max_chars=len(first_entry) + 1)
        assert "a.pdf" in out
        assert heading_path in out
        assert "b.pdf" not in out

    def test_part_source_prefixes_a_part_header_line(self) -> None:
        # Multi-source assembly (fix-chat-session-integrity D2): the part
        # header line sits above the untouched per-chunk format.
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Snapshot mode stores VM state.",
                "source_file": "doc.pdf",
                "page": 12,
                "chunk_role": "body",
                "heading_path": "Chapter 16 > Backup Modes > snapshot mode",
            },
        ]
        out = pipeline._format_context(chunks, part_source="doc.pdf")
        assert out == (
            "Source: doc.pdf\n"
            "Source: doc.pdf (page 12 [body, Chapter 16 > Backup Modes > snapshot mode])\n"
            "Snapshot mode stores VM state.\n"
        )

    def test_default_output_stays_byte_identical(self) -> None:
        # part_source=None (the default) must not change the single-source
        # output — including the in-flight heading_path tag.
        pipeline = _make_pipeline()
        chunks = [
            {
                "chunk_text": "Snapshot mode stores VM state.",
                "source_file": "doc.pdf",
                "page": 12,
                "chunk_role": "body",
                "heading_path": "Chapter 16 > Backup Modes > snapshot mode",
            },
        ]
        assert pipeline._format_context(chunks) == pipeline._format_context(
            chunks, part_source=None
        )
        assert pipeline._format_context(chunks) == (
            "Source: doc.pdf (page 12 [body, Chapter 16 > Backup Modes > snapshot mode])\n"
            "Snapshot mode stores VM state.\n"
        )

    def test_multi_source_parts_join_with_per_part_headers(self) -> None:
        pipeline = _make_pipeline()
        parts = [
            (
                "a.pdf",
                [
                    {
                        "chunk_text": "Alpha material",
                        "source_file": "a.pdf",
                        "page": 21,
                        "chunk_role": "body",
                        "heading_path": "Chapter 15 > High Availability",
                    }
                ],
            ),
            (
                "b.pdf",
                [
                    {
                        "chunk_text": "Beta material",
                        "source_file": "b.pdf",
                        "page": 60,
                    }
                ],
            ),
            # An empty part carries no attributable content: skipped.
            ("c.pdf", []),
        ]
        out = pipeline._format_multi_source_parts(parts)
        assert out == (
            "Source: a.pdf\n"
            "Source: a.pdf (page 21 [body, Chapter 15 > High Availability])\n"
            "Alpha material\n"
            "\n\n"
            "Source: b.pdf\n"
            "Source: b.pdf (page 60)\n"
            "Beta material\n"
        )

    def test_multi_source_parts_with_no_chunks_is_empty(self) -> None:
        pipeline = _make_pipeline()
        assert pipeline._format_multi_source_parts([("a.pdf", [])]) == ""
        assert pipeline._format_multi_source_parts([]) == ""

    def test_part_header_respects_the_per_part_budget(self) -> None:
        pipeline = _make_pipeline()
        chunks = [
            {"chunk_text": "first", "source_file": "a.pdf", "page": 1},
            {"chunk_text": "second", "source_file": "a.pdf", "page": 2},
        ]
        first_entry = "Source: a.pdf (page 1)\nfirst\n"
        out = pipeline._format_multi_source_parts(
            [("a.pdf", chunks)], max_chars_per_part=len(first_entry) + 1
        )
        # The budget is applied to the part's body (the header prefix rides
        # on top), so only the first chunk fits.
        assert out == "Source: a.pdf\n" + first_entry


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
