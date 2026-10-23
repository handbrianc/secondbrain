#!/usr/bin/env python3
"""Export chapter-map fixtures from the live store and capture baselines.

One-off capture utility backing the ``add-anthology-aware-chapter-summarization``
OpenSpec change (tasks 1-2).  Two phases, selectable independently:

``--export``
    Scroll every chunk for the corpus sources out of Qdrant and write one
    JSON fixture per source under ``tests/fixtures/chapter_map/``.  Body
    chunk text is truncated to 600 chars (the chapter-map scans read at most
    the first 150); headings keep their full text so title matching is
    faithful.

``--baselines``
    Run the CURRENT pipeline's chapter enumeration against each exported
    fixture (via ``tests/unit/rag/_chapter_fixture_storage.py``) with stubbed
    retrieval and LLM, and record the derived chapter ranges, buckets and a
    heading-agreement score per document into ``baselines.json``.  Must be
    captured BEFORE any pipeline code change: it is the characterization
    reference the tests compare against after the change.

Usage (repo root, project venv)::

    ./scripts/export_chapter_fixtures.py --export
    ./scripts/export_chapter_fixtures.py --baselines
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "unit" / "rag"))

from _chapter_fixture_storage import ChapterFixtureStorage, load_fixture  # noqa: E402

from secondbrain.rag.pipeline import RAGPipeline  # noqa: E402

SOURCES: dict[str, str] = {
    "user-manual": "/home/bchand/UserManual.pdf",
    "pve-admin-guide": "/home/bchand/pve-admin-guide-9.1.pdf",
    "hcd-report": "/data/workspace/uploads/hcd_best_practices_report.pdf",
    "knowledge-compilation": (
        "/data/workspace/uploads/Consolidated_Knowledge_Compilation.pdf"
    ),
}
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "chapter_map"
BODY_TEXT_TRIM = 600
EXPORT_FIELDS = (
    "chunk_text",
    "page_number",
    "page_pos",
    "chunk_role",
    "element_type",
    "source_file",
)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def export_fixtures(url: str, collection: str) -> None:
    """Scroll each corpus source out of the live store into a fixture JSON."""
    from qdrant_client import QdrantClient
    from qdrant_client import models as qmodels

    client = QdrantClient(url=url, timeout=120)
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        chunks: list[dict[str, Any]] = []
        offset = None
        flt = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="source_file", match=qmodels.MatchValue(value=source)
                )
            ]
        )
        while True:
            points, offset = client.scroll(
                collection_name=collection,
                scroll_filter=flt,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                record = {field: payload.get(field) for field in EXPORT_FIELDS}
                if (
                    record["chunk_role"] == "body"
                    and isinstance(record["chunk_text"], str)
                    and len(record["chunk_text"]) > BODY_TEXT_TRIM
                ):
                    record["chunk_text"] = record["chunk_text"][:BODY_TEXT_TRIM]
                chunks.append(record)
            if offset is None or not points:
                break
        # The scroll loop above is offset-driven and processes each batch
        # as it arrives.
        out = FIXTURE_DIR / f"{name}.json"
        out.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
        pages = [c.get("page_number") or 0 for c in chunks]
        print(
            f"exported {name}: {len(chunks)} chunks, "
            f"pages {min(pages) if pages else '-'}..{max(pages) if pages else '-'}, "
            f"{out.stat().st_size / 1e6:.1f} MB"
        )


# --------------------------------------------------------------------------
# Baseline capture
# --------------------------------------------------------------------------


class _RangesCapture(logging.Handler):
    """Capture the pipeline's own "Chapter page ranges" debug line."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.ranges: dict[int, tuple[int, int]] | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if record.getMessage().startswith("Chapter page ranges for"):
            raw = record.getMessage().split(": ", 1)[1]
            self.ranges = {int(k): v for k, v in ast.literal_eval(raw).items()}


class _StubSearcher:
    def __init__(self, storage: ChapterFixtureStorage) -> None:
        self.storage = storage

    def search(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []


class _StubLLM:
    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 512
    ) -> str:
        return ""


def _evidence_divergence(
    ranges: dict[int, tuple[int, int]],
    evidence_pins: dict[int, int],
) -> dict[str, Any] | None:
    """Score the design.md §3 gate metric: final start vs N.1 evidence pin."""
    divs: dict[str, int] = {}
    within = 0
    for ch, (start, _end) in ranges.items():
        pin = evidence_pins.get(ch)
        if pin is None or start <= 0:
            continue
        div = start - pin
        divs[str(ch)] = div
        if abs(div) <= 2:
            within += 1
    compared = len(divs)
    if compared == 0:
        return None
    return {
        "score": round(within / compared, 3),
        "within": within,
        "compared": compared,
        "divs": divs,
    }


