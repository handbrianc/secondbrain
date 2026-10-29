# Design: Fix chunk heading context and term/definition binding

See proposal.md for motivation and the delta specs for behavior contracts.

## Context

The ingestion pipeline converts docling text items into segments
(`processor._extend_segments_from_document` — each item carries `text`,
`page`, optional `label`), merges them (`chunker._merge_segments`), splits
into chunks, classifies roles (`chunker.classify_chunk_role`), and annotates
them against the captured tree (`structure_annotate.annotate_chunks`,
processor.py:1020). `capture_docling_headings` (structure_capture.py:854)
turns docling section headers into tree nodes; outline capture is separate
and authoritative.

Measured on the PVE Admin Guide (7,515 chunks): 4,068/5,308 body chunks have
no `heading_path`; the stored tree has 3,324 nodes of which 2,741 are
unnumbered and many are plainly not headings ("Restart chrony:",
"pvesubscription - Subscription Management", "By running:").

Two mechanisms starve annotation:

1. **Tree pollution** — every docling `section_header` item becomes a node.
   Docling's layout model marks bold run-in labels and synopsis lines as
   section headers, so sibling candidates multiply per page.
2. **Same-page ambiguity bail-out** — `_annotate_chunk`
   (structure_annotate.py:297-307) refuses to annotate unanchored prose when
   any candidate node lies outside the deepest candidate's ancestor chain.
   With page-spanning ranges (by design, for tree lookups), two sibling
   sections sharing a page — the common case — leave all their prose
   unannotated. Re-ingest refresh (qdrant.py:479) reuses the same stateless
   rule in arbitrary scroll order, so hash-matched points stay unannotated
   forever ("bounded re-read waste" by the old design).

Constraints: annotation only ADDS payload keys (dedup by `text_hash` must
keep working); chunk text streams must stay byte-identical for unchanged
(plausible) input; outline capture is authoritative and ungated; the audio
(time-mode) branch of annotation must be untouched.

## Goals / Non-Goals

Goals:

- Body chunks of tree-ful documents get `heading_path`/`section_id` wherever
  reading order determines an owner (target ≥95% coverage on the PVE guide,
  from 23.3%).
- Structure trees stop growing nodes for implausible headings; term labels
  sit under their real parent section.
- Label/definition pairs stay in one chunk when the label is implausible.
- Re-ingest refresh produces the same annotations as fresh ingest.

Non-Goals:

- Perfect heading detection (residual sentence-fragment nodes are tolerated;
  ordered inheritance neutralizes their annotation impact).
- Re-ingesting documents automatically (stored documents gain fields only on
  re-ingest, via the existing refresh path).
- Changes to chunk sizes, overlap, roles of plausible headings, TOC/caption
  handling, or the audio annotation branch.

## Decisions

### D1: One shared predicate, two consumers

Add `is_plausible_heading(text: str) -> bool` to `chunker.py` (import-light;
`structure_capture` already imports from it):

- section-number prefix (`_is_section_numbered`) → True always;
- otherwise True iff `len < 120`, no trailing `.`, `:`, `,`, `;`, `—`, and
  no `" - "` substring (synopsis shape; mirrors `_is_likely_title`'s dash
  rejection).

Consumers:

- `capture_docling_headings`: skip node creation for docling-heading items
  failing the test (outline part untouched).
- `_merge_segments`: a `section_header`-labeled segment failing the test no
  longer hits the standalone structural flush (chunker.py:336-356); it joins
  the accumulation like body text and its label is dropped on join (a merged
  body chunk must not carry a heading label into `element_type`).

Rationale: one predicate keeps capture and chunking consistent — a node and
an orphan heading chunk are the same mistake seen twice. Alternatives
rejected: filtering inside docling conversion (touches text items, forbidden
by the heading-hierarchy requirement's "neither adds, removes, nor reorders"
clause); independent per-consumer heuristics (drift).

The thresholds are deliberately conservative: "GENERAL BTRFS ADVANTAGES"
(all caps, real run-in heading) passes; "Restart chrony:" fails. A real
heading misclassified as implausible loses only its tree node — its text
still reaches chunks and gets annotated by inheritance — while a spurious
node actively corrupts sibling annotation.

### D2: Ordered sticky inheritance in annotation

`annotate_chunks(chunks, tree, *, ordered=False)` — new keyword, default
False = today's behavior byte-for-byte (existing tests pass unchanged).
With `ordered=True` (callers that pass chunks in reading order), an
unanchored page-mode chunk resolves in this precedence:

1. **Anchor** — heading-form match, as today; sets the sticky owner.
2. **Sticky owner** — the previous chunk's annotation target, when its node
   is among the range-containing candidates.
3. **Most-recent-start candidate** — the candidate with the greatest
   `(start, level, reading index)`, i.e. the heading most recently opened at
   or before the chunk's position. Reading order is the one signal that
   resolves same-page siblings, so ordered mode resolves instead of bailing.

`ordered=False` keeps the conservative deepest-candidate + chain-consistency
bail-out unchanged for callers that cannot guarantee reading order.
`last_owner` is never reset by unannotated chunks; containment is re-checked
per chunk, so an oscillating page that leaves the owner's range falls through
to rule 3 (still containment-bounded). Audio (time mode) stays stateless.

