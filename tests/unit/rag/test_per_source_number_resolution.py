"""Per-source resolution of numbered chapter/section queries.

Covers fix-chat-session-integrity tasks 2.2-2.3 (design D1-D3):

1. Collision: two sources whose trees both carry chapter 15 get one labeled
   window each — no chunk-count document pick silently answers one manual's
   chapter for the other (spec: "Same chapter number in two sources").
2. Window purity: even a storage double that ignores the ``find_chunks``
   source filter cannot mix the colliding source into a window (D3 — the
   assembly-level filter is the last line of defense, and with colliding
   node ids/chapter ids across sources the ONLY one that can tell them
   apart).
3. Unique number: a number carried by exactly one source resolves against
   that source directly; a single-source collection stays byte-identical to
   the chunk-count pick it replaces (spec: "Number unique to one source").
4. Source mention: a resolved ``source_filter`` scopes resolution to that
   source even when the other source is much larger (spec: "Source mention
   scopes resolution").
5. Unchanged paths: a number no tree carries, a window that fails to
   resolve, and target-less overview queries keep the legacy chunk-count
   behavior; attribution shows up as ``Source: <file>`` part headers in the
   generation context while per-line tags stay untouched.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)
from tests.unit.rag._chapter_fixture_storage import ChapterFixtureStorage

_PVE = "/docs/pve-admin-guide.pdf"
_VBOX = "/docs/virtualbox-manual.pdf"

# Both books paginate from page 1 and collide on chapter 15 (High
# Availability vs VBoxManage) AND on its section numbers; chapter 7 exists
# only in the pve guide, chapter 2 only in the VirtualBox manual.
_PVE_CHAPTERS = {1: (1, 2), 7: (13, 14), 15: (21, 24), 16: (25, 26)}
_VBOX_CHAPTERS = {1: (1, 2), 2: (3, 4), 15: (21, 24), 16: (25, 26)}
_PVE_SECTIONS = {"15.1": (21, 21), "15.2": (22, 23)}
_VBOX_SECTIONS = {"15.1": (21, 21), "15.2": (22, 23)}
_PVE_TITLES = {15: "High Availability"}
_VBOX_TITLES = {15: "VBoxManage"}

# The VirtualBox manual is the "bigger" document: extra filler body chunks
# on non-section pages make it win the legacy chunk-count document pick, so
# every test here also proves the pick did NOT govern the answer.
_VBOX_FILLER = [(1, 3), (2, 3), (3, 3), (4, 3), (25, 3), (26, 3)]

_CANNED_ANSWER = (
    "The Proxmox guide's chapter covers high availability clustering, while "
    "the VirtualBox manual's chapter documents the VBoxManage command "
    "reference. Each source's material is summarized separately below."
)

_HEADER_RE = re.compile(r"^Source: (\S+)\n", re.MULTILINE)
_CHUNK_SOURCE_RE = re.compile(r"^Source: (\S+) \(page (\d+)", re.MULTILINE)


class _TreeSearcher:
    """Searcher double carrying the fixture storage."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    """LLM double returning one fixed, plausible, figure-free sentence.

    Records every prompt it receives — the map-reduce summarizers reach the
    provider directly (not through ``_generate``/``_vet_answer``), so the
    provider is the one seam that sees all generation traffic.
    """

    def __init__(self, answer: str = _CANNED_ANSWER) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.prompts.append(prompt)
        return self.answer


class _NullProvider:
    """LLM double returning "" — the fallback-roster path speaks instead."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 512
    ) -> str:
        return ""


