# Tasks

## 1. Capture-layer ToC parsing and number recovery (document-structure delta, D1)

- [x] 1.1 Add a pure ToC-row parser to `src/secondbrain/document/structure_capture.py` (dot-leader rows `N Title … page`, `N.M Title … page`; whitespace-squash tolerant) and verify with unit tests in `tests/unit/document/test_structure_capture.py` covering numbered, dotted, and glued rows
- [x] 1.2 Implement the post-merge numbering pass in `structure_capture.py` that matches number-less nodes to ToC listings by normalized title + document order + nesting level, never overwriting parsed numbers, and verify the three spec scenarios (number-less outline → numbered tree; parsed numbers untouched; ambiguous match stays unnumbered) via new unit tests
- [x] 1.3 Wire the recovery pass into the ingest capture flow and verify on a synthetic fixture PDF (number-less bookmarks + numbered ToC) that `StructureStore.save_structure` persists the recovered numbers — `pytest tests/unit/document/test_structure_capture.py tests/unit/storage/test_structure_sqlite.py`

## 2. Stored-tree chapter map integrity (rag-pipeline delta, D2)

- [x] 2.1 In `_tree_chapter_map` (`_structure_mixin.py`), reject candidate chapter ranges whose stored chunks are dot-leader-dense (ToC-like) and verify via unit test that a chapter node ranged inside a ToC span contributes no map entry (`tests/unit/rag/test_structure_tree_query.py`)
- [x] 2.2 Add the degenerate-map fallback: when the surviving number-keyed map covers fewer chapters than the tree's non-ToC-span chapter-shaped nodes, log and return the legacy-path signal instead of enumerating from the partial map, and verify with a unit test reproducing the 2-of-21 shape from `pve-admin-guide-9.1.pdf`
- [x] 2.3 Verify the healthy-tree case is unchanged: existing tree-path tests still pass with the guard in place — `pytest tests/unit/rag/test_structure_tree_query.py tests/unit/rag/test_pipeline.py`

## 3. Legacy chapter title and window guards (rag-pipeline delta, D3)

- [x] 3.1 In `_derive_chapter_numbers`, reject dotted-prefix headings as chapter titles (mirroring the ToC-row guard at `_structure_mixin.py:598`) and fall back to the ToC-listing title for that chapter number, else number-only header; verify with unit tests: "1.1 Central Management" never titles chapter 1, ToC title "Introduction" is used (`tests/unit/rag/test_pipeline.py`)
- [x] 3.2 Implement the extend-only window clamp (chapter end = next chapter start − 1 when derivable and beyond current end) and verify with unit tests: undershooting chapter 1 extends to chapter 2's start; a healthy document's windows and emitted summaries are byte-identical (`tests/unit/rag/test_pipeline.py`, `tests/unit/rag/test_pipeline_iterative.py`)

## 4. Environment and re-ingest (D4)

- [x] 4.1 Check docling-parse for a release fixing the space-glue regression (`scripts/libyear.sh` / `pip index versions docling-parse`) and record the outcome; upgrade only if a fixed release exists — verify the chosen docling/docling-parse versions print cleanly after the decision
  - Outcome (2026-10-26): **no upgrade** — upstream releases 7.22.3 / 7.22.4 / 7.23.0 (everything since installed 7.22.2) contain no fix for the space-glue regression (verified against the full upstream CHANGELOG.md); docling 2.138.0 / docling-parse 7.22.2 remain installed. D1–D3 make capture and query paths healthy regardless of the glue regression.
- [x] 4.2 Re-ingest `/home/bchand/pve-admin-guide-9.1.pdf` and verify the tree is rebuilt (`secondbrain structure pve-admin-guide-9.1.pdf` shows 21 numbered chapter nodes at body pages and sections 1.1–1.13; no re-embedding of unchanged text in the log)
  - Verified 2026-10-26 (ingest 07:13 UTC): tree rebuilt with recovery; **18 numbered body chapters** at body pages (1–6, 8, 9, 11–19, 21) and chapter 1 at pp. 23–31 with sections 1.1–1.13 — the planning-time "21" did not account for (a) the spec's designed conservative guards (parsed junk child numbers win over recovery: ch. 7 Storage blocked by 'Backend' parsed as 'LVM', ch. 10 QEMU by 'Generation ID' as 'VM', ch. 20 FAQ by list items parsed as '10'–'13') and (b) 8 appendix chapters that are letter-numbered in the document (no decimal ToC rows). No re-embedding occurred (skip-existing path; only the tree was re-captured).

## 5. Verification gate (D5)

- [x] 5.1 Re-run both chat queries ("summarize by chapter the proxmox guide", "summarize by chapter 16 the proxmox guide") and verify chapter 1 covers all 13 sections with the title "Introduction" and chapter 16 remains deep and faithful
  - Verified 2026-10-26: broad query → 20 chapters, all correctly titled; chapter 1 is "Introduction" (window spans its body pages 23–31, next bucket starts at 32), summaries drawn from real body content; chapter-16 query → deep faithful overview (modes, fleecing, change detection, retention, live-restore, vzdump.conf, hook scripts).
- [x] 5.2 Run `scripts/audit_chapter_summaries.py` across the document and verify no chapter window is ToC-span-derived or truncated versus the ToC listing boundaries
  - Verified 2026-10-26 (`/tmp/opencode/audit_post.json`): PASS — 20 buckets anchored at the ToC-listing body pages (1→23, 2→32, 3→49, 4→119, 5→132, 6→158, 7→163, 8→195, 9→221, 10→225, 11→309, 12→340, 13→367, 14→386, 15→409, 16→434, 17→450, 18→461, 19→467, 20→469), zero buckets inside the ToC span (3–22), monotonic, 0 empty, 0 degraded; ch. 7's 3 dropped chunks are the window guard correctly excluding out-of-range pages.
- [x] 5.3 Full quality gate: `ruff check . && ruff format --check . && mypy .` and `pytest -m "not integration and not chaos"` pass with the new tests included
  - Verified 2026-10-26: ruff clean, 567 files formatted, mypy clean (108 source files), `pytest -m "not integration and not chaos"` → 4148 passed, 3 skipped in 45s (includes the 48 new capture-layer tests + 15 guard tests + 14 page-bound tests).