Rationale: the processor already walks chunks in document order (docstring
guarantee of `annotate_chunks`; the worker's post-dedup list preserves it).
The hard constraint "only ADD keys" is preserved: every rule picks a node the
containment filter already deemed a candidate. Alternatives: dropping the
bail-out for unordered callers too (unsound); character-offset ownership
(payload has no char offsets; would need a schema migration).

**Verification finding (2026-10-27, live PVE re-ingest):** with the original
sticky-then-bail rule, *stored* coverage stayed at 23.8% while a full-stream
ordered pass reached 87.1% — both entry points (dedup-filtered ingest,
`is_empty`-filtered refresh) fragment the reading order, and the bail
cascade leaves chunks whose predecessors were dropped unannotated. Rule 3
removes the ordered-mode bail; measured full-stream coverage with it:
~99% of body chunks (front-matter pages before the first node excepted).

### D3: Refresh annotates the full document stream, payload-only

Rework `refresh_structural_payload` (qdrant.py):

1. Scroll **all** of the document's points — not only those with an empty
   `node_id` — payload only (`with_vectors=False`; vectors are never
   round-tripped; ≈7.7k points ≈ 15 MB payloads).
2. Sort on `(page_number, page_pos, chunk_id)` and annotate in ONE
   `annotate_chunks(..., ordered=True)` pass (design D2).
3. Write back with `set_payload` by explicit point ids in batches
   (~256 ids/batch), **only for points whose stored annotation keys are
   missing or differ** from the fresh annotation. One payload dict applies
   to every listed id, so records are grouped by identical annotation first.
   Points whose annotated chunk resolves no node are never written.
4. Delete stale extras: stored annotation keys the fresh annotation no
   longer carries are removed with a targeted `delete_payload(keys, points)`
   pass (also id-batched, grouped by identical stale-key set).
   `set_payload` cannot delete keys — a diff-gated set-only write leaves
   such extras on the point forever, and the diff gate then re-detects them
   on every re-run (measured on the live PVE collection: 33/7,717 points
   carried `section_id` from the pre-change tree; a set-only refresh
   reported 33 on every re-run). Deletion makes the refresh truly converge.
   Stored `t_start`/`t_end` are treated as legitimate annotation input only
   for time-keyed (audio) trees (`is_time_mode_tree`); page-keyed documents
   get stale audio leftovers deleted.

Why the full stream: the previous `is_empty("node_id")`-filtered refresh
annotated a *sparse* subset in which most heading chunks (already annotated)
were missing, so no anchor and no sticky owner ever existed — the PVE
re-ingest left stored body coverage at 23.8% where the full stream reaches
~99% (design D2's verification finding). The full stream also *corrects*
stale annotations: points annotated against an older tree (the gate changes
the tree at recapture) get their `heading_path`/`section_id` rewritten.
Diff-gated writes keep the operation idempotent and cheap on no-op re-runs.

`set_payload` sets/overwrites only the listed keys, matching the old
full-payload rewrite's net effect on annotation keys. Value `None` keys are
never set (only keys present in the annotated chunk). This replaces the
read-modify-write + `seen_ids` stall-guard loop: the collect pass finishes
before any write, the filter-cursor stall is structurally impossible, and
vectors are never re-uploaded.

### D4: Callers switch deliberately

- processor.py:1020 passes `ordered=True` (fresh ingest, true reading order).
- The refresh path sorts then passes `ordered=True` (D3).
- No other call sites exist; `ordered` defaults False so any future caller
  is conservative until it opts in.

### D5: Pluralization at the CLI boundary only

`cli/ingest.py:145` (and the skipped/failed lines) pluralize with a tiny
helper (`f"{n} file{'s' if n != 1 else ''}"` shape). No spec delta — display
detail, below spec level.

## Risks / Trade-offs

- [Gate demotes a real heading → missing tree node] → Numbered prefixes
  always pass; outline nodes ungated; text still lands in chunks and gets
  annotated via inheritance; thresholds conservative.
- [Sticky owner wrong on alternating same-page siblings] → Owner must
  contain the chunk's page; anchors take priority; unresolvable cases fall
  back to today's conservative rule (never worse than the status quo).
- [Pairing changes chunk boundaries for implausible labels] → That is the
  point (orphan chunks are the defect); regression suites guard plausible
  streams byte-for-byte (`test_chunker_role_regression.py`); label dropped
  on join keeps `element_type` truthful.
- [set_payload rewrite departs from read-modify-write] → Older points keep
  their payload except annotation keys; vector untouched; behavior covered
  by updated refresh wiring tests; rollback safe (keys are additive).
- [Docling labels vary across file types] → Gate and pairing apply only to
  the `section_header` label; `label_to_element_type` unchanged for others.
- [Memory of the payload-only refresh pass] → Payloads only, no vectors;
  bounded per document; acceptable at 10× the PVE size.

## Migration Plan

1. Ship code; existing stored documents are unchanged until re-ingest.
2. Re-ingest refreshes structural payload keys on hash-matched points (no
   re-embedding) and recaptures trees; fresh ingest annotates ordered.
3. Rollback: revert the change; payloads retain extra keys harmlessly.

Verification uses the PVE guide: re-ingest, then re-run the chunk-analysis
scripts from the evaluation (`/tmp/opencode/find_chunks.py`,
`/tmp/opencode/search_chunks.py`) to confirm heading_path coverage ≥95% of
body chunks, absence of the "FSYNCS/SECOND"-under-mangled-parent shape, and
a chat spot-check on the three eval defects.

## Open Questions

None. Gate thresholds (120 chars, punctuation set, synopsis shape) are
tunable constants, documented above; they do not change the spec's contract.
