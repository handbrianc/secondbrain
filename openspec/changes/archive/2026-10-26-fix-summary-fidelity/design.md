# Design

## Context

See proposal.md — Why. Verified evidence anchors this design:

- **Bleed:** CRS/HA chunks at pp. 432–433 (tail of Chapter 15, range 409–433) entered the Chapter 16 window; the model's reasoning exposed it. Chapter pinning/ranging itself is heavily specified in `rag-pipeline` (pins, agreement gate) and is treated as authoritative here — the defect is in what each chapter's generation window admits, not in how ranges are derived.
- **Reasoning leak:** two divergent policies exist today. The guarded per-window sink (`rag/pipeline/_streaming.py`, `_WindowStreamSink`) never forwards reasoning; the overview/reduce path forwards every reasoning delta to the terminal callback (`rag/pipeline/_fallback_mixin.py`, `emit("", reasoning)`), which `cli/chat_helpers.py` (`_ThinkingStream`) renders as `▸ Thinking:` text inline in the answer flow. Storage is already content-only.
- **Table corruption:** chunk `01f27ef1…` in the `embeddings` collection contains the literal `5.26 minutes 99.9999`. Table structure extraction is configured in `document/docling_factory.py` (`do_table_structure`, `TableStructureOptions`, `do_cell_matching`, `pdf_table_fast_mode`); the corruption appears in the serialized chunk text, so serialization/chunking — not docling detection — is where fidelity is lost (or where it can be caught).

Constraints: the 3445-test suite must stay green; complexity ruff rules (C901/PLR0913/…) are intentionally not enabled but new code should not deepen hot-path complexity; `scripts/audit_chapter_summaries.py` is the established audit harness for chapter behavior.

## Goals / Non-Goals

**Goals:**

- Range-faithful chapter windows with a small, testable admission rule and explicit coverage-gap surfacing.
- One reasoning-display policy across all streaming paths, plus a documented display↔storage contract for answer text: live committed-prefix streaming, parity on the happy path, documented divergence on repair paths.
- Row-aligned table serialization with ingest-time degeneracy flagging.

**Non-Goals:**

- Re-deriving chapter pins/ranges (the existing rag-pipeline requirements and agreement gate stay authoritative).
- Silent repair or re-ingest of already-stored chunks; existing corrupted chunks stay until re-ingest (detection/flagging only).
- Suppressing reasoning wholesale at the provider level or changing provider APIs.
- Renaming/moving any capability spec.

## Decisions

**D1 — Window admission filter keyed on the derived range (not re-retrieval).**
Each chapter's window assembly filters candidate chunks by page-position membership in the chapter's derived range, with a one-page tolerance for chunks straddling the range boundary. Alternatives considered: (a) per-chapter semantic retrieval — rejected: adds nondeterminism and re-litigates pinning the gate already validates; (b) post-hoc answer re-check — rejected: detects nothing before the summary is emitted. Rationale: the ranges are the pipeline's own validated product; filtering at assembly is deterministic and directly kills the observed bleed. Boundary tolerance is needed because body chunks genuinely straddle opener boundaries (the existing pin rule already models this with its "minus one page" logic).

**D2 — Coverage note driven by window-composition statistics, not by parsing model reasoning.**
Compute per chapter: in-range body chunk count and foreign-range share. Emit an explicit coverage note (same style as the rangeless-chapter placeholder) when the window has no in-range body chunks or foreign content dominates (threshold calibrated on corpus fixtures). Alternative considered: scanning the model's output/reasoning for "the source is mostly about X, oddly" — rejected: untestable and model-dependent. The existing "Enumeration emits every roster chapter" placeholder precedent gives the note a natural home in the output contract.

