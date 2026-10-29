# Design

## Context

See proposal.md — Why for the motivation. Diagnosis summary (verified against
the live store, 2026-10-27): the audited document has a structure tree, so the
chapter-overview answer went through the tree branch (`_tree_chapter_query`,
`src/secondbrain/rag/pipeline/_pipeline.py:2270`), which collects FULL
document-ordered per-chapter buckets via `_tree_chapter_buckets`
(`_structure_mixin.py:2586`) and generates per-chapter briefs through
`_generate_multi_chapter_summary` (`_fallback_mixin.py:548`). Chapter 16's
bucket (132 body chunks, 28,447 chars) fits the single-pass budget
(`_SINGLE_PASS_MAX_CHARS = 320_000`), so the model saw the complete chapter —
the VM/container snapshot-mode swap is a compression-attribution error, not
retrieval truncation.

The legacy (treeless) multi-chapter sampler (`_pipeline.py:1596-1715`) is a
separate, latent defect: it streams `get_body_chunks` output (sorted by
`page_number` only — within-page order is Qdrant point order,
`storage/qdrant.py:888`) and admits first-come under `per_chapter_limit = 8`
and `page_cap = 3` (header-promotion exception up to `page_cap + 2`).
Replaying it over the live store drops the correct VM snapshot-mode chunk and
admits the container one instead — deterministic only because Qdrant's point
order happens to be stable.

Relevant mechanics that constrain the design:

- Both the tree path and the legacy path build per-chapter briefs through
  `_generate_multi_chapter_summary` — one instruction site covers both.
- `_summarize_bounded` (`_fallback_mixin.py:964`) formats each window through
  `_format_context` with `max_chars = rag_max_context_chars` (16k per ~3.5k
  window — no truncation), joins the window contexts, and compares the joined
  total against the single-pass budget.
- `_format_context` (`_formatting_mixin.py:14`) labels each chunk
  `Source: {file} (page {page} [{tags}])` where tags carry only `chunk_role`
  and an inferred section label for heading-like chunks — `heading_path` is
  never shown.
- Store chunk dicts already carry `heading_path` and `page_pos`
  (`_payload_to_chunk` over `_OUTPUT_KEYS`, `storage/qdrant.py:383`) — both
  fixes need no schema or ingestion change.

## Goals / Non-Goals

**Goals**

- Give the summarizer an explicit scope-faithful attribution guard for the
  repeated-item-name pattern (VM block vs container block).
- Put each chunk's scope marker (heading path) on its own source line in
  summary context, for both the tree and legacy paths.
- Make legacy multi-chapter admission a deterministic function of stored
  content (document-order within a page) and let dense pages contribute more
  than the flat 3-chunk cap, within a bounded maximum.
- Keep window purity, window-composition statistics, the single-section
  lossless path, and the stored data untouched.

**Non-Goals**

- No guarantee that the LLM can never misattribute — the guard is
  instruction-level; the deterministic parts are testable invariants, the
  attribution outcome is regression-verified (see Risks).
- No post-generation verification or repair pass over summaries (one extra
  LLM call per chapter; the compressor that erred would also be the checker).
- No change to the single-chapter detailed path
  (`_generate_single_chapter_summary`), the single-section (≤2 chapters)
  full-fetch path, tree bucket collection, or coverage/window-composition
  reporting.
- No re-ingestion, re-chunking, payload refresh, or stored-data migration.
- Not addressing the source document's own internal inconsistency (the PVE
  guide states both 30 MB and 128 MiB for the same limit) — the transcript
  reproduced the source verbatim.

## Decisions

### D1. Attribution guard as instruction text in `_generate_multi_chapter_summary`

Extend the per-chapter brief-summary instruction
(`src/secondbrain/rag/pipeline/_fallback_mixin.py:608-618`) with an explicit
guard, roughly: "When the source lists the same item names under different
parent sections (e.g. backup modes described separately for VMs and for
containers), attribute each item's description to the parent section it
appears under; never swap, merge, or reuse one section's description for
another section's same-named item." Keep the 2-4-sentence length guidance
unchanged.

- **Why here:** both the tree branch (`_pipeline.py:2513`) and the legacy
  multi-chapter branch funnel per-chapter briefs through this one builder,
  and the audited briefs came from it.
- **Alternatives rejected:** (a) a post-generation verification/repair pass —
  an extra LLM call per chapter (~20 per overview), added latency and cost,
  and the same compressor that erred would judge the repair; (b) suppressing
  briefs when sibling scopes collide — degrades the feature instead of
  fixing it.

### D2. Heading-path label in `_format_context` source lines

When a chunk's dict carries a non-empty `heading_path`, append it to the
source-line tags: `Source: {file} (page {page} [{role}, {heading_path}])`.
Chunks without `heading_path` (or with an empty value) format byte-identical
to today. The label is per chunk, travels in `chunk_entry`, and therefore
participates in the existing `max_chars` budgeting — no separate accounting.

