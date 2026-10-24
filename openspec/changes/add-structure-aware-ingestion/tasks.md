# Structure-Aware Ingestion — Tasks

## 1. Structure store (lane 1a)

- [x] 1. Create `src/secondbrain/storage/structure_sqlite.py`: models
  (`StructureNode`, `PageLabelRange`, `AudioSegment`, `DocumentStructure`) +
  `StructureStore` mirroring `ConversationStorage` (sync + `*_async` twins,
  `ValidatableService`), schema per design §4, save = full replace per
  `source_file` in one transaction, `load_tree`/`has_tree`/`delete_structure`
- [x] 2. Store unit tests: save/load round-trip, idempotent re-save, treeless
  lookup → None, delete, user_version untouched

## 2. Capture at ingest (lane 1a)

- [x] 3. Create `src/secondbrain/document/structure_capture.py`:
  `capture_pdf_outline` (pypdfium2 `get_toc`, deterministic node ids, kind
  inference), `capture_page_labels` (`FPDF_GetPageLabel` grouped runs),
  `capture_docling_headings` (`SectionHeaderItem.level`), `merge_structures`,
  dispatcher `capture_structure` that never raises
- [x] 4. Enable docling heading hierarchy in `docling_factory.py`
  (`heading_hierarchy_options.enabled = True` for PDF pipelines)
- [x] 5. Wire capture into `processor.py` worker path (returns `structure`
  with the result) and persist once per document from
  `ingestor/_sync.py`/`_async.py` via the shared save helper
- [x] 6. Capture tests: synthetic outline fixture (nested + anthology-shaped
  TOC), page-label grouping, heading hierarchy on a docling fixture, merge
  precedence (outline wins), failure → None + ingest continues

## 3. Chunk roles, annotation, payload (lane 1b)

- [x] 7. `chunker.py`: remove the section-numbered → `body` downgrade;
  assert chunk text streams byte-identical before/after on fixture inputs
- [x] 8. Create `src/secondbrain/document/structure_annotate.py`
  (`annotate_chunks` per design §7); worker calls it when a tree exists
- [x] 9. `storage/qdrant.py`: add `chunk_role` to `_INDEXED_FIELDS` +
  idempotent payload-index creation in `_ensure_collection`;
  `refresh_structural_payload(source_file)` batched is_empty-targeted
  read-modify-write; call it from both ingest paths after store
- [ ] 10. Audio capture in `structure_capture.py`: ASR timestamps →
  `t_start`/`t_end` nodes/segments (empirical probe on the corpus m4a);
  LLM topic segmentation in the parent after persist (config flag, ≤20
  windows); no-timestamps → single whole-document segment; ingest never fails
- [x] 11. Tests: annotate mapping (anchor, inherit, chapter/section ids),
  role-change regression (fixture byte-identity), qdrant index creation +
  refresh against a fake client, audio degradation path

## 4. Tree-lookup query path (lane 2)

- [x] 12. `_pipeline.py`: tree branch in `_iterative_query` ahead of
  roster/pinning (per design §8), building the legacy-consumable map shape
  from SQL nodes; `structure_source=tree` provenance
- [x] 13. Buckets collect through existing qdrant page-range filters driven by
  tree ranges; empty-range chapters emit the existing placeholder note
- [x] 14. `_structure_mixin.py`/`_fallback_mixin.py`: reuse bounded-window
  summarizers unchanged for tree-built maps; legacy path untouched as fallback
  (lookup error / treeless / tree without structural nodes)
- [x] 15. Tests: tree-driven enumeration on a synthetic HCD-shaped tree (all
  chapters, no placeholders, chapter-6 range clean); fallback
  characterization on treeless fixtures (legacy output unchanged); anthology
  + gate still own treeless anthologies

## 5. Inspector CLI + management (lane 3)

- [x] 16. `secondbrain structure <doc>` (`cli/structure.py` + registration):
  tree view (kind/number/title/pages/labels), page-label table, audio
  segments, `--json`; treeless → re-ingest guidance; unknown source → error
- [x] 17. Document delete removes the stored tree
  (`management/__init__.py` → `StructureStore.delete_structure`)
- [x] 18. Docs: user-guide page for `structure` + backfill note; README CLI
  mention

## 6. Validation

- [x] 19. `openspec validate add-structure-aware-ingestion --strict`
- [x] 20. `ruff check . && ruff format --check .`; `mypy` on touched files
- [x] 21. Fast suite green: `pytest -m "not integration and not chaos"`

## 7. Live verification

- [ ] 22. Re-ingest with the worktree code against the live store:
  `hcd_best_practices_report.pdf`, VirtualBox UserManual, pve admin guide,
  Tampa m4a; confirm trees stored + payload fields populated + legacy points
  refreshed without re-embedding unchanged hashes
- [ ] 23. Replay the failing chat queries: HCD summarize enumerates chapters
  1–21 (no placeholders, chapter 6 clean); section-start questions answer from
  the tree (`structure_source=tree`); `secondbrain structure` output matches
  the store; treeless control document keeps legacy behavior
- [ ] 24. Tick tasks as steps complete; archive the change
  (`openspec archive add-structure-aware-ingestion`) with spec promotion
