"""Chapter-range agreement gate contract: ``_chapter_range_gate``.

The gate (add-anthology-aware-chapter-summarization design §3) cross-checks
the legacy path's derived ``chapter_ranges_`` against the provisional
first-section (``N.1``) heading evidence pins: a chapter agrees when its final
range start stays within 2 pages of its pin.  Score = agreeing / compared;
the gate vetoes (returns False) only when >= 4 chapters are comparable AND
score < 0.7.  Absence of evidence never vetoes.

Calibration values come from ``tests/fixtures/chapter_map/baselines.json``
(UserManual 1.00, PVE 1.00, compilation 0.25, HCD report no evidence).

These tests are EXPECTED RED (AttributeError) until Lane A/B land
``_chapter_range_gate``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "chapter_map"


class _StubSearcher:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _CannedProvider:
    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        return (
            "The document presents its material as a sequence of focused "
            "sections, each developing one theme with concrete examples and "
            "practical guidance. Recurring ideas are introduced early and "
            "then applied to specific cases, so the reader can follow the "
            "argument without losing the overall thread."
        )


def _make_pipeline() -> RAGPipeline:
    return RAGPipeline(
        searcher=_StubSearcher(None), llm_provider=_CannedProvider(), top_k=5
    )


def _baselines() -> dict[str, Any]:
    with (_FIXTURE_DIR / "baselines.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def _baseline_maps(name: str) -> tuple[dict[int, tuple[int, int]], dict[int, int], str]:
    """Int-keyed (ranges, evidence pins, source) from a baselines entry."""
    entry = _baselines()[name]
    ranges = {int(k): tuple(v) for k, v in entry["ranges"].items()}
    pins = {int(k): int(v) for k, v in entry["evidence_pins"].items()}
    return ranges, pins, entry["source_file"]


def _synthetic_map(
    pins: dict[int, int], diverged: dict[int, int]
) -> dict[int, tuple[int, int]]:
    """Ranges whose start sits *diverged[ch]* pages beside its pin (end +8)."""
    return {
        ch: (pin + diverged.get(ch, 0), pin + diverged.get(ch, 0) + 8)
        for ch, pin in pins.items()
    }


class TestFixtureBaselines:
    """Gate verdicts on the recorded pre-change corpus maps."""

    @pytest.mark.parametrize(
        ("fixture_name", "expected"),
        [
            ("user-manual", True),  # score 1.00, 18/18 within ±2
            ("pve-admin-guide", True),  # score 1.00, 19/19 within ±2
            ("knowledge-compilation", False),  # score 0.25, 2/8 — garbage map
            ("hcd-report", True),  # no N.1 evidence pins → gate must not run
        ],
    )
    def test_gate_on_recorded_baselines(
        self, fixture_name: str, expected: bool
    ) -> None:
        ranges, pins, source = _baseline_maps(fixture_name)
        gate = _make_pipeline()._chapter_range_gate(ranges, pins, source)
        assert gate is expected, (
            f"{fixture_name}: gate verdict must be {expected} "
            f"(score {_baselines()[fixture_name].get('gate_divergence')})"
        )


class TestGateBoundaries:
    """Threshold and evidence-floor boundaries on synthetic maps."""

    def test_below_evidence_floor_passes_even_at_zero_score(self) -> None:
        # Only 3 comparable chapters, all wildly divergent: the gate runs on
        # >= 4 comparable chapters, so it must not veto regardless of score.
        pins = {1: 1, 2: 2, 3: 3}
        ranges = _synthetic_map(pins, diverged={1: 100, 2: 100, 3: 100})
        assert _make_pipeline()._chapter_range_gate(ranges, pins, "book.pdf") is True

    def test_no_evidence_pins_passes(self) -> None:
        # Populated ranges but zero N.1 pins (the HCD-report shape): nothing
        # to disagree with → legacy path unchanged.
        ranges = {1: (10, 20), 2: (21, 30), 3: (31, 40), 4: (41, 50)}
        assert _make_pipeline()._chapter_range_gate(ranges, {}, "book.pdf") is True

    def test_score_exactly_at_threshold_passes(self) -> None:
        # 10 comparable chapters, exactly 7 agree → 0.7 is not below the
        # threshold ("veto if score < 0.7").
        pins = {ch: ch * 10 for ch in range(1, 11)}
        ranges = _synthetic_map(pins, diverged={1: 10, 2: 10, 3: 10})
        assert _make_pipeline()._chapter_range_gate(ranges, pins, "book.pdf") is True

    def test_score_just_below_threshold_vetoes(self) -> None:
        # 10 comparable chapters, 6 agree → 0.6 < 0.7 → veto.
        pins = {ch: ch * 10 for ch in range(1, 11)}
        ranges = _synthetic_map(pins, diverged={1: 10, 2: 10, 3: 10, 4: 10})
        assert _make_pipeline()._chapter_range_gate(ranges, pins, "book.pdf") is False

    def test_single_off_by_three_chapter_in_eight_still_passes(self) -> None:
        # One chapter pinned 3 pages off in an 8-chapter map: 7/8 = 0.875
        # stays above the threshold.
        pins = {ch: ch * 10 for ch in range(1, 9)}
        ranges = _synthetic_map(pins, diverged={4: 3})
        assert _make_pipeline()._chapter_range_gate(ranges, pins, "book.pdf") is True

    def test_three_of_eight_off_by_three_vetoes(self) -> None:
        # 5/8 = 0.625 < 0.7 → veto.
        pins = {ch: ch * 10 for ch in range(1, 9)}
        ranges = _synthetic_map(pins, diverged={2: 3, 5: 3, 7: 3})
        assert _make_pipeline()._chapter_range_gate(ranges, pins, "book.pdf") is False

    def test_divergence_is_measured_in_both_directions(self) -> None:
        # ±2 agrees, ±3 disagrees — the tolerance is symmetric.
        pins = {ch: ch * 10 for ch in range(1, 5)}
        within = _synthetic_map(pins, diverged={1: -2, 2: 2, 3: -1, 4: 1})
        assert _make_pipeline()._chapter_range_gate(within, pins, "book.pdf") is True
        beyond = _synthetic_map(pins, diverged={1: -3, 2: 3, 3: -1, 4: 1})
        # 2/4 = 0.5 < 0.7 with 4 comparable chapters → veto.
        assert _make_pipeline()._chapter_range_gate(beyond, pins, "book.pdf") is False
