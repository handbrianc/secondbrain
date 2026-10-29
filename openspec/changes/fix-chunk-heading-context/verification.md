# Verification — fix-chunk-heading-context

Live verification on the Proxmox VE Administration Guide 9.1 PDF (656 pages),
executed 2026-10-27. Ground truth: extracted PDF text
(`/tmp/opencode/pve.txt`, `@@PAGE n@@` markers); chunk data via the Qdrant
HTTP API on the collection points of `source_file =
/home/bchand/pve-admin-guide-9.1.pdf`.

## Baseline (evaluation, pre-change)

- Body chunks without `heading_path`: **4,068 / 5,308 (76.7% missing)**;
  stored coverage 23.3–23.8%.
- Structure tree: 3,324 nodes, 2,741 unnumbered, many spurious
  ("Restart chrony:", synopsis lines) — every docling `section_header`
  became a node.
- Term/definition split: "FSYNCS/SECOND" label orphaned from its definition
  sentence; definition retrieval mis-attributed the §19.2 pveperf metric.
- Eval defects: FSYNCS > 200 attributed to the wrong metric (§19.2, printed
  p. 445); Ch.13 fused firewall directions with zones (§13.1, printed
  p. 345); §9.6 `pvesr create-local-job` quoted without `--schedule "*/5"
  --rate 10` (printed p. 202) — LLM synthesis slip; the full command was in
  chunk `f72b53bb…` all along (docling spacing: "create - local-job").

## After the change (stored, post re-ingest + refresh)

Live re-ingest recaptured the tree (3,108 nodes; 216 spurious docling
headings gated out) and the refresh annotated the full point set
(7,717 points; wrote 4,745 diff-gated `set_payload` batches in 6.4 s):

| Measure | Before | After | Target |
| --- | --- | --- | --- |
| Body chunks with `heading_path` | 1,150/4,823 (23.8%) | **4,823/4,823 (100.0%)** | ≥95% |
| Remaining unannotated body chunks | 3,673 | **0** | 0 |
| FSYNCS definition chunk (p. 467) path | unannotated / wrong parent | ends `> FSYNCS/SECOND` (§19 chapter chain) | term bound to definition |
| pvesr §9.6 chunk (`f72b53bb…`, p. 224) | path None | `Chapter 9 — Storage Replication > 9.6`, full command present | correct section |
| `section_id` vs `heading_path` inconsistencies | n/a (unmeasured) | **0** (token-level check over all 7,717 points) | 0 |
| Idempotent re-refresh | n/a | **0 points written** (runs 2 and 3) | 0 |
| Vectors | round-tripped (old design) | never read or rewritten (`with_vectors=False`, no `upsert`) | payload-only |

### Stale-extraneous keys and the delete pass

A second finding surfaced during the idempotence check: 33 points (0.4%)
carried `section_id`/`section_label` from the **pre-change** tree (e.g.
`10.2.1 General Settings` on p. 226) that the fresh annotation no longer
computes. `set_payload` cannot delete payload keys, so a diff-gated
set-only refresh left them — and the diff gate then re-detected the
difference on every re-run (33 rewritten each time, never converging).
Resolution (design D3 step 4): a targeted `delete_payload(keys, points)`
pass removes annotation keys the fresh annotation no longer carries,
grouped by identical stale-key set. Live result: run 1 deleted exactly
those 33; runs 2 and 3 wrote 0. The refresh now converges.

Notes:

- The FSYNCS/SECOND node parents under the outline-derived
  "pvesubscription - Subscription Management" synopsis node. Accepted by
  design: that title IS a genuine PDF outline bookmark (verified with
  pypdfium2 `get_toc`, 680 entries); outline nodes stay ungated. The
  definition chunk's `section_id` is 19 ("Useful Command-line Tools"), and
  its `heading_path` ends with the term itself, so term→definition
  retrieval resolves correctly.
- "Command-line Interface > qm - QEMU/KVM Virtual Machine Manager > …"
  paths (421 chunks) are **not** stale: `qm - QEMU/KVM Virtual Machine
  Manager` and its option sub-nodes are genuine outline-derived nodes in
  the current tree; the diff gate found stored == fresh and left them.
- In-memory full-stream ordered annotation (rule 3, most-recent-start
  fallback) measured 100.0% body coverage before the refresh was written;
  the stored result matches it exactly — refresh now equals fresh ingest.

## Test results

- Predicate/capture/pairing lanes: 23 + 6 + capture-gate tests; byte-identity
  suites (chunking, labeled chunking, role regression, split
  characterization) green.
- Annotation: 32 tests (incl. ordered sticky, oscillating-page
  most-recent-start fallback, unordered bail-out preserved, time-mode
  unaffected, add-only/no-mutation).
- Qdrant refresh: 16 tests (full-set payload-only scroll, reading-order
  reconstruction, diff-gated writes, **stale-key deletion + convergence**,
  partial-count degradation, batch bound 256, other-sources untouched,
  vector preservation).
- Fast suite: `pytest -m "not integration and not chaos"` → **4,193
  passed, 3 skipped** (45 s).
- Lint/types: `ruff check .` clean; `ruff format --check .` clean (577
  files); `mypy` clean on all six touched modules.
- `openspec validate fix-chunk-heading-context --strict`: valid.
