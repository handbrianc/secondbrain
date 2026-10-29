"""Chapter-window purity, coverage notes, and threshold calibration (Lane B).

Covers fix-summary-fidelity tasks 2.1-2.3:

- 2.1 the range-faithful admission filter: chunks outside a chapter's
  derived page range are refused, with a bounded one-page boundary-straddle
  tolerance for chunks carrying opener evidence.  The real pve-admin-guide
  Chapter 15 -> 16 bleed (CRS material on pages 432-433) is reproduced
  end to end.
- 2.2 per-chapter window-composition statistics and the explicit coverage
  note for empty or foreign-dominated windows, in the placeholder style.
- 2.3 calibration of the note thresholds against the corpus fixtures used
  for chapter-pin work: known-good books emit no coverage notes, and the
  vetoed compilation anthology never builds windows at all.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

import pytest

from secondbrain.rag.pipeline._pipeline import (
    _FOREIGN_SHARE_NOTE_THRESHOLD,
    _STRADDLE_TOLERANCE_PAGES,
    _WINDOW_FOREIGN,
    _WINDOW_IN_RANGE,
    _WINDOW_STRADDLE,
    RAGPipeline,
    _chapter_coverage_note,
    _chapter_window_evidence,
    _classify_window_chunk,
    _window_composition,
)
from tests.unit.rag._chapter_fixture_storage import (
    BASELINE_WINDOW_OVERRIDES,
    ChapterFixtureStorage,
    load_fixture,
)

_SRC = "/fixtures/chapter-window-purity.pdf"

_CANNED_ANSWER = (
    "The document presents its material as a sequence of focused sections, "
    "each developing one theme with concrete examples and practical "
    "guidance. Recurring ideas are introduced early and then applied to "
    "specific cases, so the reader can follow the argument without losing "
    "the overall thread."
)

_EMPTY_NOTE = (
    "No document content was retrieved for this chapter (its detected page "
    "window contains only material from outside the chapter's own page "
    "range), so no faithful summary could be generated."
)
_PARTIAL_NOTE_PREFIX = "Coverage note: only "


def _chunk(
    text: str,
    page: int,
    *,
    role: str = "body",
    pos: int = 0,
) -> dict[str, Any]:
    return {
        "chunk_text": text,
        "chunk_role": role,
        "source_file": _SRC,
        "page_number": page,
        "page_pos": pos,
    }


class _StubSearcher:
    """Searcher double carrying the fixture storage (baseline-capture shape)."""

    def __init__(self, storage: ChapterFixtureStorage) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _NullProvider:
    """LLM double returning "" — mirrors the baseline-capture stub."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 512
    ) -> str:
        return ""


class _CannedProvider:
    """LLM double returning one fixed, plausible, non-empty sentence."""

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return _CANNED_ANSWER


