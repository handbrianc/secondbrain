"""End-to-end ``_iterative_query`` behavior on the chapter-map corpus fixtures.

Three groups, mirroring the baseline-capture recipe in
``scripts/export_chapter_fixtures.py`` (same stub storage, same query shape,
same DEBUG-log capture) so pre-change baselines and these runs are
byte-comparable:

1. The compilation fixture routes through the (new) anthology path and
   streams one summary per part — EXPECTED RED until Lanes A/B land.
2. Characterization: the three single-book/HCD fixtures keep their legacy
   chapter maps and multi-chapter buckets EXACTLY as recorded in
   ``baselines.json`` — the no-regression net, green before and after.
3. Gate veto: an anthology whose openers were hidden from the detector takes
   the legacy path, whose garbage map must be vetoed into a whole-document
   overview — EXPECTED RED until the gate lands.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path
from typing import Any

import pytest

from secondbrain.rag.pipeline import RAGPipeline
from tests.unit.rag._chapter_fixture_storage import (
    ChapterFixtureStorage,
    load_fixture,
)

_COMPILATION = "knowledge-compilation"
_BOOKS = ("user-manual", "pve-admin-guide", "hcd-report")

_CANNED_ANSWER = (
    "The document presents its material as a sequence of focused sections, "
    "each developing one theme with concrete examples and practical "
    "guidance. Recurring ideas are introduced early and then applied to "
    "specific cases, so the reader can follow the argument without losing "
    "the overall thread."
)

_PART_LABELS = {"I.1", "I.2", "I.3", "I.4"} | {f"II.{n}" for n in range(1, 13)}
_PART_HEADING_RE = re.compile(r"^([IVX]+\.\d+) — (.+)$", re.MULTILINE)
_LEGACY_CHAPTER_HEADING_RE = re.compile(r"^Chapter \d+ — ", re.MULTILINE)
_PLACEHOLDER_NOTE = "No document content was retrieved"
_VETO_NOTE = "Per-chapter page mapping was unavailable"
_OPENER_TEXT_RE = re.compile(r"^[IVX]+\.\d+")


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
        if record.getMessage().startswith("Chapter page ranges for"):
            raw = record.getMessage().split(": ", 1)[1]
            self.ranges = {int(k): v for k, v in ast.literal_eval(raw).items()}


def _make_fixture_pipeline(
    storage: ChapterFixtureStorage,
    provider: Any,
) -> RAGPipeline:
    """Pipeline wired to the fixture storage exactly like the baseline script."""
    pipeline = RAGPipeline(
        searcher=_StubSearcher(storage), llm_provider=provider, top_k=8
    )
    pipeline._config.streaming_enabled = False
    return pipeline


def _run_iterative(pipeline: RAGPipeline, query: str, source: str) -> dict[str, Any]:
    return pipeline._iterative_query(
        query,
        top_k=8,
        show_sources=False,
        source_filter=source,
    )


def _fixture_source(name: str) -> str:
    return load_fixture(name)[0]["source_file"]


class TestCompilationAnthologyPath:
    """The compilation must summarize per part, never per fake chapter."""

    def test_compilation_streams_one_summary_per_part(self) -> None:
        source = _fixture_source(_COMPILATION)
        storage = ChapterFixtureStorage.from_fixture(_COMPILATION)
        pipeline = _make_fixture_pipeline(storage, _CannedProvider())

        result = _run_iterative(pipeline, "summarize knowledge_compilation.pdf", source)
        answer = result["answer"]

        headings = _PART_HEADING_RE.findall(answer)
        labels = [label for label, _title in headings]
        assert len(labels) == 16, (
            f"expected 16 part headings, got {len(labels)}: {labels}"
        )
        assert set(labels) == _PART_LABELS
        assert all(title.strip() for _label, title in headings), (
            "every part heading must carry a title"
        )

        # The legacy failure modes must be gone.
        assert not _LEGACY_CHAPTER_HEADING_RE.search(answer), (
            "no legacy 'Chapter N —' heading may appear for an anthology"
        )
        assert _PLACEHOLDER_NOTE not in answer, (
            "no part may carry the placeholder note when its pages hold body text"
        )
        assert _VETO_NOTE not in answer, (
            "a detected anthology must not fall back to the whole-document overview"
        )


class TestLegacyCharacterization:
    """No-regression net: single-book legacy maps are byte-identical.

    Runs the exact baseline-capture flow and asserts the DEBUG-logged
    ``chapter_ranges_`` and the multi-chapter bucket page lists equal the
    recorded pre-change baselines.  Must pass before AND after the change.
    """

    @pytest.mark.parametrize("fixture_name", _BOOKS)
    def test_ranges_and_buckets_match_baselines(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fixture_name: str,
    ) -> None:
        source = _fixture_source(fixture_name)
        storage = ChapterFixtureStorage.from_fixture(fixture_name)
        pipeline = _make_fixture_pipeline(storage, _NullProvider())

        # Record the bucket page lists at the same capture point the baseline
        # script used (inside _generate_multi_chapter_summary), then
        # short-circuit the prose — buckets are the baseline, not text.
        recorded: dict[str, list[int]] = {}

        def _recorder(
            chapter_keys: list[int],
            chapter_buckets: dict[int, list[dict[str, Any]]],
            ch_titles: dict[int, str],
        ) -> str:
            for ch, bucket in chapter_buckets.items():
                recorded[str(ch)] = [c.get("page_number") or 0 for c in bucket]
            return ""

        monkeypatch.setattr(pipeline, "_generate_multi_chapter_summary", _recorder)

        capture = _RangesCapture()
        plog = logging.getLogger("secondbrain.rag.pipeline._pipeline")
        plog.setLevel(logging.DEBUG)
        plog.addHandler(capture)
        try:
            _run_iterative(pipeline, f"summarize {Path(source).name}", source)
        finally:
            plog.removeHandler(capture)
            plog.setLevel(logging.NOTSET)

        baselines = _baseline_entry(fixture_name)
        expected_ranges = {int(k): tuple(v) for k, v in baselines["ranges"].items()}
        assert capture.ranges is not None, (
            "the 'Chapter page ranges' debug line must be logged"
        )
        assert capture.ranges == expected_ranges, (
            f"{fixture_name}: derived chapter ranges diverged from the "
            "recorded pre-change baseline"
        )
        assert recorded == baselines["multi"]["bucket_pages"], (
            f"{fixture_name}: multi-chapter bucket page lists diverged from "
            "the recorded pre-change baseline"
        )


def _baseline_entry(name: str) -> dict[str, Any]:
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "chapter_map"
    with (fixture_dir / "baselines.json").open(encoding="utf-8") as fh:
        return json.load(fh)[name]


class TestGateVetoEndToEnd:
    """A detector-missed anthology degrades to the whole-document overview."""

    def test_detector_miss_on_the_real_document_vetoes_the_map(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Design §2 fallback scenario: the detector fails to claim a real
        # anthology (its openers exist but do not match the opener pattern).
        # The legacy path then derives its known-garbage map; the agreement
        # gate — comparing against the RAW N.1 evidence pins — must veto it
        # (calibrated: score 0.25-0.30, well under the 0.7 threshold) and the
        # pipeline must answer with a whole-document overview instead.
        source = _fixture_source(_COMPILATION)
        storage = ChapterFixtureStorage.from_fixture(_COMPILATION)
        pipeline = _make_fixture_pipeline(storage, _CannedProvider())
        monkeypatch.setattr(
            RAGPipeline,
            "_detect_anthology_parts",
            staticmethod(lambda heading_chunks, source: None),
        )

        result = _run_iterative(pipeline, "summarize knowledge_compilation.pdf", source)
        answer = result["answer"]

        assert _VETO_NOTE in answer, (
            "the vetoed legacy map must fall back to a whole-document "
            "overview that says per-chapter page mapping was unavailable"
        )
        assert not _PART_HEADING_RE.search(answer), (
            "a detector-missed anthology must not emit per-part headings"
        )
        assert not _LEGACY_CHAPTER_HEADING_RE.search(answer), (
            "the vetoed garbage map must not surface per-chapter entries"
        )
        assert _PLACEHOLDER_NOTE not in answer, (
            "the whole-document overview must summarize, not placeholder"
        )

    def test_hidden_openers_veto_the_garbage_map(self) -> None:
        # Build a modified compilation fixture IN-TEST: the 16 part-opener
        # headings keep their element_type but flip chunk_role to "body", so
        # the detector's heading stream misses them and the legacy path runs
        # on the anthology — producing exactly the garbage map the change
        # exists to defend against.  The agreement gate must veto it.
        chunks = load_fixture(_COMPILATION)
        opener_chunks = [
            c
            for c in chunks
            if c.get("chunk_role") == "heading"
            and _OPENER_TEXT_RE.match(c.get("chunk_text", ""))
        ]
        assert len(opener_chunks) == 16, "precondition: 16 openers in the fixture"

        mutated: list[dict[str, Any]] = []
        for chunk in chunks:
            clone = dict(chunk)
            if clone.get("chunk_role") == "heading" and _OPENER_TEXT_RE.match(
                clone.get("chunk_text", "")
            ):
                clone["chunk_role"] = "body"
            mutated.append(clone)

        source = mutated[0]["source_file"]
        storage = ChapterFixtureStorage(mutated)
        pipeline = _make_fixture_pipeline(storage, _CannedProvider())

        result = _run_iterative(pipeline, "summarize knowledge_compilation.pdf", source)
        answer = result["answer"]

        assert _VETO_NOTE in answer, (
            "the vetoed legacy map must fall back to a whole-document "
            "overview that says per-chapter page mapping was unavailable"
        )
        assert not _PART_HEADING_RE.search(answer), (
            "a detector-missed anthology must not emit per-part headings"
        )
        assert not _LEGACY_CHAPTER_HEADING_RE.search(answer), (
            "the vetoed garbage map must not surface per-chapter entries"
        )
