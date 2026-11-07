"""Unit tests for add-intra-page-chapter-pins (tasks 1.4 and 2.5).

Five surfaces, all against the exported hcd-report fixture (plus synthetic
chunks for the guard-chain edges):

1. Claim channel (D1): claim map shape, halves, recorded offsets.
2. Carve-out rescue (D2): ch4 claims with its real title; license shapes
   stay rejected; tail deferral defers only mid-chunk truncation fragments
   (a match at the chunk's very start is a standalone heading emission and
   claims in-loop exactly as before the change).
3. Claim pin tier + extension + sentinel recovery (D3/D5): the final
   ``chapter_ranges_`` equals the design's corrected expected table; no
   ``(0, -1)`` sentinel survives for the hcd roster.
4. Cut admission (D4): ``_chunk_chapter_owner`` routes every body chunk on
   the oracle pages exactly as the live-oracle table dictates, and the real
   buckets realize the routing where page caps allow.
5. Fallback: an owner whose final range lacks the page yields ``None`` and
   the caller falls back to today's first-range-wins rule.

Rows 19-21 of the ranges table are rule-derived from the implemented claim
map (design D5 "predictions pending"): ch20's claim sits at p22.p1
(ppos > 0), so the extension rule moves ch19's end onto page 22 — the
design table's provisional ``(20, 21)`` predates the captured ch20 cut
position; ch21's cut is ppos 0 and extends nothing.
"""

from __future__ import annotations

import ast
import logging
import re
import types
from pathlib import Path
from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from secondbrain.rag.pipeline._pipeline import _chunk_chapter_owner, _chunk_ppos
from secondbrain.rag.pipeline._structure_mixin import _LICENSE_TITLE_RE
from tests.unit.rag._chapter_fixture_storage import (
    ChapterFixtureStorage,
    load_fixture,
)
from tests.unit.rag.test_anthology_pipeline import _NullProvider, _StubSearcher

HCD = "hcd-report"
USER_MANUAL = "user-manual"
ORACLE_PAGES = (3, 4, 5, 6, 10, 11, 12, 13, 14, 19, 20, 22, 23)


# --- helpers -----------------------------------------------------------------


def _make_chunk(
    text: str,
    page: int = 1,
    ppos: int = 0,
    role: str = "body",
) -> dict[str, Any]:
    return {
        "chunk_text": text,
        "source_file": "synthetic.pdf",
        "page_number": page,
        "page_pos": ppos,
        "chunk_role": role,
        "element_type": "text",
    }


def _derive_claims(chunks: list[dict[str, Any]]) -> dict[int, tuple[Any, ...]]:
    """Run _derive_chapter_numbers over synthetic chunks; return the claims."""
    probe: Any = RAGPipeline.__new__(RAGPipeline)
    probe._llm_provider = None
    probe._searcher = None
    probe._derive_chapter_numbers(chunks)
    return dict(getattr(probe, "_chapter_claims", None) or {})