class _RangesCapture(logging.Handler):
    """Capture the pipeline's "Chapter page ranges" debug line (ast-parsed)."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.ranges: dict[int, tuple[int, int]] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("Chapter page ranges for"):
            raw = message.split(": ", 1)[1]
            self.ranges = {int(k): tuple(v) for k, v in ast.literal_eval(raw).items()}


def _make_pipeline(
    storage: ChapterFixtureStorage,
    provider: Any,
) -> RAGPipeline:
    pipeline = RAGPipeline(
        searcher=_StubSearcher(storage),  # type: ignore[arg-type]
        llm_provider=provider,
        top_k=8,
    )
    pipeline._config.streaming_enabled = False
    return pipeline


def _run_iterative(
    pipeline: RAGPipeline,
    query: str,
    source: str,
) -> str:
    result = pipeline._iterative_query(
        query,
        top_k=8,
        show_sources=False,
        source_filter=source,
    )
    return str(result["answer"])


def _record_buckets(
    pipeline: RAGPipeline,
    monkeypatch: pytest.MonkeyPatch,
    return_text: str = "",
) -> dict[str, list[int]]:
    """Capture bucket page lists at the summarizer boundary (baseline recipe).

    ``return_text`` makes the double answer with canned text: the canned
    text bypasses the summarizer's internal plausibility gate, which rejects
    ungrounded LLM output — the wrapper's note-splicing contract is tested
    against what the summarizer would have produced, not against the gate.
    """
    recorded: dict[str, list[int]] = {}

    def _recorder(
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        for ch, bucket in chapter_buckets.items():
            recorded[str(ch)] = [c.get("page_number") or 0 for c in bucket]
        return return_text

    monkeypatch.setattr(pipeline, "_generate_multi_chapter_summary", _recorder)
    return recorded


def _fixture_source(name: str) -> str:
    return str(load_fixture(name)[0]["source_file"])


class TestRangeFaithfulAdmission:
    """The admission filter's verdict surface (task 2.1, unit level)."""

    @staticmethod
    def _classify(
        chunk: dict[str, Any],
        ch: int,
        start: int,
        end: int,
        *,
        opener: bool = False,
        title: str = "",
    ) -> str:
        return _classify_window_chunk(
            chunk,
            ch,
            start,
            end,
            opener_on_start_page=opener,
            title=title,
        )

    def test_speculative_start_page_refuses_foreign_tail(self) -> None:
        # pve Chapter 16 shape: its range starts at 433, but page 433 holds
        # only Chapter 15's closing CRS bleed bullets — no ch16 opener
        # evidence on the page or in the chunk, so the chunk is refused.
        bleed = _chunk(
            "- Node affinity rules: If a node affinity rule is created or "
            "HA resources/nodes are affected, those CRM commands update the "
            "rules accordingly.",
            433,
        )
        assert (
            self._classify(bleed, 16, 433, 448, title="Backup and Restore")
            == _WINDOW_FOREIGN
        )

    def test_in_range_beyond_start_admitted_without_evidence(self) -> None:
        prose = _chunk("prose on backup schedules and retention windows", 435)
        assert (
            self._classify(prose, 16, 433, 448, title="Backup and Restore")
            == _WINDOW_IN_RANGE
        )

    def test_opener_start_page_admits_everything_on_it(self) -> None:
        # When the start page itself names the chapter, every chunk on it is
        # admitted — including chunks without their own evidence (a page
        # banner merged into a neighbor chunk).
        bannerless = _chunk("prose continuing from the banner above", 433)
        assert (
            self._classify(
                bannerless, 16, 433, 448, opener=True, title="Backup and Restore"
            )
            == _WINDOW_IN_RANGE
        )

    def test_straddle_tolerance_one_page(self) -> None:
        title = "Backup and Restore"
        # The chapter's opening sentence merged onto the previous chapter's
        # last page: one page before the range with opener evidence.
        straddler = _chunk("16 Backup and Restore prose on backup storage", 432)
        assert self._classify(straddler, 16, 433, 448, title=title) == (
            _WINDOW_STRADDLE
        )
        # The same page without opener evidence stays refused.
        tail = _chunk("prose finishing the CRS affinity rules", 432)
        assert self._classify(tail, 16, 433, 448, title=title) == _WINDOW_FOREIGN
        # Two pages before the range is beyond the tolerance even with
        # evidence.
        distant = _chunk("16 Backup and Restore prose on backup storage", 431)
        assert self._classify(distant, 16, 433, 448, title=title) == _WINDOW_FOREIGN
        assert _STRADDLE_TOLERANCE_PAGES == 1

    def test_out_of_range_pages_never_admitted(self) -> None:
        # Beyond the range end, even with evidence: the range governs.
        far = _chunk("16 Backup and Restore prose on backup storage", 449)
        assert (
            self._classify(far, 16, 433, 448, title="Backup and Restore")
            == _WINDOW_FOREIGN
        )


