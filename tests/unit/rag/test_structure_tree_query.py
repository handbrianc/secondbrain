"""Structure-tree query-path tests (add-structure-aware-ingestion, tasks 12-15).

Four groups:

1. Tree-governed enumeration: a synthetic HCD-shaped tree (21 chapters,
   same-page openers for chapters 10/13/15, one 2-page chapter-6 /
   section-5.2 overlap) enumerates every chapter with node-true ranges,
   no placeholder notes, and a chapter-6 bucket that excludes section-5.2's
   solo page and non-body roles.
2. Treeless fallback characterization: the exported chapter-map fixtures
   (``tests/fixtures/chapter_map/`` + ``baselines.json``) keep their legacy
   ranges and multi-chapter buckets byte-identically, with ``None`` tree
   provenance — the no-regression net for task 14.
3. Degraded-store fallbacks: store construction failure, ``load_tree``
   raising, and a tree with zero structural nodes all proceed down the
   unchanged legacy path.
4. Tree beats anthology: a treeful document takes the tree path without
   the anthology detector ever running.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any, cast

import pytest

from secondbrain.document.structure_annotate import annotate_chunks
from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.storage.structure_sqlite import (
    DocumentStructure,
    StructureNode,
    StructureStore,
)
from tests.unit.rag._chapter_fixture_storage import (
    ChapterFixtureStorage,
    load_fixture,
)

_BOOKS = ("user-manual", "pve-admin-guide", "hcd-report")

_CANNED_ANSWER = (
    "The document develops its subject chapter by chapter, pairing concrete "
    "guidance with worked examples so each part builds on the previous one."
)

_PLACEHOLDER_NOTE = "No document content was retrieved"

_SYNTH = "/data/workspace/uploads/hcd-shape-synthetic.pdf"

# The synthetic HCD shape: 21 chapters over pages 1-29.  Chapters 10, 13 and
# 15 open on the same page their predecessor ends (the same-page-opener shape
# that starved legacy pinning); chapter 6 opens on page 11, the last page of
# section 5.2 (the 2-page ch6/section-5 overlap shape behind the legacy
# ``('6', (5, 5))`` defect).
_CHAPTER_PLAN: dict[int, tuple[int, int]] = {
    1: (1, 2),
    2: (3, 4),
    3: (5, 6),
    4: (7, 8),
    5: (9, 11),
    6: (11, 12),
    7: (13, 13),
    8: (14, 15),
    9: (16, 17),
    10: (17, 18),
    11: (19, 19),
    12: (20, 20),
    13: (20, 21),
    14: (22, 22),
    15: (22, 23),
    16: (24, 24),
    17: (25, 25),
    18: (26, 26),
    19: (27, 27),
    20: (28, 28),
    21: (29, 29),
}

_SECTIONS: dict[str, tuple[int, int]] = {
    "5.1": (9, 9),
    "5.2": (10, 11),
    "6.1": (11, 12),
}


class _TreeSearcher:
    """Searcher double carrying the fixture storage."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    """LLM double returning one fixed, plausible, non-empty sentence."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return _CANNED_ANSWER


class _NullProvider:
    """LLM double returning "" — mirrors the baseline-capture stub."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 512
    ) -> str:
        return ""


class _LogCapture(logging.Handler):
    """Capture pipeline log lines, parsing the chapter-ranges debug line."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []
        self.ranges: dict[int, tuple[int, int]] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        self.messages.append(message)
        if message.startswith("Chapter page ranges for"):
            raw = message.split(": ", 1)[1]
            self.ranges = {int(k): v for k, v in ast.literal_eval(raw).items()}


class _TreeStorage(ChapterFixtureStorage):  # type: ignore[misc]
    """Fixture double extended with the page-list ``find_chunks`` API.

    Mirrors the live ``find_chunks`` semantics the tree path relies on:
    equality on ``source_file``, an exact MatchAny page-number list, and NO
    role filter (role filtering is the tree path's own client-side job, so
    the double must not pre-apply it).
    """

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
            if source_file and chunk.get("source_file") != source_file:
                continue
            if pages is not None and (chunk.get("page_number") or 0) not in pages:
                continue
            out.append(dict(chunk))
        return out