class _MultiSourceStorage(ChapterFixtureStorage):  # type: ignore[misc]
    """Fixture double extended with the page-list ``find_chunks`` API.

    Mirrors the live ``find_chunks`` semantics (equality on ``source_file``,
    exact MatchAny page-number list, no role filter).  ``honor_source=False``
    turns the double into a leaky store that ignores the source filter — the
    adversarial shape the assembly-level purity filter (D3) must survive.
    """

    def __init__(
        self, chunks: list[dict[str, Any]], *, honor_source: bool = True
    ) -> None:
        super().__init__(chunks)
        self._honor_source = honor_source

    def find_chunks(
        self,
        source_file: str | None = None,
        *,
        chapter_id: str | None = None,
        section_id: str | None = None,
        section_id_pattern: str | None = None,
        printed_page: int | str | None = None,
        page_number: int | list[int] | None = None,
        with_text: bool = True,
    ) -> list[dict[str, Any]]:
        pages: list[int] | None = None
        if isinstance(page_number, list):
            pages = page_number
        elif page_number is not None:
            pages = [page_number]
        out: list[dict[str, Any]] = []
        for chunk in self._chunks:
            if (
                self._honor_source
                and source_file
                and chunk.get("source_file") != source_file
            ):
                continue
            if pages is not None and (chunk.get("page_number") or 0) not in pages:
                continue
            out.append(dict(chunk))
        return out


def _save_tree(
    store: StructureStore,
    source_file: str,
    chapters: dict[int, tuple[int, int]],
    sections: dict[str, tuple[int, int]],
    *,
    titles: dict[int, str] | None = None,
    drop_page_range_for: set[int] | None = None,
) -> None:
    """Persist a synthetic capture tree for one book."""
    drop = drop_page_range_for or set()
    nodes: list[StructureNode] = []
    for ch, (start, end) in chapters.items():
        nodes.append(
            StructureNode(
                node_id=f"ch-{ch}",
                parent_id=None,
                kind="chapter",
                level=1,
                number=str(ch),
                title=(titles or {}).get(ch, f"Title {ch}"),
                page_start=None if ch in drop else start,
                page_end=None if ch in drop else end,
                heading_path=f"Chapter {ch}",
            )
        )
        for sec, (sec_start, sec_end) in sections.items():
            if not sec.startswith(f"{ch}."):
                continue
            nodes.append(
                StructureNode(
                    node_id=f"sec-{sec}",
                    parent_id=f"ch-{ch}",
                    kind="section",
                    level=2,
                    number=sec,
                    title=f"Section {sec}",
                    page_start=sec_start,
                    page_end=sec_end,
                    heading_path=f"Chapter {ch} / Section {sec}",
                )
            )
    store.save_structure(
        DocumentStructure(
            source_file=source_file,
            nodes=nodes,
            sources={source_file: True},
            captured_at="2026-10-29T00:00:00+00:00",
        )
    )


def _book_chunks(
    source_file: str,
    chapters: dict[int, tuple[int, int]],
    sections: dict[str, tuple[int, int]],
    *,
    filler: list[tuple[int, int]] | None = None,
) -> list[dict[str, Any]]:
    """Body chunks for one book with owner-annotated fillers.

    Section-owned on section pages, chapter-owned elsewhere, plus
    optional owner-annotated filler to inflate the chunk-count pick.
    """
    name = source_file.rsplit("/", 1)[-1].removesuffix(".pdf")
    chunks: list[dict[str, Any]] = []
    pos_by_page: dict[int, int] = {}

    def add(page: int, text: str, **meta: Any) -> None:
        pos = pos_by_page.get(page, 0)
        pos_by_page[page] = pos + 1
        chunk: dict[str, Any] = {
            "chunk_id": f"{source_file}#p{page}c{pos}",
            "source_file": source_file,
            "page_number": page,
            "page_pos": pos,
            "chunk_text": text,
            "element_type": "paragraph",
            "chunk_role": "body",
            "score": 0.5,
        }
        chunk.update(meta)
        chunks.append(chunk)

    section_page_of: dict[int, str] = {}
    for sec, (start, end) in sections.items():
        for page in range(start, end + 1):
            section_page_of[page] = sec

    for ch, (start, end) in chapters.items():
        for page in range(start, end + 1):
            sec = section_page_of.get(page)
            if sec is not None:
                add(
                    page,
                    f"{name} section {sec} guidance on page {page}.",
                    node_id=f"sec-{sec}",
                    chapter_id=str(ch),
                    section_id=sec,
                )
            else:
                add(
                    page,
                    f"{name} chapter {ch} material on page {page}.",
                    node_id=f"ch-{ch}",
                    chapter_id=str(ch),
                )
    for page, count in filler or []:
        owner = next(
            ch
            for ch, (start, end) in chapters.items()
            if start <= page <= end and page not in section_page_of
        )
        for i in range(count):
            add(
                page,
                f"{name} filler prose {i} on page {page}.",
                node_id=f"ch-{owner}",
                chapter_id=str(owner),
            )
    return chunks