class TestTwoTierOpenerEvidence:
    """Tight tier gates admission; the page-level tier only widens openers."""

    def test_tight_shapes_fire(self) -> None:
        title = "Backup and Restore"
        # Chapter banner at the text start.
        assert _chapter_window_evidence(
            _chunk("Chapter 16 Backup and Restore\nprose on backup modes", 434),
            16,
            title,
        )
        # Own section numbering at the text start.
        assert _chapter_window_evidence(
            _chunk("16.1 Backup storage\nprose on vzdump", 434), 16, title
        )
        # Roster title opening the text.
        assert _chapter_window_evidence(
            _chunk("backup and restore prose on archive modes", 434), 16, title
        )
        # Number + title pair opening the text.
        assert _chapter_window_evidence(
            _chunk("16 Backup and Restore\nprose on backup modes", 434), 16, title
        )
        # Number + title glued mid-text: an opener sentence merged onto the
        # previous chunk's tail.
        assert _chapter_window_evidence(
            _chunk("closing prose. 16 Backup and Restore opens here", 432),
            16,
            title,
        )

    def test_glued_roster_title_matches_space_free_chunk(self) -> None:
        # Docling space regression: the chunk carries the number and title
        # without inner whitespace ("16.ClusterManager…").
        assert _chapter_window_evidence(
            _chunk("16.ClusterManager tuning prose", 60), 16, "Cluster Manager"
        )

    def test_loose_mentions_never_pass_the_tight_tier(self) -> None:
        title = "Eleventh Model Pipelines"
        # Cross-reference: the chapter number without its title or numbering.
        xref = _chunk("see 11 for worked examples and archived notes", 300)
        assert not _chapter_window_evidence(xref, 11, title)
        # A network address that merely contains the number.
        addr = _chunk("network=10.1.2.0/24 gateway prose", 224)
        assert not _chapter_window_evidence(addr, 10, "Quantization Strategies")

    def test_page_level_tier_adds_loose_shapes(self) -> None:
        title = "Eleventh Model Pipelines"
        xref = _chunk("see 11 for worked examples and archived notes", 300)
        # The page-level tier fires on the bare number mention: a false hit
        # there only widens an opener page, it never admits boundary-page
        # foreign chunks.
        assert _chapter_window_evidence(xref, 11, title, page_level=True)
        # Numbered heading anywhere in the chunk (title drifted from the
        # printed one).
        heading = _chunk("reviewing 6. Phase-by-Phase Working Table prose", 5)
        assert _chapter_window_evidence(heading, 6, "", page_level=True)
        assert not _chapter_window_evidence(heading, 6, "")
        # Roster title anywhere, but not opening the text: the tight tier
        # requires the title to open the chunk (or the number+title pair);
        # the page-level tier adds the anywhere shape.
        drifted = _chunk("the backup and restore chapter explains modes", 434)
        assert _chapter_window_evidence(
            drifted, 16, "Backup and Restore", page_level=True
        )
        assert not _chapter_window_evidence(drifted, 16, "Backup and Restore")

    def test_empty_text_carries_no_evidence(self) -> None:
        assert not _chapter_window_evidence(_chunk("", 4), 1, "Anything At All")


class TestWindowCompositionAndNotes:
    """Window-composition statistics and the coverage-note contract (D2)."""

    def test_composition_stats_shape(self) -> None:
        comp = _window_composition(8, 1, 4)
        assert comp == {
            "in_range": 8,
            "foreign": 1,
            "dropped": 4,
            "foreign_share": pytest.approx(1 / 9),
        }
        assert _window_composition(0, 0, 0)["foreign_share"] == 0.0

    def test_empty_window_gets_the_placeholder_style_note(self) -> None:
        comp = _window_composition(0, 0, 1)
        assert _chapter_coverage_note(comp) == _EMPTY_NOTE

    def test_foreign_dominated_window_gets_the_partial_note(self) -> None:
        comp = _window_composition(2, 3, 0)
        note = _chapter_coverage_note(comp)
        assert note is not None and note.startswith(_PARTIAL_NOTE_PREFIX)
        assert "only 2 of 5 window chunks" in note
        assert "this summary is partial" in note

    def test_share_boundary_is_strictly_greater(self) -> None:
        # Exactly half foreign: no note (calibrated boundary, strict >).
        assert _chapter_coverage_note(_window_composition(4, 4, 0)) is None
        assert _FOREIGN_SHARE_NOTE_THRESHOLD == 0.5
        # One over the boundary: note.
        assert _chapter_coverage_note(_window_composition(3, 4, 0)) is not None

    def test_truly_empty_window_defers_to_the_base_placeholder(self) -> None:
        # A window with no candidates at all (sentinel/empty range) is the
        # existing empty-bucket placeholder's territory, not the D2 note's.
        assert _chapter_coverage_note(_window_composition(0, 0, 0)) is None

    def test_healthy_window_keeps_output_unchanged(self) -> None:
        assert _chapter_coverage_note(_window_composition(8, 0, 0)) is None
        # A tolerated straddle well under the threshold is not flagged.
        assert _chapter_coverage_note(_window_composition(7, 1, 0)) is None