def capture_baselines() -> None:
    """Run the current pipeline per fixture and record the baseline maps."""
    baselines: dict[str, Any] = {}
    for name, source in SOURCES.items():
        fixture_chunks = load_fixture(name)
        storage = ChapterFixtureStorage(fixture_chunks)
        pipeline = RAGPipeline(_StubSearcher(storage), _StubLLM(), top_k=8)
        pipeline._config.streaming_enabled = False

        capture = _RangesCapture()
        plog = logging.getLogger("secondbrain.rag.pipeline._pipeline")
        plog.setLevel(logging.DEBUG)
        plog.addHandler(capture)

        evidence_pins: dict[int, int] = {}
        multi_record: dict[str, Any] = {}
        single_record: dict[str, Any] = {}

        orig_shp = pipeline._section_heading_pins

        def wrapped_shp(
            chapters: list[tuple[int, str, str]],
            src: str,
            heading_chunks: list[dict[str, Any]],
            boiler_pages: set[int] | None = None,
            body_chunks_by_page: dict[int, list[dict[str, Any]]] | None = None,
            _orig: Any = orig_shp,
            _pins: dict[int, int] = evidence_pins,
        ) -> dict[int, int]:
            out = _orig(
                chapters,
                src,
                heading_chunks,
                boiler_pages=boiler_pages,
                body_chunks_by_page=body_chunks_by_page,
            )
            _pins.update(out)
            return out

        pipeline._section_heading_pins = wrapped_shp

        def wrapped_multi(
            chapter_keys: list[int],
            chapter_buckets: dict[int, list[dict[str, Any]]],
            ch_titles: dict[int, str],
            _record: dict[str, Any] = multi_record,
        ) -> str:
            _record["keys"] = list(chapter_keys)
            _record["bucket_pages"] = {
                ch: [c.get("page_number") or 0 for c in bucket]
                for ch, bucket in chapter_buckets.items()
            }
            _record["titles"] = dict(ch_titles)
            return ""  # short-circuit: buckets are the baseline, not prose

        pipeline._generate_multi_chapter_summary = wrapped_multi

        def wrapped_single(
            *args: Any,
            _record: dict[str, Any] = single_record,
            **kwargs: Any,
        ) -> str:
            _record["called"] = True
            return ""

        pipeline._generate_single_chapter_summary = wrapped_single

        pipeline._iterative_query(
            f"summarize {Path(source).name}",
            top_k=8,
            show_sources=False,
            source_filter=source,
        )
        plog.removeHandler(capture)
        plog.setLevel(logging.NOTSET)

        pages = [c.get("page_number") or 0 for c in fixture_chunks]
        entry: dict[str, Any] = {
            "source_file": source,
            "n_chunks": len(fixture_chunks),
            "pages": [min(pages), max(pages)] if pages else [],
            "ranges": {str(k): list(v) for k, v in (capture.ranges or {}).items()},
            "evidence_pins": {str(k): v for k, v in sorted(evidence_pins.items())},
            "multi": multi_record or None,
            "single_chapter_called": bool(single_record.get("called")),
        }
        if capture.ranges:
            entry["gate_divergence"] = _evidence_divergence(
                capture.ranges, evidence_pins
            )
        baselines[name] = entry
        print(
            f"baseline {name}: ranges={entry['ranges']} gate={entry.get('gate_divergence')}"
        )

    out = FIXTURE_DIR / "baselines.json"
    out.write_text(
        json.dumps(baselines, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"wrote {out}")


def main() -> None:
    """CLI entry point: export fixtures and/or capture baselines."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export", action="store_true", help="export fixtures from the live store"
    )
    parser.add_argument(
        "--baselines", action="store_true", help="capture pre-change baselines"
    )
    parser.add_argument("--url", default="http://localhost:6333")
    parser.add_argument("--collection", default="embeddings")
    args = parser.parse_args()
    if not (args.export or args.baselines):
        parser.error("nothing to do: pass --export and/or --baselines")
    if args.export:
        export_fixtures(args.url, args.collection)
    if args.baselines:
        capture_baselines()


if __name__ == "__main__":
    main()