**D3 — Reasoning display unified behind the CLI renderer's collapsed treatment; reduce path stops forwarding raw deltas.**
Remove the unconditional `emit("", reasoning)` forwarding in the overview/reduce path; instead route reasoning through the same buffered/folded treatment the guarded path implies (`_ThinkingStream` already supports buffering and collapsed emission). Add an explicit opt-in (CLI flag/config) that expands reasoning text; default is collapsed. One policy constant lives with the pipeline's streaming wiring so both paths share it. Alternatives: (a) suppress reasoning entirely everywhere — rejected: discards useful live progress signal for long thinking models; (b) keep path-dependent behavior and document it — rejected: the inconsistency is the defect. Display↔storage contract (revised 2026-10-25, user decision: live streaming wins over byte parity): the reduce path streams committed hold-releases live on the content channel while the draft forms; the stored message is the finalized overview. The two are equal byte for byte on the happy path (finalize makes no mutation); repair paths (leak-scrub hold replacement, low-temperature retry blocks, dead-stream continuation, finalize post-pass trims) may legitimately leave screen text the stored answer supersedes, and each divergence is pinned by test instead of hidden. The hold/scrub machinery keeps its `flushed` accounting exact so the leak scrubber's already-emitted-prefix comparison stays correct (the observed `depenzds`/`depends` case — root cause documented under 3.4 below). Reasoning-channel policy is unchanged.

**D4 — Row-oriented table serialization + alignment check + chunk-boundary rule.**
Serialize tables row by row (row label/header bound to its cells, e.g. one line per row: `99.999% — 5.26 minutes`), validate cell order against the source table's row order, and restrict table-internal chunk splits to row boundaries. Failures set a `table_degenerate`-style metadata flag on the affected chunk(s) and emit an ingest warning. Alternatives: (a) disable `pdf_table_fast_mode` globally — rejected: memory/latency cost on 600+-page PDFs (pdf-conversion's memory budget is a spec'd constraint) and doesn't itself guarantee serialization order; (b) detection only, no serialization change — rejected: leaves the wrong numbers retrievable and only warns after the fact. Rationale: docling already recovers table structure (cell matching exists); the fix is in how we flatten it to text.

**D5 — Ship as three independent lanes, audited by the existing harness.**
Each capability delta is independently implementable and testable; `scripts/audit_chapter_summaries.py` extends to report per-chapter window composition (bleed detection), giving a regression harness calibrated on the corpus fixtures the repo already uses for chapter-pin work.

## Risks / Trade-offs