def _straddle_book() -> list[dict[str, Any]]:
    """A three-chapter book: banner headings @20, @30 and @40.

    Three chapters force the multi-chapter round-robin path with the
    deferred straddle pool (a two-chapter book takes the lossless
    single-section fetch instead, which admits boundary straddlers without
    any window budget).  Titles derive from the banner headings (as in the
    real books), body chunks are pure prose, and page 29 (ch1's last page)
    may carry straddler chunks whose glued cross-reference shape
    ("… See 2 <title> …") carries ch2 opener evidence for the admission
    filter while — like the real user-manual "See 3 Configuring" chunk —
    pinning nothing: ch2's pin stays on its @30 heading anchor.
    """
    return [
        _chunk("1 Alpha Foundational Frameworks", 20, role="heading"),
        _chunk("prose deriving wavelets", 20),
        _chunk("prose buffering stream windows", 21),
        _chunk("prose pacing coherence schedules", 22),
        _chunk("2 Beta Optimization Landscapes", 30, role="heading"),
        _chunk("3 Gamma Convolution Pipelines", 40, role="heading"),
        _chunk("prose convolving kernels", 41),
    ]


def _with_straddlers(
    chunks: list[dict[str, Any]],
    texts: list[str],
) -> list[dict[str, Any]]:
    for pos, text in enumerate(texts):
        chunks.append(_chunk(text, 29, pos=pos))
    return chunks


def _straddle_texts(count: int) -> list[str]:
    base = "prose harvesting meadow fields. See 2 Beta Optimization Landscapes"
    suffixes = [
        " for the tuning workflow calmly",
        " before configuring the estates",
        " alongside the archived notes",
    ]
    return [f"{base}{suffixes[i % len(suffixes)]}" for i in range(count)]


def _finish_book(
    chunks: list[dict[str, Any]],
    ch2_pages: list[int],
) -> list[dict[str, Any]]:
    for i, pg in enumerate(ch2_pages):
        chunks.append(_chunk(f"prose mapping convexity regimes {i}", pg))
    return chunks


