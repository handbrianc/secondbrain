#!/usr/bin/env python3
"""Audit whether every ingested source would be summarized by chapter.

Read-only, agent-runnable harness: it drives the REAL chapter detection +
bucket-fill path (``RAGPipeline._iterative_query``) against the live Qdrant
collection with a stubbed LLM, so bucket filling exercises the production
code while generation is a no-op. Per source it records the chapter count,
heading-title anchors, each chapter bucket's first page, empty buckets,
monotonicity, and a PASS/FAIL verdict.

PASS rule: ``chapters_detected > 0`` AND zero empty buckets AND bucket first
pages monotonic non-decreasing AND every first page >= 10. (Zero detected
chapters is a FAIL, not a vacuous pass.)

Usage::

    python scripts/audit_chapter_summaries.py [options]

Preconditions (exit code 2 otherwise):

- Qdrant reachable at ``$SECONDBRAIN_QDRANT_URL`` (default
  ``http://localhost:6333``)
- collection ``$SECONDBRAIN_QDRANT_COLLECTION`` (default ``embeddings``)
  non-empty (> 0 points)
- at least one source with body chunks discovered (or provided via
  ``--manifest``)

Exit codes: 0 = all audited sources PASS, 1 = at least one source FAILs
(the audit verdict, not a script error), 2 = precondition failure.

Sources are discovered dynamically from the collection (distinct
``source_file`` values that have body chunks); no book names are hard-coded.
The script never writes to Qdrant and is not imported by product code.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
import traceback
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from secondbrain.rag.interfaces import StreamingCallback
    from secondbrain.rag.pipeline import RAGPipeline
    from secondbrain.search import Searcher
    from secondbrain.storage.qdrant import QdrantVectorStorage

REPO = Path(__file__).resolve().parents[1]
if (REPO / "src" / "secondbrain").is_dir():
    sys.path.insert(0, str(REPO / "src"))


class BookTimeoutError(Exception):
    """Raised by the SIGALRM handler when a source exceeds its time budget."""


def _on_alarm(signum: int, frame: Any) -> None:
    """SIGALRM handler: abort the in-flight audit with BookTimeoutError."""
    raise BookTimeoutError()


class StubProvider:
    """LLM stub: chapter buckets still fill; generation itself is a no-op.

    Implements the full ``LocalLLMProvider`` protocol so the pipeline accepts
    it, while every generation entry point produces empty output.
    """

    @property
    def model(self) -> str:
        """Model name reported to the pipeline."""
        return "stub"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Return an empty summary; bucket filling never depends on text."""
        return ""

    async def agenerate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async no-op: return an empty summary."""
        return ""

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Emit nothing; return the empty response text."""
        return ""

    async def stream_chat_async(
        self,
        messages: list[dict[str, str]],
        on_chunk: StreamingCallback,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Async no-op: emit nothing, return the empty response text."""
        return ""

    def health_check(self) -> bool:
        """Report the stub as always available."""
        return True


def _manifest_file(value: str) -> Path:
    """Argparse type: require an existing manifest file (exit 2 otherwise)."""
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"manifest file not found: {value}")
    return path


def _positive_float(value: str) -> float:
    """Argparse type: a timeout in seconds that must be > 0."""
    try:
        secs = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid timeout: {value!r}") from None
    if secs <= 0:
        raise argparse.ArgumentTypeError("timeout must be > 0 seconds")
    return secs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="audit_chapter_summaries",
        description=(
            "Audit whether every ingested source would be summarized by "
            "chapter, by driving the real RAG pipeline with a stubbed LLM."
        ),
        epilog=(
            "Preconditions: Qdrant reachable at $SECONDBRAIN_QDRANT_URL "
            "(default http://localhost:6333) with a non-empty collection "
            "$SECONDBRAIN_QDRANT_COLLECTION (default 'embeddings'); exits 2 "
            "if unreachable, empty, or no sources with body chunks are found."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SUBSTRING",
        help=(
            "only audit sources whose path contains this substring "
            "(case-insensitive); repeatable, sources matching ANY filter "
            "are audited"
        ),
    )
    parser.add_argument(
        "--manifest",
        type=_manifest_file,
        default=None,
        metavar="FILE",
        help=(
            "audit exactly the source paths listed one-per-line in FILE, "
            "overriding dynamic discovery"
        ),
    )
    parser.add_argument(
        "--evidence-out",
        default=None,
        metavar="PATH",
        help="write the JSON evidence report to PATH (default: print to stdout)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=120.0,
        metavar="SECONDS",
        help="per-source time budget before the run is recorded as a failure (default: 120)",
    )
    return parser.parse_args(argv)


def _fatal(message: str) -> NoReturn:
    """Print a fatal precondition error to the real stderr and exit 2."""
    print(f"FATAL: {message}", file=sys.__stderr__)
    raise SystemExit(2)


def _import_secondbrain() -> tuple[
    type[RAGPipeline], type[Searcher], type[QdrantVectorStorage]
]:
    """Import the product pipeline lazily, after stderr has been silenced."""
    try:
        from secondbrain.rag.pipeline import RAGPipeline
        from secondbrain.search import Searcher
        from secondbrain.storage.qdrant import QdrantVectorStorage
    except Exception as exc:
        _fatal(f"cannot import secondbrain from {REPO}: {exc}")
    return RAGPipeline, Searcher, QdrantVectorStorage


def check_preconditions(st: QdrantVectorStorage) -> int:
    """Return the collection point count; exit 2 unless Qdrant is usable."""
    try:
        info = st._get_client().count(collection_name=st.collection_name, exact=True)
        points = int(info.count)
    except Exception as exc:
        _fatal(
            f"Qdrant not reachable at {st.url} (collection "
            f"{st.collection_name!r}): {exc}. Run `secondbrain start --wait` first."
        )
    if points == 0:
        _fatal(
            f"collection {st.collection_name!r} at {st.url} has 0 points; "
            "refusing to audit empty state."
        )
    return points


def discover_sources(st: QdrantVectorStorage, filters: list[str]) -> list[str]:
    """Distinct sources with body chunks, optionally narrowed by substrings.

    Dynamic discovery only: distinct ``source_file`` values in the collection
    that own at least one body chunk. *filters* are case-insensitive
    substrings; a source matching ANY filter is kept.
    """
    sources = [
        src
        for src in st.list_source_files()
        if st.count_chunks(source_file=src, chunk_role="body") > 0
    ]
    if filters:
        needles = [f.lower() for f in filters]
        sources = [src for src in sources if any(n in src.lower() for n in needles)]
    return sorted(sources)


def load_manifest(path: Path) -> list[str]:
    """Read one source path per line; blank lines ignored; result deduped."""
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        _fatal(f"cannot read manifest {path}: {exc}")
    return sorted({line.strip() for line in lines if line.strip()})


def audit_source(
    pipeline_cls: type[RAGPipeline],
    searcher_cls: type[Searcher],
    st: QdrantVectorStorage,
    source: str,
    timeout_s: float,
) -> dict[str, Any]:
    """Run the real detection + bucket-fill path for one source.

    Monkeypatches ``_generate_multi_chapter_summary`` to record each chapter
    bucket's first page (restored in ``finally``), instruments
    ``_heading_title_anchors`` for anchor stats, and guards the run with a
    per-source SIGALRM timeout recorded as a failure.
    """
    name = Path(source).stem
    rec: dict[str, Any] = {
        "source": source,
        "chapters_detected": 0,
        "anchors": {},
        "bucket_first_pages": {},
        "empty": [],
        "monotonic": False,
        "pass": False,
        "error": None,
        "secs": 0.0,
    }
    started = time.monotonic()

    # --- Structural anchors (bare instance + storage only, no LLM) ---
    try:
        probe: Any = pipeline_cls.__new__(pipeline_cls)
        probe._searcher = types.SimpleNamespace(storage=st)
        probe._llm_provider = None
        structure = probe._probe_document_structure(top_k=400, source_filter=source)
        entries, _good_nums, _appendix = probe._derive_chapter_numbers(structure)
        full = [e for e in entries if e[1] == source]
        desc = probe._front_matter_desc_pages(structure)
        heading: Any = list(
            st.find_structural_chunks(chunk_roles=["heading"], source_prefix=source)
        )
        anchors = pipeline_cls._heading_title_anchors(
            full, source, heading, blocked_pages=desc
        )
        rec["anchors"] = {
            str(n): anchors.get(n) for n, _s, _t in sorted(full, key=lambda e: e[0])
        }
    except Exception as exc:
        rec["error"] = f"structure-probe: {type(exc).__name__}: {exc}"

    # --- Real bucket-fill path with stubbed LLM + per-source timeout ---
    report: dict[int, int | None] = {}

    def logged_multi(
        self: RAGPipeline,
        chapter_keys: Any,
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: Any,
    ) -> str:
        for k in chapter_keys:
            bucket = chapter_buckets.get(k, [])
            report[int(k)] = min(
                (int(c.get("page_number") or 0) for c in bucket), default=None
            )
        return ""

    orig_multi = pipeline_cls._generate_multi_chapter_summary
    pipeline_cls._generate_multi_chapter_summary = logged_multi
    try:
        q = pipeline_cls(searcher_cls(), StubProvider())
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout_s)
        try:
            q._iterative_query(
                f"summarize by chapter {name}",
                top_k=12,
                show_sources=False,
                source_filter=source,
            )
        except BookTimeoutError:
            rec["error"] = f"timeout: exceeded {timeout_s:g}s"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    except Exception as exc:
        rec["error"] = f"iterative-query: {type(exc).__name__}: {exc}"
    finally:
        pipeline_cls._generate_multi_chapter_summary = orig_multi

    # --- Verdict ---
    chapters = sorted(report)
    first_pages = [report[k] for k in chapters]
    rec["chapters_detected"] = len(chapters)
    rec["bucket_first_pages"] = {str(k): report[k] for k in chapters}
    rec["empty"] = [str(k) for k in chapters if report[k] is None]
    if not chapters or any(v is None for v in first_pages):
        rec["monotonic"] = False
    else:
        pages = [v for v in first_pages if v is not None]
        rec["monotonic"] = len(pages) == len(first_pages) and all(
            pages[i] <= pages[i + 1] for i in range(len(pages) - 1)
        )
    rec["pass"] = bool(
        chapters
        and not rec["empty"]
        and rec["monotonic"]
        and all(v is not None and v >= 10 for v in first_pages)
    )
    if rec["error"] is None and not chapters:
        rec["error"] = "pipeline fallback: zero chapters detected"
    rec["secs"] = round(time.monotonic() - started, 1)
    return rec


def failing_chapters(rec: dict[str, Any]) -> list[str]:
    """Chapters that are empty, out of order, or pinned before page 10."""
    bad: set[str] = set(rec["empty"])
    ordered = sorted(rec["bucket_first_pages"], key=int)
    running_max: int | None = None
    for ch in ordered:
        page = rec["bucket_first_pages"][ch]
        if page is None:
            bad.add(ch)
            continue
        if page < 10:
            bad.add(ch)
        if running_max is not None and page < running_max:
            bad.add(ch)
        running_max = page if running_max is None else max(running_max, page)
    return sorted(bad, key=int)


def _print_table(results: list[dict[str, Any]]) -> None:
    """Print the compact per-source verdict table to stdout."""
    print(
        f"{'RESULT':<4} {'source':<55} {'ch':>3} {'emp':>3} {'mono':<5} {'secs':>5}  failing"
    )
    for r in results:
        name = Path(r["source"]).stem
        status = "PASS" if r["pass"] else "FAIL"
        fails = "" if r["pass"] else " ".join(failing_chapters(r))
        suffix = f" ({r['error']})" if r["error"] else ""
        print(
            f"{status:<4} {name:<55} {r['chapters_detected']:>3} "
            f"{len(r['empty']):>3} {r['monotonic']!s:<5} {r['secs']:>5}  {fails}{suffix}"
        )


def main(argv: list[str] | None = None) -> int:
    """Run the audit; return the process exit code (0/1/2)."""
    args = parse_args(argv)

    # Silence library noise BEFORE heavy imports: stderr -> devnull so stdout
    # stays a clean table. Fatal errors go to the real stderr (sys.__stderr__).
    sys.stderr = Path(os.devnull).open("w")  # noqa: SIM115 - process-long by design
    logging.disable(logging.CRITICAL)

    pipeline_cls, searcher_cls, storage_cls = _import_secondbrain()

    st = storage_cls()
    points = check_preconditions(st)
    print(f"qdrant={st.url} collection={st.collection_name} points={points}")

    if args.manifest is not None:
        sources = load_manifest(args.manifest)
        print(f"sources_from_manifest={len(sources)} file={args.manifest}")
    else:
        sources = discover_sources(st, args.source)
        print(f"sources_discovered={len(sources)}")
    if not sources:
        _fatal(
            "zero sources to audit; check --source filters/--manifest, or "
            "ingest documents first"
        )

    results = [
        audit_source(pipeline_cls, searcher_cls, st, src, args.timeout)
        for src in sources
    ]
    n_pass = sum(1 for r in results if r["pass"])

    print()
    _print_table(results)

    payload = {
        "captured_at": datetime.now(UTC).isoformat(),
        "kind": "chapter-summary-audit",
        "worktree": str(REPO),
        "qdrant_url": st.url,
        "collection": st.collection_name,
        "qdrant_points": points,
        "n_sources": len(sources),
        "n_pass": n_pass,
        "n_fail": len(results) - n_pass,
        "timeout_s": args.timeout,
        "filters": args.source,
        "manifest": str(args.manifest) if args.manifest is not None else None,
        "pass_rule": (
            "chapters_detected > 0 AND zero empty buckets AND bucket first "
            "pages monotonic non-decreasing AND every first page >= 10"
        ),
        "results": results,
    }
    print()
    print(
        f"RESULT: {'PASS' if n_pass == len(results) else 'FAIL'} "
        f"({n_pass}/{len(results)} sources passing)"
    )
    if args.evidence_out is not None:
        out = Path(args.evidence_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"evidence={out}")
    else:
        # JSON last on stdout: everything up to the first '{' is the table.
        print(json.dumps(payload, indent=2))
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(file=sys.__stderr__)
        sys.exit(1)
