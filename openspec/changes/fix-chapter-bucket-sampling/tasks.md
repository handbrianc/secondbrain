# Tasks

## 1. Heading-path labels in formatted summary context

- [x] 1.1 In `_format_context` (`src/secondbrain/rag/pipeline/_formatting_mixin.py`), append the chunk's `heading_path` to the source-line tags when the chunk dict carries a non-empty value (`Source: {file} (page {page} [{role}, {heading_path}])` per design D2); chunks without it format byte-identical to today; update the docstring example; verify with `pytest tests/unit/rag/test_pipeline_mixins.py -k format -x -q` green
- [x] 1.2 Extend `_format_context` tests in `tests/unit/rag/test_pipeline_mixins.py` (chunk with heading path → label present on its own source line; chunk without → output unchanged vs. current format; several chunks from different scopes → per-chunk labels) and run them green

## 2. Attribution guard in per-chapter brief summaries

- [x] 2.1 Extend the per-chapter brief-summary instruction built in `_generate_multi_chapter_summary` (`src/secondbrain/rag/pipeline/_fallback_mixin.py:608-618`) with the scope-faithful attribution guard per design D1 (repeated item names under different parent sections are attributed to their own section; never swapped/merged/reused; 2-4-sentence length guidance unchanged); verify with the existing chapter-summary instruction tests green
- [x] 2.2 Add a unit test asserting the guard text is present in the built per-chapter brief instruction and that empty-bucket placeholder handling is unchanged; run `pytest tests/unit/rag -k chapter_summary -x -q` green

## 3. Deterministic, density-aware legacy sampler admission

- [x] 3.1 In `get_body_chunks` (`src/secondbrain/storage/qdrant.py:888`), sort by `(page_number, page_pos)` with a missing `page_pos` sorting last (design D3 layer 1); mirror the same ordering in the mock backend's equivalent method (`tests/unit/rag/_chapter_fixture_storage.py` semantics stay aligned); verify with an ordering unit test (fixture chunks stored out of order → returned in `(page_number, page_pos)` order) green
- [x] 3.2 In the multi-chapter round-robin (`src/secondbrain/rag/pipeline/_pipeline.py:1596-1715`), sort the incoming chunk stream client-side by `(page_number, page_pos)` before the admission loop (design D3 layer 2) and compare the header-promotion exception against the dynamic per-page cap; verify the existing purity suite `pytest tests/unit/rag/test_chapter_window_purity.py tests/unit/rag/test_pipeline_iterative.py -x -q` green unchanged where fixtures are already document-ordered
- [x] 3.3 Implement the density-aware per-page cap per design D4 (`cap_pg = min(PAGE_CAP_MAX, max(page_cap, ceil(PAGE_DENSITY_FACTOR * n_chunks_on_page)))`, `page_cap=3`, `PAGE_DENSITY_FACTOR=0.6`, `PAGE_CAP_MAX=6`); verify with new admission tests: dense page admits more than 3 (≤6), sparse page unchanged, per-chapter limit wins over density, deterministic replay (shuffled storage order → identical bucket), boundary-straddle supplement still respects the caps
- [x] 3.4 Extend `tests/unit/rag/test_chapter_window_purity.py` and `tests/unit/rag/test_pipeline_iterative.py` with a dense-page fixture pinning exact bucket membership (VM-block chunks admitted in document order before the container block) and run the two suites green

## 4. Full validation

- [x] 4.1 Run `ruff check . && ruff format --check .` and `mypy` on the touched packages; fix findings
- [x] 4.2 Run the fast suite `pytest -m "not integration and not chaos"` green
- [x] 4.3 Run `openspec validate fix-chapter-bucket-sampling --strict` and mark tasks complete
- [x] 4.4 End-to-end regression against the live store: re-ask the chapter-by-chapter overview for the PVE guide and verify chapter 16's VM "snapshot mode" description is scope-faithful (VM facts attributed to the VM block, container facts to the container block); record the evidence in the change's verification notes