class TestBoundaryStraddleTolerance:
    """End-to-end straddle behavior on a synthetic three-chapter book."""

    def test_straddling_opener_admitted_as_foreign_when_window_has_room(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = _finish_book(
            _with_straddlers(_straddle_book(), _straddle_texts(1)),
            [30, 31],
        )
        storage = ChapterFixtureStorage(chunks)
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_buckets(pipeline, monkeypatch)
        answer = _run_iterative(pipeline, "summarize this document", _SRC)

        # ch2's window holds its own pages plus the tolerated straddle,
        # counted as foreign in the composition (D2).
        assert sorted(recorded["2"]) == [29, 30, 31]
        comp = pipeline._window_compositions[2]
        assert comp["in_range"] == 2
        assert comp["foreign"] == 1
        assert comp["foreign_share"] == pytest.approx(1 / 3)
        # ch1's claim is unaffected: the page stays in its own window.
        assert recorded["1"] == [20, 21, 22, 29]
        assert pipeline._window_compositions[1]["foreign"] == 0
        # A share of 1/3 is below the note threshold: healthy output.
        assert _PARTIAL_NOTE_PREFIX not in answer
        assert _EMPTY_NOTE not in answer
        assert "Chapter 2 — Beta Optimization Landscapes (approx pages 30+)" in answer

    def test_full_window_suppresses_straddle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # ch2's in-range material fills the 8-slot window: the boundary
        # chunk must not displace the chapter's own content (the real
        # user-manual ch3 "See 3 Configuring" shape).
        chunks = _finish_book(
            _with_straddlers(_straddle_book(), _straddle_texts(1)),
            [*range(30, 37), 36],
        )
        storage = ChapterFixtureStorage(chunks)
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_buckets(pipeline, monkeypatch)
        answer = _run_iterative(pipeline, "summarize this document", _SRC)

        assert sorted(recorded["2"]) == sorted([*range(30, 37), 36])
        assert 29 not in recorded["2"]
        comp = pipeline._window_compositions[2]
        assert comp["in_range"] == 8
        assert comp["foreign"] == 0
        assert comp["dropped"] == 0
        assert "Chapter 2 — Beta Optimization Landscapes (approx pages 30+)" in answer
        assert _PARTIAL_NOTE_PREFIX not in answer


class TestForeignDominatedWindowNote:
    """A foreign-dominated window keeps its partial summary plus the note."""

    def test_partial_summary_carries_the_note(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Three ch2-evidence chunks sit on page 29 (inside ch1's range) and
        # straddle in, while ch2's own window holds only one prose chunk on
        # its opener page @30 and one prose chunk @31: foreign (3) dominates
        # in-range (2).  The canned recorder answers at the summarizer
        # boundary — the real plausibility gate inside
        # _generate_multi_chapter_summary would reject the ungrounded canned
        # text, and the wrapper's note-splicing contract is what's under
        # test here.
        chunks = _finish_book(
            _with_straddlers(_straddle_book(), _straddle_texts(3)),
            [30, 31],
        )
        storage = ChapterFixtureStorage(chunks)
        pipeline = _make_pipeline(storage, _CannedProvider())
        recorded = _record_buckets(pipeline, monkeypatch, return_text=_CANNED_ANSWER)
        answer = _run_iterative(pipeline, "summarize this document", _SRC)

        comp = pipeline._window_compositions[2]
        assert comp["in_range"] == 2
        assert comp["foreign"] == 3
        assert comp["foreign_share"] == pytest.approx(0.6)
        # The straddlers joined AFTER the in-range pass (deferred
        # supplement): the window leads with the chapter's own pages.
        assert recorded["2"] == [30, 31, 29, 29, 29]
        # The partial summary keeps its entry, with the explicit note
        # attached; foreign content is not presented silently as ch2's own.
        note = _chapter_coverage_note(comp)
        assert note is not None and note.startswith(_PARTIAL_NOTE_PREFIX)
        assert f"{_CANNED_ANSWER}\n\n{note}" in answer
        # Healthy windows (ch1, ch3) keep their summary unchanged: canned
        # text per chapter, and the note appears exactly once.
        assert answer.count(_CANNED_ANSWER) == 3
        assert answer.count(note) == 1


class TestPveChapterBleedRegression:
    """Task 2.1's reproduction: the real pve Chapter 15 -> 16 bleed."""

    def test_ch16_window_excludes_crs_bleed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        source = _fixture_source("pve-admin-guide")
        storage = ChapterFixtureStorage.from_fixture("pve-admin-guide")
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_buckets(pipeline, monkeypatch)
        _run_iterative(pipeline, f"summarize {Path(source).name}", source)

        # Chapter 16's window is built exclusively from its own pages: the
        # CRS 15.12.x bleed bullets on page 433 are refused, and nothing
        # from page 432 (Chapter 15's last page) leaks in either.  The
        # density cap (D4) then admits 5 of page 434's 7 in-range body
        # chunks and 3 of page 435's 9, so the pinned window below is the
        # post-D4 one (see BASELINE_WINDOW_OVERRIDES).
        assert recorded["16"] == BASELINE_WINDOW_OVERRIDES["pve-admin-guide"]["16"]
        assert 433 not in recorded["16"]
        assert 432 not in recorded["16"]
        comp = pipeline._window_compositions[16]
        assert comp["in_range"] == 8
        assert comp["foreign"] == 0
        assert comp["dropped"] == 4
        assert comp["foreign_share"] == 0.0
        # Chapter 15 keeps its own window: the bleed pages stay out of it.
        # The density cap (D4) moves its page list onto the post-D4 values
        # (page 409 holds 11 in-range body chunks -> cap 6, so it admits 6
        # and spills 2 onto page 410); the refusal-free composition is
        # unchanged.
        assert recorded["15"] == [409, 409, 409, 409, 409, 409, 410, 410]
        assert pipeline._window_compositions[15]["dropped"] == 0


_DENSE_BANNER_TEXTS: tuple[str, ...] = (
    # The banner's second line carries the chapter's first section number:
    # the flow's post-admission "N.1" header injection otherwise prepends
    # "2.1 " to the bucket's first chunk, which would blur the identity
    # assertion below.  Real openers carry their first section header too.
    "Chapter 2 Beta Optimization Landscapes\n2.1 VM snapshot mode captures guest state",
    "snapshot mode freezes the guest file system briefly",
    "snapshot mode keeps the memory image beside the disk state",
    "2.3 Container backup modes\narchive the configuration directories",
    "container backup runs walk each mounted volume in turn",
    "container backup schedules follow the retention window",
    "container backup verification reopens every archived bundle",
    "container backup notes stay beside the restore checklist",
)


def _dense_banner_book() -> list[dict[str, Any]]:
    """The straddle book with ch2's opener page 30 made PVE-ch16-dense.

    Page 30 carries 8 body chunks in the real dense-opener shape — chapter
    banner, VM prose, a numbered section heading embedded in body text
    ("2.3 Container backup modes" at page_pos 3, the docling shape the
    header-promotion path exists for), then container prose — and page 31
    carries 3 tail chunks.  ch1 (pages 20-22) and ch3 (page 41) stay
    sparse, so the bounds decide ch2's window alone; the stored chunk list
    is handed to ``ChapterFixtureStorage`` in document order, matching its
    own ordering guarantee (D3 layer 1 — the client-side sort is pinned by
    the iterative tests' shuffled storage double).

    The test pins the probe's structural sample to the three opener
    headings: a real top-k probe over this book ranks page 30's dense body
    chunks ahead of ch3's lone heading and drops chapter 3 from the roster
    entirely — a probe-ranking artifact, not the admission behavior under
    test here.
    """
    banner_page = [
        _chunk(text, 30, pos=pos) for pos, text in enumerate(_DENSE_BANNER_TEXTS)
    ]
    tail_page = [
        _chunk("prose archiving container estates calmly", 31, pos=0),
        _chunk("prose restoring archived bundles quietly", 31, pos=1),
        _chunk("prose verifying the restore checklist again", 31, pos=2),
    ]
    return [
        _chunk("1 Alpha Foundational Frameworks", 20, role="heading"),
        _chunk("prose deriving wavelets", 20),
        _chunk("prose buffering stream windows", 21),
        _chunk("prose pacing coherence schedules", 22),
        _chunk("2 Beta Optimization Landscapes", 30, role="heading"),
        *banner_page,
        *tail_page,
        _chunk("3 Gamma Convolution Pipelines", 40, role="heading"),
        _chunk("prose convolving kernels", 41),
    ]


def _dense_probe() -> list[dict[str, Any]]:
    """The structural sample a healthy probe returns for the dense book."""
    return [
        {
            "chunk_text": text,
            "chunk_role": "heading",
            "source_file": _SRC,
            "page_number": page,
        }
        for text, page in (
            ("1 Alpha Foundational Frameworks", 20),
            ("2 Beta Optimization Landscapes", 30),
            ("3 Gamma Convolution Pipelines", 40),
        )
    ]


def _straddle_cap_book() -> list[dict[str, Any]]:
    """The straddle book with four page-29 straddler candidates.

    ch2's in-range material (page 30's prose chunk plus three page-31 tail
    chunks) leaves the 8-slot window 4 short, so the supplement's admission
    bound — the base per-page cap, since page 29 lies outside ch2's range
    and the density pre-pass counts nothing for it there — is what stops
    the fourth straddler, not the chapter limit.
    """
    chunks = _with_straddlers(_straddle_book(), _straddle_texts(4))
    # Explicit within-page positions: _finish_book leaves every tail chunk
    # at pos 0 (its older consumers pin pages only), but the supplement
    # admits straddlers in document order, so the page-31 tail needs its
    # own 0/1/2 ordering to be readable as such.
    chunks.append(_chunk("prose mapping convexity regimes 0", 30, pos=0))
    chunks.append(_chunk("prose mapping convexity regimes 1", 31, pos=0))
    chunks.append(_chunk("prose mapping convexity regimes 2", 31, pos=1))
    chunks.append(_chunk("prose mapping convexity regimes 3", 31, pos=2))
    return chunks


def _record_window_positions(
    pipeline: RAGPipeline,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, list[tuple[int, int, str]]]:
    """Capture (page, position, text) triples at the summarizer boundary.

    Like :func:`_record_buckets` (whose page-only lists the older tests
    pin), but keeps the within-page position and the chunk text so a test
    can assert document order and chunk identity inside a window.
    Returning "" keeps the LLM out of the run — the roster fallback speaks
    instead.  Note the flow's post-admission "N.1" header injection
    mutates the first bucket chunk's text in place; the recorded text of
    that one chunk carries the injected prefix.
    """
    recorded: dict[str, list[tuple[int, int, str]]] = {}

    def _recorder(
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        for ch, bucket in chapter_buckets.items():
            recorded[str(ch)] = [
                (
                    int(c.get("page_number") or 0),
                    int(c.get("page_pos") or 0),
                    str(c.get("chunk_text") or ""),
                )
                for c in bucket
            ]
        return ""

    monkeypatch.setattr(pipeline, "_generate_multi_chapter_summary", _recorder)
    return recorded


class TestDensePageDocumentOrder:
    """D3+D4 end to end: document-order admission on a PVE-ch16-shaped page."""

    def test_dense_opener_admits_in_document_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = _dense_banner_book()
        storage = ChapterFixtureStorage(chunks)
        pipeline = _make_pipeline(storage, _NullProvider())
        # Pin the structural roster (see _dense_banner_book): without this,
        # a real top-k probe ranks the dense page's body chunks ahead of
        # ch3's lone heading and the book degrades to a 2-chapter lossless
        # fetch where no per-page bound applies at all.
        monkeypatch.setattr(
            pipeline,
            "_probe_document_structure",
            lambda top_k, source_filter=None: _dense_probe(),
        )
        recorded = _record_window_positions(pipeline, monkeypatch)
        answer = _run_iterative(pipeline, "summarize this document", _SRC)

        # D3: the window reads in stored document order — banner (pos 0),
        # VM prose (pos 1-2), the embedded 2.3 heading (pos 3), container
        # prose (pos 4).  D4: page 30 holds 8 in-range body chunks -> bound
        # ceil(0.6 * 8) = 5 (the flat base bound 3 would keep only 3), so
        # the window keeps 5 of them and spills 3 onto page 31.
        assert [t[:2] for t in recorded["2"]] == [
            (30, 0),
            (30, 1),
            (30, 2),
            (30, 3),
            (30, 4),
            (31, 0),
            (31, 1),
            (31, 2),
        ]
        # Chunk identity at the shape boundaries: the admitted pos-3 chunk
        # is the embedded 2.3 heading (the injection post-pass only
        # rewrites the bucket's first chunk, so pos 3 keeps its text).
        assert recorded["2"][3][2].startswith("2.3 Container backup modes")
        assert recorded["2"][0][2].startswith("Chapter 2 Beta Optimization Landscapes")
        # The sparse chapters keep their full windows: pages at or under
        # the base bound are unaffected (spec: a sparse page is unaffected).
        assert [t[:2] for t in recorded["1"]] == [(20, 0), (21, 0), (22, 0)]
        assert [t[:2] for t in recorded["3"]] == [(41, 0)]
        # Purity unchanged: the window holds only ch2's own pages, the
        # composition is healthy, and the output keeps the roster line with
        # no coverage note.
        assert [pg for pg, _pos, _txt in recorded["2"]] == [
            30,
            30,
            30,
            30,
            30,
            31,
            31,
            31,
        ]
        comp = pipeline._window_compositions[2]
        assert comp["in_range"] == 8
        assert comp["foreign"] == 0
        assert comp["dropped"] == 0
        assert _PARTIAL_NOTE_PREFIX not in answer
        assert _EMPTY_NOTE not in answer
        assert "Chapter 2 — Beta Optimization Landscapes (approx pages 30+)" in answer


class TestStraddleSupplementCap:
    """The straddle supplement respects the (base) per-page cap, not the limit."""

    def test_fourth_straddler_refused_by_page_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunks = _straddle_cap_book()
        storage = ChapterFixtureStorage(chunks)
        pipeline = _make_pipeline(storage, _NullProvider())
        recorded = _record_window_positions(pipeline, monkeypatch)
        answer = _run_iterative(pipeline, "summarize this document", _SRC)

        # Exactly 3 of the 4 straddlers join, in document order (positions
        # 0-2): page 29 lies outside ch2's range, so the density pre-pass
        # counts nothing for it and the supplement's bound falls back to
        # the base per-page cap (3).  The window holds 7 chunks — under
        # the 8-slot chapter limit — so the cap, not the limit, refused
        # the fourth straddler (position 3 is absent).
        assert [t[:2] for t in recorded["2"]] == [
            (30, 0),
            (31, 0),
            (31, 1),
            (31, 2),
            (29, 0),
            (29, 1),
            (29, 2),
        ]
        assert len(recorded["2"]) == 7
        # ch1 keeps its own claim on page 29: its window admits the
        # straddlers it owns in document order — three of the four, the
        # page's bound (n=4 -> ceil(2.4) = 3, unchanged from the base cap) —
        # and ch2's copies do not displace them.
        assert [t[:2] for t in recorded["1"]] == [
            (20, 0),
            (21, 0),
            (22, 0),
            (29, 0),
            (29, 1),
            (29, 2),
        ]
        # A 3/7 foreign share stays below the note threshold: healthy
        # output, roster line only.
        comp = pipeline._window_compositions[2]
        assert comp["in_range"] == 4
        assert comp["foreign"] == 3
        assert comp["foreign_share"] == pytest.approx(3 / 7)
        assert _PARTIAL_NOTE_PREFIX not in answer
        assert _EMPTY_NOTE not in answer
        assert "Chapter 2 — Beta Optimization Landscapes (approx pages 30+)" in answer


class TestThresholdCalibration:
    """Task 2.3: thresholds calibrated on the corpus fixtures (D1/D2)."""

    @pytest.mark.parametrize(
        "fixture_name",
        ("user-manual", "pve-admin-guide", "hcd-report"),
    )
    def test_known_good_books_emit_no_coverage_notes(
        self, monkeypatch: pytest.MonkeyPatch, fixture_name: str
    ) -> None:
        source = _fixture_source(fixture_name)
        storage = ChapterFixtureStorage.from_fixture(fixture_name)
        pipeline = _make_pipeline(storage, _NullProvider())
        _record_buckets(pipeline, monkeypatch)
        answer = _run_iterative(pipeline, f"summarize {Path(source).name}", source)

        compositions = pipeline._window_compositions
        assert compositions, "every book must build chapter windows"
        # No chapter's window is empty of in-range content, and no window's
        # tolerated foreign share approaches the note threshold: the
        # calibrated values (in_range == 0 rule, 0.5 share) stay silent on
        # the whole corpus.
        for ch, comp in compositions.items():
            assert _chapter_coverage_note(comp) is None, (
                f"{fixture_name} chapter {ch}: unexpected coverage note "
                f"for composition {comp}"
            )
        max_share = max(float(c["foreign_share"]) for c in compositions.values())
        assert max_share <= _FOREIGN_SHARE_NOTE_THRESHOLD
        # And the note text never surfaces in the answer either.
        assert _EMPTY_NOTE not in answer
        assert _PARTIAL_NOTE_PREFIX not in answer

    def test_vetoed_compilation_never_builds_windows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The knowledge-compilation anthology's detector-miss path vetoes
        # the legacy chapter map and answers with a whole-document
        # overview: no chapter windows, hence no composition statistics and
        # no coverage notes.
        source = _fixture_source("knowledge-compilation")
        storage = ChapterFixtureStorage.from_fixture("knowledge-compilation")
        pipeline = _make_pipeline(storage, _CannedProvider())
        monkeypatch.setattr(
            RAGPipeline,
            "_detect_anthology_parts",
            staticmethod(lambda heading_chunks, source: None),
        )
        answer = _run_iterative(pipeline, "summarize knowledge_compilation.pdf", source)

        assert pipeline._window_compositions == {}
        assert _PARTIAL_NOTE_PREFIX not in answer
        assert _EMPTY_NOTE not in answer