- [Tighter admission starves chapters pinned loosely] → one-page tolerance mirrors the existing pin convention; the chapter-range agreement gate still vets the map before generation; the audit script's per-chapter composition report surfaces starvation across the corpus before release.
- [Coverage-note threshold mis-calibrated → noisy or silent misses] → calibrate on the corpus fixtures used for the pin work; the note is additive (healthy windows unchanged), so a conservative threshold degrades to status quo rather than wrong summaries.
- [Reasoning collapse hides the live-progress signal during long thinking gaps] → the collapsed one-line/fold still appears at reasoning onset (the existing spinner-lift logic already handles "thinking arrived before content"); full text remains one opt-in flag away.
- [Parity contract touches the leak-scrub/retry machinery — the most delicate streaming code] → keep the requirement to the observable contract (live committed-prefix streaming; happy-path parity; documented repair divergence); add regression tests around the hold/scrub/flush paths rather than restructuring them.
- [Table serialization changes stored text for all future ingests] → intended (that's the fix); row-oriented text may be slightly longer, marginally increasing chunk counts; verify against the ingestion cost envelope in CI.
- [Existing corrupted chunks persist until re-ingest] → documented in the proposal; the audit script can also scan stored chunk text for degenerate patterns to produce a re-ingest target list (advisory only).

## Migration Plan

1. Land lanes independently in order: document-ingestion (D4) → rag-pipeline (D1/D2) → conversational-rag (D3); each is separately revertable.
2. No schema or API migration: table flag is new chunk metadata (additive); reasoning display is CLI behavior.
3. Existing corpora: re-ingest is optional and user-driven; provide an audit-script scan listing chunks matching degenerate table patterns as re-ingest candidates.
4. Rollback: revert the lane; metadata flags on already-stored chunks are inert.

## Open Questions

- The `depenzds`→`depends` divergence mechanism between the streamed display and the stored final text (2026-10-24 run) is not yet root-caused; D3's parity requirement covers it observably, and implementation must instrument the hold/scrub/flush path to find it. If the mechanism contradicts D3's approach, stop and revisit before shipping that lane.
- Exact foreign-share/coverage thresholds and the table-degeneracy detector's tolerance are calibration values, to be fixed against corpus fixtures during implementation (they do not change the specified behavior).

## Implementation notes (apply phase, 2026-10-25)

**D1/D2 calibration values (task 2.3).** `_STRADDLE_TOLERANCE_PAGES = 1`, gated by tight (chunk-level) opener evidence — the page-level tier only widens opener-page detection and can never admit a boundary-page foreign chunk. `_FOREIGN_SHARE_NOTE_THRESHOLD = 0.5`, strict `>` (exactly-half foreign stays silent). Empty-window rule: `in_range == 0` with foreign or dropped chunks present → coverage note; a truly empty `(0,0,0)` window stays the base placeholder's territory. Calibration basis (all note-free, foreign share 0.0): user-manual (18 chapters), pve-admin-guide (20 chapters; straddles dropped ch7=3, ch16=4, ch17=7), hcd report (16 chapters); the vetoed anthology builds no windows at all.

**D2 implementation shape.** Straddle chunks are collected during the in-range pass into a per-chapter pool and appended *after* it (deferred supplement), so a boundary chunk never displaces a chapter's own content; a full window suppresses straddles. Compositions ride on the pipeline (`window_compositions`) and are reported by the audit script (new `deg`/`tbl` columns; degenerate-table scan advisory, not verdict-gating). The audit also fixed a pre-existing harness bug (query stem `"9.1"` parsed as a chapter target narrowed audits to chapter 9).

**3.4 root cause (`depenzds`→`depends`).** Two mechanisms reproduced: (1) finalize post-passes (scrub, metric prune, figure grounding, word budget, sentence trim) mutated the draft *after* it was committed to the screen; (2) raw reasoning streamed inline as content pre-3.1. Mechanism (2) is fixed by the reasoning-channel policy (3.1); mechanism (1) is the documented repair-path divergence of the restored live-streaming contract (D3 revised per user decision 2026-10-25: streaming wins over byte parity — the interim deferred-display fix was reverted because the whole answer appearing in one end-burst regressed the chat UX). The scrub-withheld-tail candidate was refuted (prefix check + hold replacement keep the scrubbed accumulation equal to what was streamed, so a confined scrub never alters already-emitted text). Residual, documented, unchanged: the legacy dead path `_map_reduce_stream → _generate_window_guarded → _low_temp_retry` appends the retry block after the committed prefix while storing only the retry (no production callers — `_map_reduce_stream` has none in `src/`); and the pre-existing all-empty multi-chapter run streams headings that the roster fallback then replaces on screen. No D3 contradiction.

**D3 consequence accepted by spec (revised 2026-10-25).** The reduce path streams committed hold-releases live again (deferred display reverted per user decision); reasoning keeps flowing on the reasoning channel for the renderer's collapsed thinking element. The stored answer is the finalized overview: display↔storage parity holds on the happy path, and repair paths (retry blocks, finalize post-pass mutations, continuation) diverge as documented under D3. In mixed multi-chapter runs, failed chapters' streamed heading blocks join the stored transcript (A′) so the transcript matches the streamed headings; a run where no chapter produced content collapses to `""` for the roster fallback.

**Lane A ingest discoveries.** With table structure OFF, docling emits table cells as a row-major plain-text stream plus a `TableItem` carrying a placeholder 1×1 grid whose export returns the whole raw table text as one cell — silently accepted, this destroyed table content (now rejected; grids reconstruct rows geometrically, vertical-overlap ≥ 0.5, one line per row joined by `" — "`). Degenerate flag (`table_degenerate`) is metadata-only, present only when True; no Qdrant schema change; existing corrupted chunks persist until re-ingest (design non-goal honored).