class _RangesCapture(logging.Handler):
    """Capture the pipeline's "Chapter page ranges" debug line."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.ranges: dict[int, tuple[int, int]] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("Chapter page ranges for"):
            raw = record.getMessage().split(": ", 1)[1]
            self.ranges = {int(k): v for k, v in ast.literal_eval(raw).items()}


def _run_hcd(query: str) -> dict[str, Any]:
    """One full legacy run over the hcd fixture with buckets + ranges captured.

    Buckets are captured from whichever summary entry point the query's
    intent selects: the multi-chapter coverage wrapper hands each chapter's
    bucket to ``_generate_multi_chapter_summary``, a single-target query
    (``chapter N``) routes to ``_generate_single_chapter_summary`` with the
    merged (single-section: untrimmed) chunk list instead.
    """
    source = load_fixture(HCD)[0]["source_file"]
    storage = ChapterFixtureStorage.from_fixture(HCD)
    pipeline = RAGPipeline(
        searcher=_StubSearcher(storage), llm_provider=_NullProvider(), top_k=8
    )
    pipeline._config.streaming_enabled = False
    buckets: dict[int, list[tuple[int, int]]] = {}

    def _recorder(
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        for ch, bucket in chapter_buckets.items():
            buckets[ch] = [
                (int(c.get("page_number") or 0), _chunk_ppos(c)) for c in bucket
            ]
        return ""

    pipeline._generate_multi_chapter_summary = _recorder  # type: ignore[method-assign]

    def _single_recorder(
        final_chunks: list[dict[str, Any]],
        enum_target: str,
        chapter_title: str,
        foreign_titles: list[str] | None = None,
    ) -> str:
        del chapter_title, foreign_titles
        buckets[int(enum_target)] = [
            (int(c.get("page_number") or 0), _chunk_ppos(c)) for c in final_chunks
        ]
        return ""

    pipeline._generate_single_chapter_summary = _single_recorder  # type: ignore[method-assign]
    capture = _RangesCapture()
    plog = logging.getLogger("secondbrain.rag.pipeline._pipeline")
    plog.setLevel(logging.DEBUG)
    plog.addHandler(capture)
    try:
        pipeline._iterative_query(
            query, top_k=8, show_sources=False, source_filter=source
        )
    finally:
        plog.removeHandler(capture)
        plog.setLevel(logging.NOTSET)
    assert capture.ranges is not None, "the ranges debug line must be logged"
    return {
        "source": source,
        "pipeline": pipeline,
        "ranges": capture.ranges,
        "keys": sorted(capture.ranges),
        "buckets": buckets,
        "cuts": pipeline._chapter_cuts,
        "claims": dict(pipeline._chapter_claims),
    }


def _bare_probe(name: str) -> dict[str, Any]:
    """Derivation-only probe over an exported fixture (audit-script recipe)."""
    chunks = load_fixture(name)
    source = chunks[0]["source_file"]
    st = ChapterFixtureStorage(chunks)
    probe: Any = RAGPipeline.__new__(RAGPipeline)
    probe._searcher = types.SimpleNamespace(storage=st)
    probe._llm_provider = None
    structure = probe._probe_document_structure(top_k=10000, source_filter=source)
    entries, _good, _app = probe._derive_chapter_numbers(structure)
    return {
        "source": source,
        "claims": dict(getattr(probe, "_chapter_claims", None) or {}),
        "roster": {e[0]: e[2] for e in entries if e[1] == source},
    }


@pytest.fixture(scope="module")
def hcd_probe() -> dict[str, Any]:
    return _bare_probe(HCD)


@pytest.fixture(scope="module")
def hcd() -> dict[str, Any]:
    return _run_hcd(f"summarize {Path(load_fixture(HCD)[0]['source_file']).name}")


# --- 1. Claim channel (D1) ---------------------------------------------------


class TestClaimChannel:
    def test_claim_map_covers_roster_with_source_position_halves(
        self, hcd_probe: dict[str, Any]
    ) -> None:
        claims: dict[int, tuple[Any, ...]] = hcd_probe["claims"]
        assert set(claims) == set(range(1, 22))
        for claim in claims.values():
            assert len(claim) == 5
            src, page, ppos, offset, half = claim
            assert src == hcd_probe["source"]
            assert page > 0 and ppos >= 0 and offset >= 0
            assert half is (offset < 10**9) or isinstance(half, bool)
            assert isinstance(half, bool)

    def test_recorded_geometry_matches_diagnosis_table(
        self, hcd_probe: dict[str, Any]
    ) -> None:
        claims: dict[int, tuple[Any, ...]] = hcd_probe["claims"]
        # (page, page_pos, offset, first_half) per the verified claim
        # geometry table (design Context; ch8's offset was not captured
        # during diagnosis — only its page/pos are pinned here).
        expected = {
            1: (2, 0, 0, True),
            2: (3, 1, 247, True),
            3: (4, 0, 0, True),
            4: (4, 2, 259, False),
            5: (5, 0, 0, True),
            6: (5, 4, 55, True),
            7: (6, 3, 38, True),
            9: (10, 0, 70, True),
            10: (10, 5, 179, True),
            11: (11, 2, 418, False),
            12: (12, 1, 132, True),
            13: (12, 5, 172, True),
            14: (13, 1, 181, True),
            15: (13, 3, 389, False),
            16: (14, 0, 376, False),
        }
        for n, geometry in expected.items():
            assert (claims[n][1], claims[n][2], claims[n][3], claims[n][4]) == (
                geometry
            ), f"ch{n}"
        assert claims[8][1:3] == (9, 0)

    def test_half_rule_mirrors_structure_annotate(
        self, hcd_probe: dict[str, Any]
    ) -> None:
        claims: dict[int, tuple[Any, ...]] = hcd_probe["claims"]
        by_position = {
            (int(c.get("page_number") or 0), int(c.get("page_pos") or 0)): c
            for c in load_fixture(HCD)
        }
        for claim in claims.values():
            chunk = by_position[(claim[1], claim[2])]
            assert claim[4] == (claim[3] < len(chunk.get("chunk_text", "")) / 2), (
                f"claim at p{claim[1]}.p{claim[2]}"
            )


# --- 2. Carve-out rescue + license gate + tail deferral (D2) ------------------


class TestCarveOutAndTails:
    def test_ch4_claims_with_real_title(self, hcd_probe: dict[str, Any]) -> None:
        assert hcd_probe["roster"][4] == "The Four Phases of HCD Work"

    def test_user_manual_license_shapes_stay_rejected(self) -> None:
        """Every dot-shaped "the" bare match in user-manual stays rejected.

        None of the license-vocabulary shapes wins its number's claim slot.
        """
        probe = _bare_probe(USER_MANUAL)
        claims: dict[int, tuple[Any, ...]] = probe["claims"]
        chunks = load_fixture(USER_MANUAL)
        bare_re = re.compile(
            r"(?:^|\n)\s*(\d{1,2})\.?[^\S\n]+([A-Za-z0-9]"
            r"[A-Za-z0-9 \t\v\f\-\(\),'/:.\u2013\u2014\"\u201c\u201d]{4,200})",
            re.MULTILINE,
        )
        shapes: list[tuple[int, int, int, str]] = []
        for chunk in chunks:
            raw = chunk.get("chunk_text", "")
            for bm in bare_re.finditer(raw):
                if raw[bm.end(1) : bm.end(1) + 1] != ".":
                    continue
                title = re.sub(r"\s+", " ", bm.group(2)).strip()
                fw = (title.lower().split()[0] if title.split() else "").rstrip(":;,.")
                if fw != "the":
                    continue
                page = int(chunk.get("page_number") or 0)
                ppos = int(chunk.get("page_pos") or 0)
                shapes.append((int(bm.group(1)), page, ppos, title))
        assert len(shapes) >= 8, "the corpus regression scan saw 8 shapes"
        for num, page, ppos, title in shapes:
            assert _LICENSE_TITLE_RE.search(title), title
            claim = claims.get(num)
            assert claim is None or (claim[1], claim[2]) != (page, ppos), (
                f"license shape claimed: ch{num} p{page}.p{ppos} {title!r}"
            )

    @pytest.mark.parametrize(
        ("num", "line"),
        [
            (1, "The Project Gutenberg eBook of Alice's Adventures in Wonderland"),
            (2, "The MIT License"),
            (
                3,
                "The Free Software Foundation may publish revised and/or new "
                "versions of the GNU Free Documentation License",
            ),
            (
                4,
                "The name of the author may not be used to endorse or promote "
                "products derived from this software",
            ),
            (5, "The origin of this software must not be misrepresented"),
            (6, "The GNU Free Documentation License"),
            (7, "The documentation license below applies to all contributors"),
            (8, "The redistribution of this work is permitted under the terms"),
            (9, "The ebook of common knowledge is not a chapter heading"),
            (10, "The e-book of recipes collected by the community"),
        ],
    )
    def test_license_vocabulary_never_claims(self, num: int, line: str) -> None:
        claims = _derive_claims([_make_chunk(f"Preface body.\n{num}. {line}")])
        assert num not in claims, f"{num}. {line} must stay rejected"

    def test_hcd_ch7_tail_fragment_never_claims(
        self, hcd_probe: dict[str, Any]
    ) -> None:
        claims: dict[int, tuple[Any, ...]] = hcd_probe["claims"]
        # The p6.p2 fragment "7. The IDEO" defers; the complete capture on
        # p6.p3 wins the slot with the full title.
        assert claims[7][1:3] == (6, 3)
        assert hcd_probe["roster"][7] == (
            "The IDEO Field Guide: Mindsets, Phases, and Methods"
        )

    def test_mid_chunk_tail_fragment_claims_post_scan_when_unclaimed(
        self,
    ) -> None:
        # A truncated heading with no other claimant still claims after the
        # scan — no legitimate claim is lost.
        claims = _derive_claims([_make_chunk("Intro paragraph.\n3. The Deferr")])
        assert 3 in claims
        claim = claims[3]
        assert claim[1:3] == (1, 0)
        assert claim[3] > 0, "the fragment match starts mid-chunk"

    def test_mid_chunk_tail_fragment_yields_to_complete_capture(self) -> None:
        fragment = _make_chunk("Chapter 6 content.\n7. The IDEO", page=6, ppos=2)
        complete = _make_chunk(
            "7. The IDEO Field Guide: Mindsets, Phases, and Methods\nBody.",
            page=6,
            ppos=3,
        )
        claims = _derive_claims([fragment, complete])
        assert claims[7][1:3] == (6, 3)

    def test_standalone_tail_heading_claims_in_loop(self) -> None:
        # A heading chunk whose text IS the heading (match at offset 0,
        # title class running to the chunk end) claims in-loop; deferring it
        # would let a later garbage claim steal the number (the pve ch1
        # regression this refinement prevents).
        heading = _make_chunk("1 Introduction", page=3, ppos=0)
        garbage = _make_chunk(
            "1 Migrate to Proxmox VE https://pve.proxmox.com/wiki/Migrate",
            page=29,
            ppos=12,
        )
        claims = _derive_claims([heading, garbage])
        assert claims[1][1:3] == (3, 0)


# --- 3. Claim tier, extension, sentinel recovery (D3/D5) ---------------------


class TestPinTierAndRanges:
    def test_final_ranges_match_design_table(self, hcd: dict[str, Any]) -> None:
        # D5's corrected expected table, rows 1-18.  Rows 19-21 are
        # rule-derived from the implemented claim map: ch20's cut sits at
        # p22.p1 (ppos > 0) so ch19's end extends onto page 22 — the design
        # table's provisional (20, 21) predates the captured ch20 cut
        # position; ch21's cut is ppos 0 and extends nothing.
        expected = {
            1: (2, 3),
            2: (3, 3),
            3: (4, 4),
            4: (4, 4),
            5: (5, 5),
            6: (5, 6),
            7: (6, 8),
            8: (9, 9),
            9: (10, 10),
            10: (10, 11),
            11: (11, 12),
            12: (12, 12),
            13: (12, 13),
            14: (13, 13),
            15: (13, 13),
            16: (14, 15),
            17: (16, 18),
            18: (19, 20),
            19: (20, 22),
            20: (22, 22),
            21: (23, 10**6),
        }
        assert hcd["ranges"] == expected

    def test_no_zero_sentinel_survives_for_hcd(self, hcd: dict[str, Any]) -> None:
        # ch4/6/10/13/15 used to carry (0, -1); every claimed roster chapter
        # is recovered to a real range starting at its claim page.
        assert all(rng != (0, -1) for rng in hcd["ranges"].values())

    def test_claim_tier_pins_ch1_to_ch3_at_claim_pages(
        self, hcd: dict[str, Any]
    ) -> None:
        # Starts 2/3/4 come from the D3 claim tier (no other tier can pin
        # pages < 10); ch4's same-page claim stays unpinned and is
        # sentinel-recovered to (4, 4).
        assert hcd["ranges"][1][0] == 2
        assert hcd["ranges"][2] == (3, 3)
        assert hcd["ranges"][3] == (4, 4)
        assert hcd["ranges"][4] == (4, 4)


# --- 4. Cut map + admission (D4) ---------------------------------------------


class TestCutAdmission:
    def test_cut_map_geometry(self, hcd: dict[str, Any]) -> None:
        positions = {
            (pg, cut[1], cut[2]) for pg, lst in hcd["cuts"].items() for cut in lst
        }
        assert positions == {
            (2, 0, 1),
            (3, 1, 2),
            (4, 0, 3),
            (4, 2, 4),
            (5, 0, 5),
            (5, 4, 6),
            (6, 3, 7),
            (9, 0, 8),
            (10, 0, 9),
            (10, 5, 10),
            (11, 2, 11),
            (12, 1, 12),
            (12, 5, 13),
            (13, 1, 14),
            (13, 3, 15),
            (14, 0, 16),
            (16, 0, 17),
            (19, 0, 18),
            (20, 4, 19),
            (22, 1, 20),
            (23, 0, 21),
        }
        # before_contains is captured from the PRE-extension ranges: True
        # exactly for the cuts whose before-chapter's range contains the cut
        # page (ch4, ch6, ch10, ch13, ch15 cuts).
        bc_true = {
            (pg, cut[2]) for pg, lst in hcd["cuts"].items() for cut in lst if cut[4]
        }
        assert bc_true == {(4, 4), (5, 6), (10, 10), (12, 13), (13, 15)}

    def test_routing_matches_live_oracle(self, hcd: dict[str, Any]) -> None:
        chunks = load_fixture(HCD)
        body = sorted(
            (
                c
                for c in chunks
                if c.get("chunk_role") == "body"
                and int(c.get("page_number") or 0) in ORACLE_PAGES
            ),
            key=lambda c: (int(c.get("page_number") or 0), _chunk_ppos(c)),
        )
        oracle: dict[int, dict[int, int]] = {
            3: {0: 1, 1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2},
            4: {0: 3, 1: 3, 2: 3, 3: 4, 4: 4, 5: 4},
            5: {0: 5, 1: 5, 2: 5, 3: 5, 4: 6},
            6: {0: 6, 1: 6, 2: 6, 3: 7, 4: 7, 5: 7, 6: 7},
            10: {0: 9, 1: 9, 2: 9, 3: 9, 4: 9, 5: 10, 6: 10},
            11: {0: 10, 1: 10, 2: 11, 3: 11, 4: 11, 5: 11, 6: 11},
            12: {0: 11, 1: 12, 2: 12, 3: 12, 4: 12, 5: 13},
            13: {0: 13, 1: 14, 2: 14, 3: 14, 4: 15, 5: 15},
            14: {0: 16, 1: 16, 2: 16, 3: 16, 4: 16},
            19: dict.fromkeys(range(7), 18),
            20: {0: 18, 1: 18, 2: 18, 3: 18, 4: 19, 5: 19},
            22: {0: 19, 1: 20, 2: 20, 3: 20, 4: 20, 5: 20},
            23: dict.fromkeys(range(7), 21),
        }
        for chunk in body:
            pg = int(chunk.get("page_number") or 0)
            ppos = _chunk_ppos(chunk)
            owner = _chunk_chapter_owner(
                pg, ppos, hcd["cuts"], hcd["keys"], hcd["ranges"]
            )
            assert owner == oracle[pg][ppos], f"p{pg}.p{ppos} routed to {owner}"

    def test_buckets_realize_the_routing_where_caps_allow(
        self, hcd: dict[str, Any]
    ) -> None:
        buckets = hcd["buckets"]
        # Page 4 fully: ch3 keeps its first half, ch4 the second.
        assert buckets[3] == [(4, 0), (4, 1), (4, 2)]
        assert buckets[4] == [(4, 3), (4, 4), (4, 5)]
        # Page 12 fully: ch11's tail, ch12's body, ch13's opener.
        assert buckets[11][-1] == (12, 0)
        assert buckets[12] == [(12, 1), (12, 2), (12, 3), (12, 4)]
        assert buckets[13] == [(12, 5), (13, 0)]
        # Extensions route the previous chapter's tail chunks onto the cut
        # page (ch1 via ch2's cut, ch10 via ch11's cut, ch18/ch19 via their
        # cut pairs).
        assert buckets[1][-1] == (3, 0)
        assert buckets[6][0] == (5, 4) and (6, 2) in buckets[6]
        assert buckets[10][-2:] == [(11, 0), (11, 1)]
        assert buckets[18][-3:] == [(20, 0), (20, 1), (20, 2)]
        assert buckets[19][-1] == (22, 0)


# --- 5. Fallback (D4) ---------------------------------------------------------


class TestFallback:
    def test_owner_whose_range_lacks_the_page_yields_none(self) -> None:
        cuts = {3: [(3, 1, 2, 1, False, True)]}
        # Segment before the cut routes to the before-chapter, which is not
        # a live key here.
        assert _chunk_chapter_owner(3, 0, cuts, [2], {2: (2, 2)}) is None
        # Boundary chunk routes to the after-chapter on the first half, but
        # its final range lost the page.
        assert _chunk_chapter_owner(3, 1, cuts, [2], {2: (2, 2)}) is None
        # With a range that contains the page, the same cut routes.
        assert _chunk_chapter_owner(3, 1, cuts, [2], {2: (2, 4)}) == 2
        # A second-half boundary with before_contains routes to the
        # before-chapter only while its range contains the page.
        cuts2 = {7: [(7, 4, 19, 18, True, False)]}
        assert _chunk_chapter_owner(7, 4, cuts2, [18, 19], {18: (7, 8)}) == 18
        assert _chunk_chapter_owner(7, 4, cuts2, [18, 19], {18: (5, 6)}) is None

    def test_single_target_fallback_keeps_today_admission(self) -> None:
        # Only ch4 targeted → single-section mode; the cut map filters to
        # after ∈ {4}, so the ch3-owned first half of page 4 has no live
        # owner and today's admission filter decides — the whole opener
        # page is admitted (page-level opener evidence), exactly the
        # pre-change behavior for ownerless pages.
        run = _run_hcd("summarize chapter 4")
        assert list(run["buckets"]) == [4]
        # final_chunks arrive score-sorted (the single-section fetch skips
        # the top_k trim), so compare the admitted chunk set orderlessly.
        assert sorted(run["buckets"][4]) == [(4, p) for p in range(6)]