def _make_pipeline(
    storage: Any,
    provider: Any,
    store: StructureStore | None = None,
) -> RAGPipeline:
    """Pipeline wired to the storage double, with an optional injected store."""
    pipeline = RAGPipeline(
        searcher=_TreeSearcher(storage),  # type: ignore[arg-type]
        llm_provider=provider,
        top_k=8,
    )
    pipeline._config.streaming_enabled = False
    if store is not None:
        pipeline._structure_store = store
        pipeline._structure_store_ready = True
    return pipeline


class _GenerationCapture:
    """Record every (prompt, context) reaching the generation boundary.

    Both seams are wrapped: the tree/dotted path vets through
    ``_vet_answer(prompt, context)``, while the map-reduce summarizers call
    ``_generate(prompt)`` directly — a capture on either alone misses the
    other's traffic.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.contexts: list[str] = []

    def attach(self, pipeline: RAGPipeline, monkeypatch: pytest.MonkeyPatch) -> None:
        real_vet = pipeline._vet_answer
        real_generate = pipeline._generate

        def vet(text: str, prompt: str, context: str) -> str:
            self.prompts.append(prompt)
            self.contexts.append(context)
            return real_vet(text, prompt, context)

        def generate(prompt: str) -> str:
            self.prompts.append(prompt)
            return real_generate(prompt)

        monkeypatch.setattr(pipeline, "_vet_answer", vet)
        monkeypatch.setattr(pipeline, "_generate", generate)


def _split_parts(context: str) -> list[tuple[str, str]]:
    """Split a multi-part context into ``(source, body)`` blocks.

    Only bare ``Source: <file>`` header lines split (per-chunk lines carry a
    `` (page …`` suffix, so the header pattern's non-space class can never
    reach the newline).
    """
    matches = list(_HEADER_RE.finditer(context))
    parts: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(context)
        parts.append((match.group(1), context[match.end() : end]))
    return parts


def _part_sources_and_pages(body: str) -> list[tuple[str, int]]:
    """The ``(source_file, page)`` pairs of the per-chunk lines in one part."""
    return [(source, int(page)) for source, page in _CHUNK_SOURCE_RE.findall(body)]


def _forbid_legacy_derivation(
    pipeline: RAGPipeline, monkeypatch: pytest.MonkeyPatch
) -> None:
    def derive(chunks: list[dict[str, Any]]) -> Any:
        raise AssertionError("legacy chapter derivation ran")

    monkeypatch.setattr(pipeline, "_derive_chapter_numbers", derive)


class TestCollidingChapterPerSource:
    """Two sources carry chapter 15: per-source parts, never a silent pick."""

    def test_two_labeled_windows_no_chunk_count_pick(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        storage = _MultiSourceStorage(
            _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
            + _book_chunks(_VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER)
        )
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        _forbid_legacy_derivation(pipeline, monkeypatch)
        capture = _GenerationCapture()
        capture.attach(pipeline, monkeypatch)

        result = pipeline._iterative_query(
            "summarize chapter 15", top_k=8, show_sources=True
        )

        assert pipeline._structure_source == "tree"
        assert result["answer"] == _CANNED_ANSWER
        # One part per source, each attributed, in the store's sorted
        # candidate order — the vbox manual being "bigger" changed nothing.
        parts = _split_parts(capture.contexts[0])
        assert [source for source, _body in parts] == [_PVE, _VBOX]
        pve_body = dict(parts)[_PVE]
        vbox_body = dict(parts)[_VBOX]
        # Window purity: each part's chunk lines name only their own source.
        assert {src for src, _pg in _part_sources_and_pages(pve_body)} == {_PVE}
        assert {src for src, _pg in _part_sources_and_pages(vbox_body)} == {_VBOX}
        # And each part carries only its own book's chapter 15 material.
        assert "virtualbox" not in pve_body
        assert "pve-admin-guide" not in vbox_body
        assert {pg for _src, pg in _part_sources_and_pages(pve_body)} == {
            21,
            22,
            23,
            24,
        }
        assert {pg for _src, pg in _part_sources_and_pages(vbox_body)} == {
            21,
            22,
            23,
            24,
        }
        # The prompt tells the model to attribute each part to its source.
        assert "separately labeled" in capture.prompts[0]
        assert _PVE in capture.prompts[0] and _VBOX in capture.prompts[0]
        # show_sources carries both parts' chunks.
        assert {c["source_file"] for c in result["sources"]} == {_PVE, _VBOX}

    def test_leaky_storage_cannot_mix_sources_into_a_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Both books use the same page numbers and the same node/chapter ids
        # for chapter 15, so a leaky store returns the OTHER manual's chunks
        # for this window's pages and structural ownership cannot tell them
        # apart — the assembly-level source filter (D3) is the only guard.
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        storage = _MultiSourceStorage(
            _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
            + _book_chunks(_VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER),
            honor_source=False,
        )
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        _forbid_legacy_derivation(pipeline, monkeypatch)
        capture = _GenerationCapture()
        capture.attach(pipeline, monkeypatch)

        result = pipeline._iterative_query(
            "summarize chapter 15", top_k=8, show_sources=True
        )

        assert pipeline._structure_source == "tree"
        parts = _split_parts(capture.contexts[0])
        assert [source for source, _body in parts] == [_PVE, _VBOX]
        for source, body in parts:
            chunk_sources = {src for src, _pg in _part_sources_and_pages(body)}
            assert chunk_sources == {source}
        # No cross-source text leaked into either part.
        pve_body = dict(parts)[_PVE]
        vbox_body = dict(parts)[_VBOX]
        assert "virtualbox" not in pve_body
        assert "pve-admin-guide" not in vbox_body
        # Both parts survived intact (the filter excluded, not emptied).
        assert {c["source_file"] for c in result["sources"]} == {_PVE, _VBOX}

    def test_dotted_section_collision_also_resolves_per_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        storage = _MultiSourceStorage(
            _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
            + _book_chunks(_VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER)
        )
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        _forbid_legacy_derivation(pipeline, monkeypatch)
        capture = _GenerationCapture()
        capture.attach(pipeline, monkeypatch)

        result = pipeline._iterative_query(
            "summarize section 15.2", top_k=8, show_sources=True
        )

        assert pipeline._structure_source == "tree"
        parts = _split_parts(capture.contexts[0])
        assert [source for source, _body in parts] == [_PVE, _VBOX]
        for source, body in parts:
            # Exact-section windows: only that section's own chunks.
            assert {src for src, _pg in _part_sources_and_pages(body)} == {source}
            assert {pg for _src, pg in _part_sources_and_pages(body)} == {22, 23}
        assert {c["source_file"] for c in result["sources"]} == {_PVE, _VBOX}


class TestUniqueNumberResolution:
    """A number carried by exactly one source resolves against that source."""

    def test_number_unique_to_one_source_resolves_against_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        provider = _CannedProvider()
        pipeline = _make_pipeline(
            _MultiSourceStorage(
                _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
                + _book_chunks(
                    _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER
                )
            ),
            provider,
            store,
        )
        _forbid_legacy_derivation(pipeline, monkeypatch)

        # Chapter 7 exists only in the pve guide; the vbox manual is much
        # larger, so the legacy chunk-count pick would have governed (and
        # failed).  Resolution proceeds against the unique carrier.
        result = pipeline._iterative_query(
            "summarize chapter 7", top_k=8, show_sources=True
        )

        assert pipeline._structure_source == "tree"
        assert {c["source_file"] for c in result["sources"]} == {_PVE}
        assert {c["page_number"] for c in result["sources"]} == {13, 14}
        # No vbox material reached any generation prompt (the chapter goes
        # through the map-reduce summarizer, so the provider is the surface).
        assert provider.prompts
        assert all("virtualbox" not in prompt for prompt in provider.prompts)

    @pytest.mark.parametrize(
        ("query", "expected_pages"),
        [
            ("summarize section 15.1", {21}),
            ("summarize chapter 1", {1, 2}),
        ],
    )
    def test_single_source_collection_stays_byte_identical(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        query: str,
        expected_pages: set[int],
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        run_a = _make_pipeline(
            _MultiSourceStorage(_book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)),
            _CannedProvider(),
            store,
        )
        run_b = _make_pipeline(
            _MultiSourceStorage(_book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)),
            _CannedProvider(),
            store,
        )
        # Run B disables the store lookup entirely — that is exactly the
        # pre-change flow (chunk-count pick -> tree query).  Run A takes the
        # new unique-carrier resolution.  For a single-source collection
        # both must produce byte-identical results.
        monkeypatch.setattr(run_b, "_tree_sources_with_number", lambda number: [])

        result_a = run_a._iterative_query(query, top_k=8, show_sources=True)
        result_b = run_b._iterative_query(query, top_k=8, show_sources=True)

        assert result_a == result_b
        assert _CANNED_ANSWER in result_a["answer"]
        assert run_a._structure_source == "tree"
        assert run_b._structure_source == "tree"
        assert {c["page_number"] for c in result_a["sources"]} == expected_pages


class TestSourceMentionScoping:
    """A resolved source mention scopes resolution to that source alone."""

    def test_mention_scopes_even_when_other_source_is_larger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        provider = _CannedProvider()
        pipeline = _make_pipeline(
            _MultiSourceStorage(
                _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
                + _book_chunks(
                    _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER
                )
            ),
            provider,
            store,
        )
        _forbid_legacy_derivation(pipeline, monkeypatch)

        # The orchestration layer resolves "the proxmox guide" to _PVE and
        # passes the filter in; resolution must scope to it even though the
        # vbox manual would win the chunk-count pick.
        result = pipeline._iterative_query(
            "in the proxmox guide, summarize chapter 15",
            top_k=8,
            show_sources=True,
            source_filter=_PVE,
        )

        assert pipeline._structure_source == "tree"
        assert _CANNED_ANSWER in result["answer"]
        assert provider.prompts
        # No vbox material reached any generation prompt, and every source
        # line in the result belongs to the mentioned guide.
        assert all("virtualbox" not in prompt for prompt in provider.prompts)
        assert {c["source_file"] for c in result["sources"]} == {_PVE}
        assert {c["page_number"] for c in result["sources"]} == {21, 22, 23, 24}


class TestUnchangedPaths:
    """Numbers no tree carries — and target-less queries — keep the legacy."""

    @staticmethod
    def _seeded(store: StructureStore) -> _MultiSourceStorage:
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        return _MultiSourceStorage(
            _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
            + _book_chunks(_VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER)
        )

    def test_number_in_no_tree_takes_the_legacy_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        pipeline = _make_pipeline(self._seeded(store), _CannedProvider(), store)
        calls: list[list[dict[str, Any]]] = []

        def derive(chunks: list[dict[str, Any]]) -> Any:
            calls.append(list(chunks))
            return [], set(), []

        monkeypatch.setattr(pipeline, "_derive_chapter_numbers", derive)
        result = pipeline._iterative_query(
            "summarize chapter 42", top_k=8, show_sources=False
        )

        # No tree carries 42: the chunk-count pick ran, the tree query
        # declined, and the legacy scan governed (no tree provenance).
        assert len(calls) == 1
        assert pipeline._structure_source is None
        assert result["query"] == "summarize chapter 42"

    def test_unresolvable_collision_falls_back_to_legacy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # vbox's chapter 15 carries no page range (a degenerate capture), so
        # only one window resolves — the multi-part answer is refused and
        # the flow continues exactly as before per-source resolution: the
        # chunk-count pick selects the larger vbox manual and the tree
        # query governs it.
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(
            store,
            _VBOX,
            _VBOX_CHAPTERS,
            _VBOX_SECTIONS,
            titles=_VBOX_TITLES,
            drop_page_range_for={15},
        )
        pipeline = _make_pipeline(
            _MultiSourceStorage(
                _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
                + _book_chunks(
                    _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER
                )
            ),
            _CannedProvider(),
            store,
        )
        picked: list[str] = []

        def tree_query(query: str, src: str, **kwargs: Any) -> dict[str, Any]:
            picked.append(src)
            return {"answer": "single-pick tree answer", "query": query}

        monkeypatch.setattr(pipeline, "_tree_chapter_query", tree_query)
        result = pipeline._iterative_query(
            "summarize chapter 15", top_k=8, show_sources=False
        )

        # The multi-part answer was refused (one window), so the unchanged
        # chunk-count pick ran and governed via the tree query.
        assert picked == [_VBOX]
        assert result["answer"] == "single-pick tree answer"

    def test_targetless_overview_keeps_chunk_count_pick(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        pipeline = _make_pipeline(self._seeded(store), _CannedProvider(), store)
        picked: list[str] = []

        def tree_query(query: str, src: str, **kwargs: Any) -> dict[str, Any]:
            picked.append(src)
            return {"answer": "tree-governed overview", "query": query}

        number_lookups: list[str] = []

        def lookup(number: str) -> list[str]:
            number_lookups.append(number)
            return []

        monkeypatch.setattr(pipeline, "_tree_chapter_query", tree_query)
        monkeypatch.setattr(pipeline, "_tree_sources_with_number", lookup)
        result = pipeline._iterative_query(
            "give me an overview of the book", top_k=8, show_sources=False
        )

        # No numbered target: no store lookup, and the chunk-count pick
        # still selects the larger vbox manual for the whole-document query.
        assert number_lookups == []
        assert picked == [_VBOX]
        assert result["answer"] == "tree-governed overview"


class TestTreeNumberWindow:
    """The per-source window builder's direct contract."""

    @staticmethod
    def _pipeline(
        tmp_path: Path, storage: _MultiSourceStorage
    ) -> tuple[RAGPipeline, StructureStore]:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _PVE, _PVE_CHAPTERS, _PVE_SECTIONS, titles=_PVE_TITLES)
        _save_tree(store, _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, titles=_VBOX_TITLES)
        return _make_pipeline(storage, _NullProvider(), store), store

    def test_chapter_window_carries_node_title_and_own_source(
        self, tmp_path: Path
    ) -> None:
        pipeline, _store = self._pipeline(
            tmp_path,
            _MultiSourceStorage(
                _book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)
                + _book_chunks(
                    _VBOX, _VBOX_CHAPTERS, _VBOX_SECTIONS, filler=_VBOX_FILLER
                )
            ),
        )
        window = pipeline._tree_number_window(
            _PVE, enum_target="15", raw_section_target=None
        )
        assert window is not None
        chunks, title = window
        assert title == "High Availability"
        assert {c["source_file"] for c in chunks} == {_PVE}
        assert {c["page_number"] for c in chunks} == {21, 22, 23, 24}
        # Page-interleaved, document order inside each page.
        assert [c["page_number"] for c in chunks] == [21, 22, 23, 24]

    def test_section_window_scopes_to_the_exact_node(self, tmp_path: Path) -> None:
        pipeline, _store = self._pipeline(
            tmp_path,
            _MultiSourceStorage(_book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)),
        )
        window = pipeline._tree_number_window(
            _PVE, enum_target="15", raw_section_target="15.2"
        )
        assert window is not None
        chunks, title = window
        assert title == "Section 15.2"
        assert {c["source_file"] for c in chunks} == {_PVE}
        assert {c["node_id"] for c in chunks} == {"sec-15.2"}
        assert {c["page_number"] for c in chunks} == {22, 23}

    def test_other_sources_number_and_missing_numbers_return_none(
        self, tmp_path: Path
    ) -> None:
        pipeline, _store = self._pipeline(
            tmp_path,
            _MultiSourceStorage(_book_chunks(_PVE, _PVE_CHAPTERS, _PVE_SECTIONS)),
        )
        # vbox's tree resolves its own chapter 15 (its title, not pve's).
        window = pipeline._tree_number_window(
            _VBOX, enum_target="15", raw_section_target=None
        )
        assert window is not None
        assert window[1] == "VBoxManage"
        # A number the tree does not carry, and a treeless document, drop
        # the source from the candidate parts.
        assert (
            pipeline._tree_number_window(
                _PVE, enum_target="42", raw_section_target=None
            )
            is None
        )
        assert (
            pipeline._tree_number_window(
                "/docs/never-ingested.pdf",
                enum_target="15",
                raw_section_target=None,
            )
            is None
        )
        # No concrete number: per-source resolution is not defined.
        assert (
            pipeline._tree_number_window(
                _PVE, enum_target=None, raw_section_target=None
            )
            is None
        )