- **Why here:** `_format_context` is the single formatter used by
  `_summarize_bounded` (both tree and legacy summary paths) and by QA prompt
  construction; one change labels everything consistently, and scope labels
  also help grounded QA answers, not just summaries.
- **Alternatives rejected:** (a) injecting stored heading chunks adjacent to
  body chunks — changes window composition and duplicates the heading text
  the tree already carries; (b) a summary-path-only formatter — duplicates
  the formatting seam the change is trying to remove.

### D3. Document-order admission: sort in two layers

Layer 1 — `get_body_chunks` (`src/secondbrain/storage/qdrant.py:888`) sorts
by `(page_number, page_pos)` with a missing `page_pos` sorting last, so the
storage API itself returns document order; mirror the same tiebreak in the
mock backend for parity. Layer 2 — the multi-chapter round-robin
(`_pipeline.py:1613`) sorts its input client-side by the same key before the
admission loop, so determinism does not depend on which storage method fed
it. The header-promotion exception keeps its semantics, now compared against
the dynamic per-page cap (D4).

- **Why both layers:** layer 1 fixes the API contract for every caller;
  layer 2 is cheap insurance that keeps the pipeline backend-agnostic and
  directly unit-testable with shuffled fixture order.
- **Alternatives rejected:** server-side `order_by` scrolling — adds a
  Qdrant-version-dependent API dependency for something a client-side sort
  does trivially.

### D4. Density-aware per-page cap

Replace the flat `page_cap = 3` comparison with a per-page dynamic bound:

```
cap_pg = min(PAGE_CAP_MAX, max(page_cap, ceil(PAGE_DENSITY_FACTOR * n_chunks_on_page)))
```

with initial constants `page_cap = 3`, `PAGE_DENSITY_FACTOR = 0.6`,
`PAGE_CAP_MAX = 2 * page_cap` (= 6). For the audited dense page (8 body
chunks) this yields cap 5 instead of 3; with document-order admission the
VM block's chunks are admitted in order and, combined with D2's labels, the
container block's snapshot description — when it is also admitted — sits in
its own labeled block instead of being the only snapshot text in the window.
`per_chapter_limit` still bounds the chapter window; the cap never grows past
`PAGE_CAP_MAX` regardless of density. Constants are implementation-tunable;
the spec constrains only the shape (bounded scaling, per-chapter limit wins).

- **Why a bounded factor, not proportional share:** a page's density is
  relative to other *pages*, not to the chapter total — proportional shares
  computed against the chapter's chunk count would leave dense pages capped
  at the base and solve nothing.
- **Alternatives rejected:** raising `page_cap` globally to 6 — over-samples
  sparse pages and starves the round-robin spread the caps exist to provide;
  removing per-page caps entirely — reintroduces first-page clustering.

### D5. Scope of the fix

The density/order changes apply only to the legacy multi-chapter round-robin
branch. The single-section (≤2 chapters) full-fetch path and the tree branch's
`_tree_chapter_buckets` already fetch complete, document-ordered buckets and
are untouched.

## Risks / Trade-offs

- [Attribution is LLM behavior and cannot be mechanically guaranteed] → The
  instruction text is concrete and situational; D2 gives the model per-chunk
  scope labels so parallel blocks are visually distinct; the ch16 case is the
  acceptance regression (end-to-end re-ask, attribution must be
  scope-faithful). Honest labeling in the spec: the testable SHALLs are the
  guard's presence and the formatting/admission mechanics.
- [`_format_context` labels change prompt text for all callers, and labels
  consume part of the 16k context budget] → Labels appear only when
  `heading_path` is present; label length is one line per chunk; run the
  pipeline and formatting test suites; dense-context callers keep their
  existing truncation behavior (budget break at chunk boundaries).
- [Density scaling changes which chunks treeless documents admit — visible
  behavior delta for existing content] → That is the point of the fix; unit
  tests pin exact bucket membership before/after; the change is deterministic
  and document-ordered, so results are reproducible and reviewable.
- [Missing `page_pos` in hypothetical legacy payloads] → Sort key treats a
  missing position as last; explicitly covered by a unit test.
- [Prompt-length guidance may interact with the added guard text] → Guard is
  one sentence; keep brief-length guidance ("2-4 sentences") unchanged and
  covered by the existing instruction tests.

## Migration Plan

Single-commit code change; no data, schema, ingestion, or configuration
migration. Rollback is `git revert`. A stored-payload refresh is not needed
(`heading_path`/`page_pos` are already present in stored payloads). After
apply, the end-to-end check is a fresh chapter-overview re-ask against the
live store (chapter 16 attribution) — recorded in the change's verification
notes.

## Open Questions

None — the density constants (D4) are tunable implementation values; the
spec constrains only the bounded-scaling shape and the per-chapter limit.
