# Anthology-Aware Chapter Summarization — Proposal

## Why

Whole-document chapter summarization is broken for anthology-style documents —
compilations that concatenate several reports, each restarting its own section
numbering at 1. The verified case: `Consolidated_Knowledge_Compilation.pdf`
(120 pages, 16 sub-reports `I.1–I.4` and `II.1–II.12`, front-matter overview +
master topic index on pp. 1–3). Asked to "summarize" it, the pipeline produced
10 placeholder chapters ("No document content was retrieved…") and 11 summaries
of the *wrong pages* (e.g. "chapter 5" summarized the front-matter
cross-reference matrix; "chapter 7" summarized report I.2's opening sections —
the model itself protested that the supplied pages were not the chapter).

Forensic replay against the live store traced every defect to one root cause:
`RAGPipeline._iterative_query` builds a single global "chapter N → page range"
map and assumes one monotone chapter sequence — the shape of the single books
its heuristics were tuned on (VirtualBox UserManual, PVE admin guide). In an
anthology that assumption is false by construction, so every stage misfires:

- `_derive_chapter_numbers` merges section numbers from different sub-reports
  into one fake 1..21 roster (ch 1–8, 11, 12 titled from report I.1; ch 9, 10,
  13–15 from I.2; ch 16–21 from I.3; the twelve II.x volumes invisible).
- The section-number/loose-digit scans pin chapters from *any* text that
  matches the number: ch5@p1 and ch6@p2 from the front-matter cross-reference
  matrix ("I.1 §§2.2, 7 · II.11 (BDD)…"), ch7@p13 from a bare "7" in report
  I.2's prose, ch21@p52 from an availability-SLA table value "21.9 min".
- `_select_monotone_pins` resolves conflicts by largest *numerically*
  consistent subset — it dropped the one correct pin (ch12@p12, I.1 §12
  "Sources and Further Reading") because ch12 must numerically sit above
  ch9@p18, and interpolation then pinned ch12@p19 / ch16@p26 between wrong
  neighbors.
- The duplicate-first-word title dedup deleted three pins the monotone pass
  had kept correctly (ch19@p34, ch20@p35, ch21@p52 — "Agentic…", "Bridging…",
  "Source Register…" collide with ch17/ch13/ch15).
- Resulting ranges span sub-report boundaries (ch6 = 2..12 = front matter +
  all of report I.1; ch18 = 33..10⁶ = I.3 §18 plus all twelve II volumes).

Patching restart-handling into the existing resolver is not a fix: the resolver's
model (chapter N globally unique, pages monotone in N) cannot represent
restarts, and the heuristic stack is already at its edge (see the PVE ch6 /
VirtualBox ch19 rescues in the code comments). The fix must *route around* the
legacy machinery for anthology-shaped documents and add a validation gate
behind it so unknown shapes degrade honestly instead of emitting confident
wrong-page summaries.

## What Changes

- **Anthology detection (new, additive):** a structure-shape detector runs
  before any roster/pinning work. It claims a document only on multiple
  independent signals: ≥3 part-opener headings (`I.1 · …`, `II.1 · Volume 0 —
  …`, `Part N` shapes) AND ≥2 parts whose first numbered section restarts at
  `1`. Single-book documents (chapter banners, straight 1..N numbering) cannot
  satisfy the guard and take the legacy path unchanged.
- **Per-part chapter maps (new path):** for an anthology, part boundaries come
  from the opener-heading pages; within each part, sections are rostered and
  pinned from that part's own heading-role chunks (per-part numbering
  namespaces are collision-free). Broad-coverage summarization emits one
  summary per part ("I.1 — From Vague Requirements to Well-Defined Epics
  (pp. 3–13)") via the existing bounded-window summarizer.
- **Chapter-range agreement gate (defense in depth, all documents):** after the
  legacy path derives `chapter_ranges_`, the map is cross-checked against
  heading-role evidence (does each range contain a heading chunk matching its
  roster title or leading number?). Below the calibrated threshold the pipeline
  refuses per-chapter enumeration and falls back to a whole-document overview
  instead of confident wrong-page summaries. Known-good books (UserManual,
  PVE) pass the gate — verified on corpus fixtures before merge.
- **Roster titles preserve quoted phrases (rider):** the bare-chapter title
  regex excludes `"`, truncating titles at embedded quotes ("First Principles:
  What" instead of `First Principles: What "Well-Defined" Actually Means`).
  The capture class is extended so quoted phrases survive.
- **Characterization fixtures from the live corpus:** chunk fixtures for the
  indexed corpus documents (VirtualBox UserManual, PVE admin guide, HCD report,
  the compilation) plus recorded pre-change chapter maps, so tests assert the
  single-book outputs are byte-identical before/after and the compilation maps
  per-part.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **rag-pipeline** — adds anthology detection and per-part chapter maps for
  broad-coverage enumeration; adds the chapter-range agreement gate with
  whole-document fallback; roster titles preserve quoted phrases.

## Dependencies

- None (self-contained change to the RAG pipeline's enumeration path).

## Impact

**Code:**

- `src/secondbrain/rag/pipeline/_structure_mixin.py` — anthology shape
  detector; per-part map builder; bare-title regex quote fix.
- `src/secondbrain/rag/pipeline/_pipeline.py` — early anthology branch in
  `_iterative_query`; agreement gate after range derivation.
- `src/secondbrain/rag/pipeline/_fallback_mixin.py` — per-part summary
  generator and whole-document overview fallback (bounded-window machinery
  reused).
- `tests/unit/rag/` — detector, per-part map, gate, and end-to-end tests.
- `tests/fixtures/chapter_map/` — corpus chunk fixtures + recorded baselines.

**Docs:** none required (behavior is user-visible only through chat output
quality).

## Non-goals

- Reworking the legacy single-book heuristic tiers: they stay untouched; the
  gate only *vetoes* their output, it does not modify pins or scans.
- Targeted section queries inside anthologies ("summarize section 5 of I.1"):
  v1 routes only target-less broad-coverage summaries through the per-part
  path; targeted queries keep the legacy path and are protected by the gate
  (honest fallback instead of wrong-page output). Per-section drill-down is a
  follow-up.
- PDF-side fixes (regenerating the compilation with bookmarks/outline): the
  fix must work on already-ingested documents.
