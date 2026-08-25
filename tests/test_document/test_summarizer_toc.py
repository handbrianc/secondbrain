"""Tests for the TOC/heading-based chapter detection fallback in the Summarizer."""

from __future__ import annotations

from secondbrain.document.summarizer import Summarizer


class _MockProvider:
    pass


class _MockStorage:
    """Storage with no chapter/section metadata; find_chunks returns all chunks."""

    def __init__(self, chunks: list[dict]) -> None:
        self._chunks = chunks

    def find_chunks(
        self,
        source_file: str | None = None,
        *,
        chapter_id: str | None = None,
        section_id: str | None = None,
        section_id_pattern: str | None = None,
        with_text: bool = True,
    ):
        if chapter_id or section_id or section_id_pattern:
            return []
        return [dict(c) for c in self._chunks if c.get("source_file") == source_file]


def _chunk(page: int, text: str, role: str = "body") -> dict:
    return {
        "chunk_id": f"c{page}",
        "chunk_role": role,
        "page_number": page,
        "chunk_text": text,
        "source_file": "book.pdf",
    }


def _summarizer(chunks: list[dict]) -> Summarizer:
    return Summarizer(
        llm_provider=_MockProvider(),
        embedder=_MockProvider(),
        storage=_MockStorage(chunks),
    )


def test_chapter_page_map_detects_heading_at_chunk_start() -> None:
    s = _summarizer(
        [
            _chunk(10, "Chapter 1 5\nIntro text about the book."),
            _chunk(34, "Some front-matter that mentions Chapter 1 mid-sentence"),
            _chunk(50, "Chapter 2 20\nFirst section of chapter two."),
            _chunk(99, "Chapter 3 44\nThird chapter begins."),
        ]
    )
    # Front-matter (34) and cross-references mid-text must be ignored; only
    # chunk-start headings are counted, and the earliest page per chapter wins.
    assert s._chapter_page_map("book.pdf") == {1: 10, 2: 50, 3: 99}


def test_collect_chapters_by_page_slices_by_page_range() -> None:
    s = _summarizer(
        [
            _chunk(10, "Chapter 1 5\nbody"),
            _chunk(50, "Chapter 2 20\nbody"),
            _chunk(99, "Chapter 3 44\nbody"),
            _chunk(60, "content between chapter 2 and 3"),
            _chunk(120, "later content in chapter 3"),
            _chunk(200, "caption after chapter 3", role="caption"),
        ]
    )
    c2 = s._collect_chapters_by_page(2, "book.pdf")
    pages = sorted(c["page_number"] for c in c2)
    assert pages == [50, 60]
    # Captions count; ensure chapter 3 range excludes chapter-2 content.
    c3 = s._collect_chapters_by_page(3, "book.pdf")
    assert [c["page_number"] for c in c3] == [99, 120, 200]


def test_collect_chapters_by_page_unknown_chapter_is_empty() -> None:
    s = _summarizer([_chunk(10, "Chapter 1 5\nbody")])
    assert s._collect_chapters_by_page(7, "book.pdf") == []


def test_collect_chapter_chunks_falls_back_to_page_map_when_no_metadata() -> None:
    s = _summarizer(
        [
            _chunk(10, "Chapter 1 5\nbody"),
            _chunk(50, "Chapter 2 20\nbody"),
            _chunk(60, "chapter two content"),
        ]
    )
    collected = s._collect_chapter_chunks(2, source_file="book.pdf")
    assert sorted(c["page_number"] for c in collected) == [50, 60]


def test_chapter_map_is_cached_per_source() -> None:
    s = _summarizer([_chunk(10, "Chapter 1 5\nbody")])
    assert s._chapter_page_map("book.pdf") is s._chapter_page_map("book.pdf")
