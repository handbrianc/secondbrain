# Tasks

## 1. Ceiling exemption and surfacing (`_structure_mixin.py`)

- [x] 1.1 Role-gate the ceiling clause in the bare-number loop (`:1316`) and the banner loop (`:1401`): refuse only when the chunk's role is not "heading"; `ft_catch` (`:1422`) unchanged
- [x] 1.2 Debug log on every ceiling refusal (number, source, shape) at the three guards
- [x] 1.3 Unit tests: dense-book real-probe roster {1,2,3} with ch3 bucketed (no single-section degradation); body-noise above-ceiling line stays refused on non-heading chunks; ft_catch above-ceiling row refused regardless of role; refusal log asserted
- [x] 1.4 `pytest tests/unit/rag -q` green

## 2. Heading channel (`_pipeline.py`)

- [x] 2.1 Merge the heading-role scan into the derivation sample before `_derive_chapter_numbers` (dedupe by chunk_id, page order preserved)
- [x] 2.2 Unit test: a primary sample missing a late heading chunk still derives the chapter via the merged channel
- [x] 2.3 `pytest tests/unit/rag -q` green

## 3. Reconciliation and acceptance

- [x] 3.1 Probe all four book fixtures for above-ceiling heading-role bare matches before/after; regenerate baselines only for books whose roster actually changes, diff classified (expected: none)
- [x] 3.2 Lint + types on touched files: `ruff check`, `ruff format`, `mypy`
- [x] 3.3 Full fast suite `pytest -m "not integration and not chaos" -q` green *(4562 passed, 3 skipped, 0 failed, 57 s; +35 = A's 27 + B's 8 new tests)*
- [x] 3.4 Live: one enumeration replay of the hcd report answers unchanged (tree-driven; derivation not consulted) *(exit 0; 21/21 chapters, clean titles, ch19 full tree title, no coverage note; `/tmp/opencode/replay_pins.txt`)*
- [x] 3.5 Write `verification.md`; `openspec validate fix-chapter-heading-probe-rank` green; update knowledge todo d4fd93ec (mechanism correction + outcome) and file the follow-up todo for the fallback-limit truncation hazard