def _synthetic_chunks(source_file: str) -> list[dict[str, Any]]:
    """Body chunks covering every planned page, plus role noise in ch6.

    Every planned chapter page carries two body chunks whose text mentions
    the chapter, so the legacy probe/roster stay non-empty and the flow
    reaches the tree seam.  Page 11 additionally carries the section-5.2
    tail (the shared opener page); page 10 is section 5.2's solo page; page
    12 carries caption/navigation noise that only a role filter may drop.
    """
    chunks: list[dict[str, Any]] = []
    pos_by_page: dict[int, int] = {}

    def add(
        page: int,
        text: str,
        role: str = "body",
        element: str = "paragraph",
        owner: int | None = None,
    ) -> None:
        pos = pos_by_page.get(page, 0)
        pos_by_page[page] = pos + 1
        chunks.append(
            {
                "chunk_id": f"{source_file}#p{page}c{pos}",
                "source_file": source_file,
                "page_number": page,
                "page_pos": pos,
                "chunk_text": text,
                "element_type": element,
                "chunk_role": role,
            }
        )
        if owner is not None:
            chunks[-1].update(chapter_id=str(owner), node_id=f"ch-{owner}")

    for ch, (start, end) in _CHAPTER_PLAN.items():
        for page in range(start, end + 1):
            # Opener-style text: the legacy roster regex needs "Chapter N"
            # followed by a capitalized title run to produce a roster entry,
            # which is what keeps the flow reaching the tree seam.
            add(page, f"Chapter {ch} Topic {ch} Overview", owner=ch)
            add(
                page,
                f"Chapter {ch} continues with detail {ch} on page {page}.",
                owner=ch,
            )
    # Section 5.2's closing text on the shared page 11 (chapter 6's opener).
    add(11, "Section 5.2 closing guidance carried over from chapter 5.", owner=5)
    chunks[-1].update(node_id="sec-5.2", section_id="5.2")
    # Non-body noise inside chapter 6's range.
    add(12, "Figure 6-A: retention windows.", role="caption", element="caption")
    add(12, "Back to table of contents", role="navigation", element="navigation")
    return chunks


def _save_tree(
    store: StructureStore,
    source_file: str,
    *,
    chapter_ranges: dict[int, tuple[int, int]] | None = None,
    sections: dict[str, tuple[int, int]] | None = None,
    drop_page_range_for: set[int] | set[str] | None = None,
    nodes_override: list[StructureNode] | None = None,
) -> None:
    """Persist a synthetic capture tree (or an explicit node list) for tests."""
    if nodes_override is not None:
        store.save_structure(
            DocumentStructure(
                source_file=source_file,
                nodes=nodes_override,
                page_labels=[],
                audio_segments=[],
                sources={source_file: True},
                captured_at="2026-10-24T00:00:00+00:00",
            )
        )
        return
    drop = {int(k) for k in (drop_page_range_for or set())}
    planned = chapter_ranges if chapter_ranges is not None else _CHAPTER_PLAN
    section_plan = sections if sections is not None else _SECTIONS
    nodes: list[StructureNode] = []
    for ch, (start, end) in planned.items():
        page_start: int | None = start
        page_end: int | None = end
        if ch in drop:
            page_start = None
            page_end = None
        chapter_id = f"ch-{ch}"
        nodes.append(
            StructureNode(
                node_id=chapter_id,
                parent_id=None,
                kind="chapter",
                level=1,
                number=str(ch),
                title=f"Title {ch}",
                page_start=page_start,
                page_end=page_end,
                t_start=None,
                t_end=None,
                heading_path=f"Chapter {ch}",
            )
        )
        for sec, (sec_start, sec_end) in section_plan.items():
            if not sec.startswith(f"{ch}."):
                continue
            nodes.append(
                StructureNode(
                    node_id=f"sec-{sec}",
                    parent_id=chapter_id,
                    kind="section",
                    level=2,
                    number=sec,
                    title=f"Section {sec}",
                    page_start=sec_start,
                    page_end=sec_end,
                    t_start=None,
                    t_end=None,
                    heading_path=f"Chapter {ch} / Section {sec}",
                )
            )
    _save_tree(
        store,
        source_file,
        nodes_override=nodes,
    )


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


