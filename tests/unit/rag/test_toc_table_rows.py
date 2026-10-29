"""Lane B (fix-summary-fidelity): ToC rows in Lane A's table serialization.

The re-ingested TEST store serializes the printed ToC one row per line with
the row cells joined by " — " (optionally an interleaved dot-leader cell),
while stores ingested before that change keep the historical flat shape
("12 Bayesian Deep Learning 310").  These tests pin both shapes: chapter
rows parse with clean titles under the ToC listing tier, section rows and
split rows (page lost in extraction) never pin, the run-on recovery tier
recovers the correct (title, printed page) pairs from table-serialized
chunks, and the historical flat run-on fixtures keep producing identical
results.  The end-to-end test reuses the harness classes from
``test_pipeline`` (imported inside the test, never subclassed) so their own
tests are not re-run here.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag.test_pipeline import _make_mock_searcher, _SequenceProvider

SRC = "guide.pdf"
LISTING_PAGE = 5
PVE_SRC = "pve-admin-guide.pdf"
RUNON_PAGE = 8


def _pipeline() -> RAGPipeline:
    """Pipeline double for direct parser calls (same shape as the B3 tests)."""
    return RAGPipeline(
        searcher=_make_mock_searcher(),
        llm_provider=_SequenceProvider([]),  # type: ignore[arg-type]
        top_k=5,
        context_window=5,
    )


def _toc_chunk(text: str, page: int = LISTING_PAGE) -> dict[str, Any]:
    return {
        "chunk_text": text,
        "chunk_role": "toc_entry",
        "source_file": SRC,
        "page_number": page,
    }


def _runon_chunk(text: str, page: int = RUNON_PAGE) -> dict[str, Any]:
    return {
        "chunk_text": text,
        "source_file": PVE_SRC,
        "page_number": page,
    }


class TestTableListingRows:
    """_toc_chapter_listings parses the table-serialized chapter rows."""

    @staticmethod
    def _listings(text: str) -> tuple[dict[int, tuple[str, int]], set[int]]:
        return _pipeline()._toc_chapter_listings([_toc_chunk(text)])

    def test_chapter_rows_parse_with_clean_titles(self) -> None:
        listings, mentions = self._listings(
            "2 Installing Proxmox VE — 10\n12 Bayesian Deep Learning — 350\n"
        )
        assert mentions == set(), mentions
        assert listings == {
            2: ("Installing Proxmox VE", 10),
            12: ("Bayesian Deep Learning", 350),
        }, listings

    def test_dot_leader_cell_never_enters_title(self) -> None:
        listings, _ = self._listings("2 Installing Proxmox VE — . . . . — 10\n")
        assert listings == {2: ("Installing Proxmox VE", 10)}, listings

    def test_section_rows_never_become_chapter_listings(self) -> None:
        """A dotted section label ("1.1 ...") fails both row shapes."""
        listings, _ = self._listings(
            "1.1 Central Management — . . . . — 2\n1.2 Command Line Interface — 3\n"
        )
        assert listings == {}, listings

    def test_flat_rows_still_parse(self) -> None:
        """The historical flat shape parses identically (no table regex hit)."""
        listings, _ = self._listings("12 Bayesian Deep Learning 310\n")
        assert listings == {12: ("Bayesian Deep Learning", 310)}, listings

    def test_gate_accepts_table_rows(self) -> None:
        """_toc_listing_pages returns table-format listings at full coverage."""
        rows = "\n".join(
            f"{n} Cluster Topic Alpha Beta — {10 * n}" for n in range(1, 13)
        )
        listings, mentions = _pipeline()._toc_listing_pages(
            [_toc_chunk(rows)], {12: 24}, set(range(1, 13))
        )
        assert mentions == set(), mentions
        assert len(listings) == 12, listings
        assert listings[7] == ("Cluster Topic Alpha Beta", 70), listings


class TestTableRunonRows:
    """_recovered_runon_toc_rows on table-serialized ToC chunks."""

    @staticmethod
    def _rows(text: str, page: int = RUNON_PAGE) -> dict[int, tuple[str, int]]:
        return _pipeline()._recovered_runon_toc_rows(
            [_runon_chunk(text, page)], PVE_SRC
        )

    def test_stranded_chapter_row_recovered_with_table_tails(self) -> None:
        """The pmxcfs shape in table serialization recovers the row.

        The chapter row sits between a three-level section tail and its own
        two-level sections, so the tail branch must name it from the
        dot-leader/tail normalization.
        """
        rows = self._rows(
            "5.14.2 Migration Network — . . . . — 134\n"
            "6 Proxmox Cluster File System (pmxcfs) — 136\n"
            "6.1 POSIX Compatibility — . . . . — 136\n"
        )
        assert rows == {6: ("Proxmox Cluster File System (pmxcfs)", 136)}, rows

    def test_chapter_only_chunk_recovered_via_glued_scan(self) -> None:
        """Chapter rows with no dotted sections in the chunk still recover.

        Pass 1's splitter needs a two-level section boundary to cut; a chunk
        of bare chapter rows has none, so only the pass-2 glued scan (which
        sees the normalized tails) can pin them.
        """
        rows = self._rows(
            "2 Installing Proxmox VE — 10\n3 Host System Administration — 27\n"
        )
        assert rows == {
            2: ("Installing Proxmox VE", 10),
            3: ("Host System Administration", 27),
        }, rows

    def test_section_tail_not_crowned_as_chapter(self) -> None:
        """A deep section's row tail is never crowned as the chapter's title.

        The TEST-store regression: "5.3.3 ... — 112" sat inside a span cut
        at the next two-level section, so the tail branch crowned the
        section name as chapter 5's title.  The dotted-title guard rejects
        it and the chunk recovers nothing.
        """
        rows = self._rows(
            "5.3.2 Log — 111\n"
            "5.3.3 Multiple Clusters in the Same Network — 112\n"
            "5.4 Enabling and Disabling HA — 113\n"
        )
        assert rows == {}, rows

    def test_deep_section_tail_rejected_before_chapter_break(self) -> None:
        """The 16.6.2@419 regression shape stays rejected.

        Without the dotted-title guard the tail branch pinned chapter 16 to
        a section row's title and page.
        """
        rows = self._rows(
            "16.6.1 Home Backup — 418\n"
            "16.6.2 Retention Settings Example — 419\n"
            "16.7 Default Storage — 424\n"
        )
        assert rows == {}, rows

    def test_split_row_without_page_cell_skipped(self) -> None:
        """Ch7's page cell landed in a separate body chunk: no row invented.

        The heading chunk ("7 Proxmox VE Storage", no page) and the lone page
        chunk ("141") must both parse to nothing while a neighbor's complete
        chapter row in an adjacent chunk still recovers normally.
        """
        chunks = [
            _runon_chunk("6 Some Chapter Title — 130\n6.1 Intro — 130\n"),
            _runon_chunk("7 Proxmox VE Storage", page=9),
            _runon_chunk("141\nThe storage subsystem supports ZFS and LVM.", page=10),
        ]
        rows = _pipeline()._recovered_runon_toc_rows(chunks, PVE_SRC)
        assert rows == {6: ("Some Chapter Title", 130)}, rows

    def test_flat_runon_fixtures_recover_identically(self) -> None:
        """The historical flat fixtures recover the same rows as before."""
        rows = self._rows(
            "5.14.2 Migration Network . . . . 134 Proxmox Cluster File System "
            "(pmxcfs) 136 6.1 POSIX Compatibility . . . . 136"
        )
        assert rows == {6: ("Proxmox Cluster File System (pmxcfs)", 136)}, rows
        wrapped = self._rows(
            "6 5.7.3 Separate Cluster Network ..... 121 5.7.4 Corosync "
            "Addresses ..... 124 Proxmox Cluster File System (pmxcfs) 136 "
            "6.1 POSIX Compatibility ..... 136"
        )
        assert wrapped == {6: ("Proxmox Cluster File System (pmxcfs)", 136)}, wrapped


class TestTableListingEndToEnd:
    """The ToC-listing tier pins an unanchored chapter from table rows.

    Mirrors TestToCListingResolution.test_toc_listing_pins_missing_chapter
    with the listing rows serialized as "N Title — page"; the harness classes
    are reused (not subclassed) so their own tests do not re-run here.
    """

    @staticmethod
    def _answer(
        toc: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
        listing: Any,
        headings: list[dict[str, Any]],
    ) -> str:
        pipeline = listing._make(monkeypatch, toc, headings=headings)
        return listing._run(pipeline)

    def test_table_listing_rows_pin_missing_chapter(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from tests.unit.rag.test_pipeline import TestToCListingResolution

        listing = TestToCListingResolution()
        nums = list(range(1, 13))
        toc = [
            *listing._toc([(n, listing.TITLES[n]) for n in nums]),
            listing._listing_chunk(
                [f"{n} {listing.TITLES[n]} — {listing._printed(n)}" for n in nums]
            ),
            listing._desc_chunk(),
        ]
        with caplog.at_level(logging.DEBUG, logger="secondbrain.rag.pipeline"):
            answer = self._answer(
                toc, monkeypatch, listing, listing._anchors(list(range(1, 12)))
            )
        for n in range(1, 12):
            assert (
                f"Chapter {n} — {listing.TITLES[n]} "
                f"(approx pages {listing._anchor_page(n)}+)" in answer
            ), answer
        assert "Chapter 12 — Bayesian Deep Learning (approx pages 350+)" in answer, (
            answer
        )
        assert "approx pages 320+" not in answer, "printed page alone must not pin"
        assert "median=30" in caplog.text
        assert "Rejected chapter" not in caplog.text
        assert "Dropped phantom" not in caplog.text

    def test_table_rows_match_flat_row_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Identical fixtures with flat vs table listing rows agree."""
        from tests.unit.rag.test_pipeline import TestToCListingResolution

        listing = TestToCListingResolution()
        nums = list(range(1, 13))
        headings = listing._anchors(list(range(1, 12)))
        toc_head = [
            *listing._toc([(n, listing.TITLES[n]) for n in nums]),
            listing._desc_chunk(),
        ]
        flat = self._answer(
            [*toc_head, listing._listing_chunk(listing._listing_rows(nums))],
            monkeypatch,
            listing,
            headings,
        )
        table = self._answer(
            [
                *toc_head,
                listing._listing_chunk(
                    [f"{n} {listing.TITLES[n]} — {listing._printed(n)}" for n in nums]
                ),
            ],
            monkeypatch,
            listing,
            headings,
        )
        assert table == flat
