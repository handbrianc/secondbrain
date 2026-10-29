# Verification — fix-chapter-bucket-sampling

Date: 2026-10-27 · Apply executed via three parallel fixer lanes (tasks 1, 2, 3)
with orchestrator reconciliation and full validation.

## Unit / static gates

| Gate | Command | Result |
| --- | --- | --- |
| Lint + format | `ruff check . && ruff format --check .` | all checks passed, 581 files formatted |
| Type check | `mypy src/secondbrain/rag src/secondbrain/storage` | Success: no issues found in 32 source files |
| Fast suite | `pytest -m "not integration and not chaos" -q` | 4209 passed, 3 skipped, 0 failed (46.19s) |
| OpenSpec | `openspec validate fix-chapter-bucket-sampling --strict` | valid |

Lane-level suites (all green before the full gates): formatting/mixins 129 passed;
chapter/summary/fallback selection 319 passed; `tests/unit/rag` 610 passed; storage
document-order tests 39 passed; purity 26 passed; iterative 20 passed; anthology
suites unaffected.

## New coverage mapping (spec → tests)

- Scope-faithful attribution guard present in the per-chapter brief instruction →
  `tests/unit/rag/test_pipeline.py::TestMultiChapterMapReduce::test_multi_chapter_brief_instruction_carries_attribution_guard`
- Heading-path label / unchanged-without / per-chunk labels / budget accounting →
  6 new tests in `tests/unit/rag/test_pipeline_mixins.py` (`TestFormatContext`)
- Document-order admission, dense-page scaling, sparse-page pin, per-chapter limit
  wins, shuffled-storage reproducibility, straddle-supplement cap, dense opener
  admission, ch16 exclusion pin → `tests/unit/rag/test_pipeline_iterative.py` and
  `tests/unit/rag/test_chapter_window_purity.py` (`TestDensePageDocumentOrder`,
  `TestStraddleSupplementCap`)
- `get_body_chunks` `(page_number, page_pos)` ordering (qdrant + mock, missing
  `page_pos` last) → `tests/test_storage/test_qdrant_filters.py`,
  `tests/test_storage/test_mock_advanced.py`

## End-to-end regression (task 4.4, live store + live LLM)

Command: `secondbrain chat "Give me a brief summary of each chapter of this
document"` (one-shot, provider `openai`/`GLM-5.3-Flash` per `.env`, live Qdrant
`embeddings` collection, PVE admin guide 9.1.0). Full transcript saved at
`/tmp/opencode/ch16_regression.md` (exit 0; intent detected: chapter enumerate).

Result: chapter 16 now attributes snapshot mode scope-faithfully —
> "For VMs, the snapshot mode provides the lowest operation downtime at the cost
> of a small inconsistency risk by performing a live backup while the VM is
> running, while the suspend mode is provided for compatibility reasons and is
> not recommended since suspending the VM results in a longer downtime and does
> not necessarily improve the data consistency."

The audited defect (VM "snapshot mode" described with the container block's
"uses the snapshotting facilities of the underlying storage") does not recur.
All 20 chapters produce briefs; previously-flagged source-verbatim items still
match the document (ch1 "30MB", ch6 "128 MiB", ch19 pvesh root-only, ch20
version table).

## Observations (honest caveats)

- The attribution guard is instruction-level (design D1 accepts this): the
  deterministic guarantees (labels, ordering, caps) are unit-tested invariants;
  the LLM-behavior outcome is verified by this one regression run, not proven
  for all runs/inputs.
- Briefs in the regression run ran longer than the instructed 2-4 sentences
  (provider/model compliance variance; the instruction text keeps the 2-4
  sentence guidance unchanged). Cosmetic only, not a code change.
- Follow-up found during testing (out of scope, documented in the purity test
  docstring): with a real top-k probe, a dense page's body chunks can outrank a
  lone chapter heading, silently dropping that chapter from the roster —
  recorded as a backlog todo.
- The working tree carries other changes' uncommitted work (fix-chunk-heading-
  context, table serialization, reasoning display); lane deltas were reviewed
  hunk-by-hunk against self-labeled design references to attribute authorship.