def _run_iterative(
    pipeline: RAGPipeline,
    query: str,
    source: str,
    *,
    show_sources: bool = False,
) -> dict[str, Any]:
    return pipeline._iterative_query(
        query,
        top_k=8,
        show_sources=show_sources,
        source_filter=source,
    )


def _capture_logs(pipeline: RAGPipeline) -> _LogCapture:
    capture = _LogCapture()
    for name in (
        "secondbrain.rag.pipeline._pipeline",
        "secondbrain.rag.pipeline._structure_mixin",
    ):
        log = logging.getLogger(name)
        log.addHandler(capture)
        log.setLevel(logging.DEBUG)
    return capture


def _release_logs(capture: _LogCapture) -> None:
    for name in (
        "secondbrain.rag.pipeline._pipeline",
        "secondbrain.rag.pipeline._structure_mixin",
    ):
        log = logging.getLogger(name)
        log.removeHandler(capture)
        log.setLevel(logging.NOTSET)


def _record_buckets(
    pipeline: RAGPipeline, monkeypatch: pytest.MonkeyPatch
) -> dict[str, list[int]]:
    """Capture bucket page lists at the summarizer boundary (baseline recipe)."""
    recorded: dict[str, list[int]] = {}

    def _recorder(
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        for ch, bucket in chapter_buckets.items():
            recorded[str(ch)] = [c.get("page_number") or 0 for c in bucket]
        return _CANNED_ANSWER

    monkeypatch.setattr(pipeline, "_generate_multi_chapter_summary", _recorder)
    return recorded


def _expected_bucket_pages(
    chunks: list[dict[str, Any]],
) -> dict[int, list[int]]:
    """Page lists the synthetic buckets must contain (body pages in range)."""
    expected: dict[int, list[int]] = {}
    for ch, (start, end) in _CHAPTER_PLAN.items():
        expected[ch] = sorted(
            chunk["page_number"]
            for chunk in chunks
            if chunk.get("chunk_role") == "body"
            and chunk.get("chapter_id") == str(ch)
            and start <= chunk["page_number"] <= end
        )
    return expected


def _fixture_source(name: str) -> str:
    return str(load_fixture(name)[0]["source_file"])


def _baseline_entry(name: str) -> dict[str, Any]:
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "chapter_map"
    with (fixture_dir / "baselines.json").open(encoding="utf-8") as fh:
        data = cast(dict[str, Any], json.loads(fh.read()))
    return cast(dict[str, Any], data[name])


class TestTreeGovernedEnumeration:
    """A stored HCD-shaped tree governs the whole chapter map (task 15a)."""

    def test_tree_enumerates_every_chapter_with_node_ranges(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, source)
        storage = _TreeStorage(_synthetic_chunks(source))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        recorded = _record_buckets(pipeline, monkeypatch)
        capture = _capture_logs(pipeline)
        try:
            result = _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            _release_logs(capture)

        # Provenance: attribute, info log, and the tree-true ranges line.
        assert pipeline._structure_source == "tree"
        assert any(
            "Structure tree governs chapter enumeration" in m for m in capture.messages
        )
        assert capture.ranges is not None
        assert capture.ranges == _CHAPTER_PLAN

        # Every chapter enumerated exactly once, with node-true bucket pages.
        assert sorted(int(k) for k in recorded) == list(range(1, 22))
        assert {int(k): v for k, v in recorded.items()} == _expected_bucket_pages(
            _synthetic_chunks(source)
        )

        # The canned multi summary means no placeholder fired.
        assert result["answer"] == _CANNED_ANSWER

    def test_ch6_bucket_excludes_section5_pages_and_nonbody_roles(
        self, tmp_path: Any
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, source)
        storage = _TreeStorage(_synthetic_chunks(source))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)

        tree = store.load_tree(source)
        assert tree is not None
        buckets = pipeline._tree_chapter_buckets(
            storage, source, _CHAPTER_PLAN, nodes=tree.nodes
        )
        assert buckets is not None

        ch6 = buckets[6]
        ch6_pages = {c.get("page_number") for c in ch6}
        # Page 10 is section 5.2's solo page; page 11 is the shared opener
        # page and legitimately part of chapter 6's node range.
        assert ch6_pages == {11, 12}
        assert 10 not in ch6_pages
        # Role noise dropped: everything in the bucket is body text.
        assert all(c.get("chunk_role") == "body" for c in ch6)
        assert not any("Figure 6-A" in c.get("chunk_text", "") for c in ch6)
        assert not any("table of contents" in c.get("chunk_text", "") for c in ch6)
        assert not any("Section 5.2 closing" in c["chunk_text"] for c in ch6)
        # The 2-page overlap shape: section 5.2 spans pages 10-11 while
        # chapter 6 spans 11-12; chapter 5's bucket still owns page 10.
        ch5_pages = {c.get("page_number") for c in buckets[5]}
        assert 10 in ch5_pages
        # Same-page-opener chapters keep their full node ranges.
        assert {c.get("page_number") for c in buckets[10]} == {17, 18}
        assert {c.get("page_number") for c in buckets[13]} == {20, 21}
        assert {c.get("page_number") for c in buckets[15]} == {22, 23}

    def test_empty_range_chapter_gets_the_placeholder_note(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        small_plan = {1: (1, 1), 2: (2, 2), 3: (3, 3)}
        _save_tree(
            store,
            source,
            chapter_ranges=small_plan,
            sections={},
            drop_page_range_for={2},
        )
        chunks: list[dict[str, Any]] = []
        for page in (1, 2, 3):
            chunks.append(
                {
                    "chunk_id": f"{source}#p{page}c0",
                    "source_file": source,
                    "page_number": page,
                    "page_pos": 0,
                    "chunk_text": f"Chapter {page} Topic {page} Overview",
                    "element_type": "paragraph",
                    "chunk_role": "body",
                }
            )
        pipeline = _make_pipeline(_TreeStorage(chunks), _CannedProvider(), store)
        result = _run_iterative(pipeline, f"summarize {Path(source).name}", source)

        answer = str(result["answer"])
        # Chapter 2's node carries no page range: sentinel range, empty
        # bucket, and the existing placeholder note speaks for it.
        assert _PLACEHOLDER_NOTE in answer
        assert "Chapter 2" in answer
        assert pipeline._structure_source == "tree"

    def test_targeted_chapter_query_uses_the_tree_single_path(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, source)
        storage = _TreeStorage(_synthetic_chunks(source))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)

        seen: dict[str, Any] = {}

        def _single_recorder(
            chunks: list[dict[str, Any]],
            chapter_num: int | str,
            chapter_title: str,
            *,
            foreign_titles: list[str] | None = None,
        ) -> str:
            seen["num"] = chapter_num
            seen["title"] = chapter_title
            seen["pages"] = [c.get("page_number") for c in chunks]
            seen["foreign"] = list(foreign_titles or [])
            return _CANNED_ANSWER

        monkeypatch.setattr(
            pipeline, "_generate_single_chapter_summary", _single_recorder
        )
        result = _run_iterative(
            pipeline, "summarize chapter 6", source, show_sources=True
        )

        assert seen["num"] == "6"
        assert seen["title"] == "Title 6"
        assert set(seen["pages"]) == {11, 12}
        assert len(seen["foreign"]) == 20
        assert "Title 6" not in seen["foreign"]
        sources = result.get("sources", [])
        assert {c.get("page_number") for c in sources} == {11, 12}
        assert pipeline._structure_source == "tree"

    @pytest.mark.parametrize("probe_result", [[], [{"source_file": _SYNTH}]])
    def test_scoped_tree_does_not_require_legacy_structure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        probe_result: list[dict[str, Any]],
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH, chapter_ranges={1: (1, 1)}, sections={})
        pipeline = _make_pipeline(
            _TreeStorage(_synthetic_chunks(_SYNTH)), _CannedProvider(), store
        )
        calls: list[str] = []

        def probe(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append("probe")
            return probe_result

        def derive(chunks: list[dict[str, Any]]) -> Any:
            calls.append("derive")
            raise AssertionError("legacy chapter derivation ran")

        monkeypatch.setattr(pipeline, "_probe_document_structure", probe)
        monkeypatch.setattr(pipeline, "_derive_chapter_numbers", derive)
        result = _run_iterative(pipeline, "summarize this document", _SYNTH)
        assert result["answer"]
        assert calls == []
        assert pipeline._structure_source == "tree"

    def test_unscoped_tree_precedes_legacy_roster(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH, chapter_ranges={1: (1, 1)}, sections={})
        pipeline = _make_pipeline(
            _TreeStorage(_synthetic_chunks(_SYNTH)), _CannedProvider(), store
        )
        monkeypatch.setattr(
            pipeline,
            "_probe_document_structure",
            lambda **kwargs: [{"source_file": _SYNTH}],
        )

        def derive(chunks: list[dict[str, Any]]) -> Any:
            raise AssertionError("legacy chapter derivation ran")

        monkeypatch.setattr(pipeline, "_derive_chapter_numbers", derive)
        result = pipeline._iterative_query(
            "summarize this document", top_k=8, show_sources=False
        )
        assert result["answer"]
        assert pipeline._structure_source == "tree"

    @pytest.mark.parametrize(
        "query",
        ["summarize section 5.2", "list sections in section 5.2"],
    )
    def test_dotted_target_retrieves_only_exact_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH)
        chunks = _synthetic_chunks(_SYNTH)
        # Page 11 is shared by section 5.2 and chapter 6. Node ownership
        # excludes the neighbor even though both physically occupy that page.
        for chunk in chunks:
            page = chunk["page_number"]
            if page in (10, 11):
                if "Chapter 6" in chunk["chunk_text"]:
                    chunk.update(node_id="sec-6.1", chapter_id="6", section_id="6.1")
                else:
                    chunk.update(node_id="sec-5.2", chapter_id="5", section_id="5.2")
        pipeline = _make_pipeline(_TreeStorage(chunks), _CannedProvider(), store)
        prompts: list[str] = []

        def generate(prompt: str) -> str:
            prompts.append(prompt)
            return _CANNED_ANSWER

        monkeypatch.setattr(pipeline, "_generate", generate)
        result = _run_iterative(pipeline, query, _SYNTH, show_sources=True)
        assert pipeline._structure_source == "tree"
        assert {c["page_number"] for c in result["sources"]} == {10, 11}
        assert all(c["node_id"] == "sec-5.2" for c in result["sources"])
        assert prompts
        assert "Section 5.2 — Section 5.2" in prompts[0]
        assert "Chapter 6" not in prompts[0]

    @pytest.mark.parametrize("ownership", ["node_id", "chapter_id"])
    def test_shared_page_ownership_filters_neighboring_chapter(
        self, tmp_path: Path, ownership: str
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH)
        tree = store.load_tree(_SYNTH)
        assert tree is not None
        chunks = _synthetic_chunks(_SYNTH)
        for chunk in chunks:
            if chunk["page_number"] == 11:
                chunk.pop("node_id", None)
                chunk.pop("chapter_id", None)
                owner = "6" if "Chapter 6" in chunk["chunk_text"] else "5"
                chunk[ownership] = f"sec-{owner}.{'1' if owner == '6' else '2'}"
                if ownership == "chapter_id":
                    chunk[ownership] = owner
        storage = _TreeStorage(chunks)
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        buckets = pipeline._tree_chapter_buckets(
            storage, _SYNTH, _CHAPTER_PLAN, nodes=tree.nodes
        )
        assert buckets is not None
        assert any(c["page_number"] == 11 for c in buckets[5])
        assert any(c["page_number"] == 11 for c in buckets[6])
        assert not any("Chapter 6" in c["chunk_text"] for c in buckets[5])
        assert not any("Section 5.2 closing" in c["chunk_text"] for c in buckets[6])
        assert any(c["page_number"] == 12 for c in buckets[6])

    def test_exact_section_does_not_require_numbered_chapter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(
            store,
            _SYNTH,
            nodes_override=[
                StructureNode(
                    node_id="unnumbered-chapter",
                    kind="chapter",
                    level=1,
                    title="Unnumbered chapter",
                    page_start=1,
                    page_end=4,
                ),
                StructureNode(
                    node_id="sec-5.2",
                    parent_id="unnumbered-chapter",
                    kind="section",
                    level=2,
                    number="5.2",
                    title="Exact target",
                    page_start=2,
                    page_end=3,
                ),
            ],
        )
        storage = _TreeStorage(
            [
                {
                    "source_file": _SYNTH,
                    "page_number": page,
                    "chunk_role": "body",
                    "chunk_text": f"Detailed material from page {page}.",
                }
                for page in range(1, 5)
            ]
        )
        pipeline = _make_pipeline(storage, _CannedProvider(), store)

        def must_not_derive(chunks: list[StructureNode]) -> Any:
            raise AssertionError("exact section lookup required a chapter map")

        monkeypatch.setattr(pipeline, "_tree_chapter_map", must_not_derive)
        result = _run_iterative(
            pipeline, "summarize section 5.2", _SYNTH, show_sources=True
        )
        assert pipeline._structure_source == "tree"
        assert {chunk["page_number"] for chunk in result["sources"]} == {2, 3}
        assert result["answer"] == _CANNED_ANSWER

    @pytest.mark.parametrize("ownership", ["node_id", "section_id"])
    def test_section_ownership_includes_descendants_not_siblings(
        self, tmp_path: Path, ownership: str
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(
            store,
            _SYNTH,
            chapter_ranges={5: (1, 3)},
            sections={"5.2": (2, 2), "5.20": (2, 2)},
        )
        tree = store.load_tree(_SYNTH)
        assert tree is not None
        tree.nodes.append(
            StructureNode(
                node_id="sub-5.2.1",
                parent_id="sec-5.2",
                kind="subsection",
                level=3,
                number="5.2.1",
                title="Nested detail",
                page_start=2,
                page_end=2,
            )
        )
        chunks = [
            {
                "source_file": _SYNTH,
                "page_number": 2,
                "chunk_role": "body",
                "chunk_text": section,
                ownership: node_id if ownership == "node_id" else section,
            }
            for section, node_id in (
                ("5.2", "sec-5.2"),
                ("5.2.1", "sub-5.2.1"),
                ("5.20", "sec-5.20"),
            )
        ]
        storage = _TreeStorage(chunks)
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        buckets = pipeline._tree_chapter_buckets(
            storage, _SYNTH, {5: (2, 2)}, nodes=tree.nodes, section_target="5.2"
        )
        assert buckets is not None
        assert [c["chunk_text"] for c in buckets[5]] == ["5.2", "5.2.1"]

    @pytest.mark.parametrize(
        "query",
        ["summarize chapter 6", "summarize section 5.2"],
    )
    def test_unannotated_shared_pages_fall_back_instead_of_claiming_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query: str
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH)
        chunks = _synthetic_chunks(_SYNTH)
        for chunk in chunks:
            if chunk["page_number"] == 11:
                for key in ("node_id", "chapter_id", "section_id"):
                    chunk.pop(key, None)
        pipeline = _make_pipeline(_TreeStorage(chunks), _CannedProvider(), store)
        calls: list[str] = []

        def probe(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append("legacy")
            return []

        monkeypatch.setattr(pipeline, "_probe_document_structure", probe)
        _run_iterative(pipeline, query, _SYNTH)
        assert calls == ["legacy"]
        assert pipeline._structure_source is None

    def test_chapter_annotation_alone_cannot_disambiguate_sibling_sections(
        self, tmp_path: Path
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(
            store,
            _SYNTH,
            chapter_ranges={5: (1, 3)},
            sections={"5.2": (2, 2), "5.3": (2, 2)},
        )
        tree = store.load_tree(_SYNTH)
        assert tree is not None
        storage = _TreeStorage(
            [
                {
                    "source_file": _SYNTH,
                    "page_number": 2,
                    "chunk_role": "body",
                    "chunk_text": "Unknown section within chapter five.",
                    "chapter_id": "5",
                }
            ]
        )
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        assert (
            pipeline._tree_chapter_buckets(
                storage, _SYNTH, {5: (2, 2)}, nodes=tree.nodes, section_target="5.2"
            )
            is None
        )

    def test_real_annotation_does_not_move_chapter5_closing_text_into_chapter6(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH)
        tree = store.load_tree(_SYNTH)
        assert tree is not None
        raw_chunks = _synthetic_chunks(_SYNTH)
        for chunk in raw_chunks:
            for key in ("node_id", "chapter_id", "section_id"):
                chunk.pop(key, None)
            chunk["page"] = chunk["page_number"]
            chunk["text"] = chunk["chunk_text"]
        chunks = [dict(chunk) for chunk in annotate_chunks(raw_chunks, tree)]
        closing = next(
            chunk for chunk in chunks if "Section 5.2 closing" in chunk["chunk_text"]
        )
        assert closing.get("chapter_id") != "6"
        assert closing.get("node_id") != "sec-6.1"
        storage = _TreeStorage(chunks)
        pipeline = _make_pipeline(storage, _CannedProvider(), store)
        buckets = pipeline._tree_chapter_buckets(
            storage, _SYNTH, _CHAPTER_PLAN, nodes=tree.nodes
        )
        # Page ranges cannot establish which side of a same-page heading
        # unanchored prose belongs to. Refuse a tree answer rather than
        # treating inherited ownership as a reliable within-page boundary.
        assert buckets is None
        monkeypatch.setattr(pipeline, "_probe_document_structure", lambda **kwargs: [])
        _run_iterative(pipeline, "summarize chapter 6", _SYNTH)
        assert pipeline._structure_source is None


class TestTreeChapterMap:
    def test_only_root_integer_sections_are_promoted(self) -> None:
        nodes = [
            StructureNode(
                node_id="root",
                kind="section",
                number="1",
                title="Root",
                level=1,
                page_start=1,
                page_end=5,
            ),
            StructureNode(
                node_id="nested",
                parent_id="root",
                kind="section",
                number="2",
                title="Nested integer",
                level=2,
                page_start=2,
                page_end=3,
            ),
            StructureNode(
                node_id="dotted",
                kind="section",
                number="3.1",
                title="Dotted root",
                level=1,
                page_start=4,
                page_end=5,
            ),
            StructureNode(
                node_id="under-part",
                parent_id="part",
                kind="section",
                number="4",
                title="Section inside a part",
                level=2,
                page_start=6,
                page_end=7,
            ),
        ]
        assert RAGPipeline._tree_chapter_map(nodes) == ({1: (1, 5)}, {1: "Root"})

    def test_duplicate_anthology_chapters_trigger_legacy_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        nodes = [
            StructureNode(
                node_id=f"part-{part}-ch-1",
                parent_id=f"part-{part}",
                kind="chapter",
                number="1",
                title=f"Part {part} opening",
                level=2,
                page_start=page,
                page_end=page + 2,
            )
            for part, page in ((1, 1), (2, 10))
        ]
        assert RAGPipeline._tree_chapter_map(nodes) == ({}, {})
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, _SYNTH, nodes_override=nodes)
        pipeline = _make_pipeline(
            _TreeStorage(_synthetic_chunks(_SYNTH)), _CannedProvider(), store
        )
        calls: list[str] = []

        def probe(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append("legacy")
            return []

        monkeypatch.setattr(pipeline, "_probe_document_structure", probe)
        _run_iterative(pipeline, "summarize this document", _SYNTH)
        assert calls == ["legacy"]
        assert pipeline._structure_source is None


class TestTreelessFallbackCharacterization:
    """Treeless documents keep the legacy baselines byte-identically (15b)."""

    @pytest.mark.parametrize("fixture_name", _BOOKS)
    def test_treeless_documents_match_baselines(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fixture_name: str,
    ) -> None:
        source = _fixture_source(fixture_name)
        storage = ChapterFixtureStorage.from_fixture(fixture_name)
        # No store injected: the (conftest-isolated) real store is consulted,
        # finds no tree, and the legacy path must proceed unchanged.
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_buckets(pipeline, monkeypatch)
        capture = _capture_logs(pipeline)
        try:
            _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            _release_logs(capture)

        baselines = _baseline_entry(fixture_name)
        expected_ranges = {int(k): tuple(v) for k, v in baselines["ranges"].items()}
        assert capture.ranges is not None, (
            "the legacy 'Chapter page ranges' debug line must be logged"
        )
        assert capture.ranges == expected_ranges, (
            f"{fixture_name}: legacy chapter ranges diverged from baseline"
        )
        assert recorded == baselines["multi"]["bucket_pages"], (
            f"{fixture_name}: legacy bucket page lists diverged from baseline"
        )
        # No tree provenance was ever set.
        assert pipeline._structure_source is None


class TestDegradedStoreFallbacks:
    """Store failures and empty trees never hijack the legacy path (15c)."""

    def test_store_load_error_falls_back_to_legacy(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _fixture_source("hcd-report")
        storage = ChapterFixtureStorage.from_fixture("hcd-report")
        store = StructureStore(db_path=str(tmp_path / "structures.db"))

        def _boom(source_file: str) -> DocumentStructure:
            raise RuntimeError("sqlite exploded")

        monkeypatch.setattr(store, "load_tree", _boom)
        pipeline = _make_pipeline(storage, _NullProvider(), store)
        recorded = _record_buckets(pipeline, monkeypatch)
        capture = _capture_logs(pipeline)
        try:
            _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            _release_logs(capture)

        baselines = _baseline_entry("hcd-report")
        expected_ranges = {int(k): tuple(v) for k, v in baselines["ranges"].items()}
        assert capture.ranges == expected_ranges
        assert recorded == baselines["multi"]["bucket_pages"]
        assert pipeline._structure_source is None
        assert any("Structure tree lookup failed" in m for m in capture.messages)

    def test_tree_with_zero_structural_nodes_falls_back_to_legacy(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _fixture_source("hcd-report")
        storage = ChapterFixtureStorage.from_fixture("hcd-report")
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(
            store,
            source,
            nodes_override=[
                StructureNode(
                    node_id="part-1",
                    parent_id=None,
                    kind="part",
                    level=1,
                    number=None,
                    title="Part I",
                    page_start=1,
                    page_end=25,
                    t_start=None,
                    t_end=None,
                    heading_path="Part I",
                )
            ],
        )
        pipeline = _make_pipeline(storage, _NullProvider(), store)
        recorded = _record_buckets(pipeline, monkeypatch)
        capture = _capture_logs(pipeline)
        try:
            _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            _release_logs(capture)

        baselines = _baseline_entry("hcd-report")
        expected_ranges = {int(k): tuple(v) for k, v in baselines["ranges"].items()}
        assert capture.ranges == expected_ranges
        assert recorded == baselines["multi"]["bucket_pages"]
        assert pipeline._structure_source is None
        assert any("no chapter/section nodes" in m for m in capture.messages)

    def test_broken_store_construction_falls_back_to_legacy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _fixture_source("hcd-report")
        storage = ChapterFixtureStorage.from_fixture("hcd-report")

        class _BrokenStore:
            def __init__(self) -> None:
                raise RuntimeError("no sqlite here")

        monkeypatch.setattr(
            "secondbrain.rag.pipeline._structure_mixin.StructureStore",
            _BrokenStore,
        )
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_buckets(pipeline, monkeypatch)
        capture = _capture_logs(pipeline)
        try:
            _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            _release_logs(capture)

        baselines = _baseline_entry("hcd-report")
        expected_ranges = {int(k): tuple(v) for k, v in baselines["ranges"].items()}
        assert capture.ranges == expected_ranges
        assert recorded == baselines["multi"]["bucket_pages"]
        assert pipeline._structure_source is None
        assert any("Structure store unavailable" in m for m in capture.messages)


class TestTreeWinsOverAnthology:
    """A treeful document never reaches the anthology machinery (15d)."""

    def test_detector_never_runs_on_a_treeful_document(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _SYNTH
        store = StructureStore(db_path=str(tmp_path / "structures.db"))
        _save_tree(store, source)
        storage = _TreeStorage(_synthetic_chunks(source))
        pipeline = _make_pipeline(storage, _CannedProvider(), store)

        def _must_not_run(
            heading_chunks: list[dict[str, Any]], source: str
        ) -> list[dict[str, Any]]:
            raise AssertionError("anthology detector ran on a treeful document")

        monkeypatch.setattr(pipeline, "_detect_anthology_parts", _must_not_run)
        # Target-less query — the legacy anthology gate would fire here.
        result = _run_iterative(pipeline, f"summarize {Path(source).name}", source)

        assert _CANNED_ANSWER in str(result["answer"])
        # The real map-reduce summarizer produced per-chapter blocks for the
        # full tree roster.
        assert "Chapter 21" in str(result["answer"])
        assert _PLACEHOLDER_NOTE not in str(result["answer"])
        assert pipeline._structure_source == "tree"
