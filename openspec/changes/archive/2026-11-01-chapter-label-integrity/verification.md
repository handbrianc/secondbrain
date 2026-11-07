# Verification — chapter-label-integrity

## 3.1 Targeted regression suites — PASS

- `pytest tests/unit/rag -q` → 680 passed (r2; 661 at v1)
- `pytest tests/test_rag/test_pipeline.py tests/test_document/test_summarizer_core.py tests/test_document/test_summarizer_toc.py -q` → 94 passed
- `ruff check` + `ruff format` + `mypy` on all touched source files → clean
- New unit file: `pytest tests/unit/rag/test_chapter_bucket_labels.py -q` → 42 passed

## 3.2 Live acceptance replay, treeless store — PASS after r2 (failed at v1)

Command: `secondbrain chat "summarize by chapter story mapping epics report" --session chapter-label-verify-r2`

**v1 attempt (session `chapter-label-verify`) FAILED acceptance** and drove the
r2 revision: output was byte-equivalent in shape to the pre-fix defect — the
v1 text-marker guard was a no-op on this document (119 body chunks span pages
1–17, all under the text path's page-20 floor; zero line-initial `N.M` text
lines), and the live legacy path delegates one chapter per call through
`_generate_multi_chapter_summary_with_coverage`, so the in-funnel guard saw
single-key rosters and the roster-note gate (≥3 chapters) never fired.

**Live-store ground truth found during diagnosis:** the chunks carry
ingest-time structured identity — page 8's walking-skeleton/masking-tape
chunks: `chapter_id='7'`, `section_id='7.1'–'7.5'`, `heading_path="Chapter 7
— Prioritization and Release Slicing"` while the page-range pin had put them
in chapter 6's bucket; page 9 carries `7.6` then `8.1–8.2`. The model's
thinking note ("content is from Chapter 7 sections") was correct; the pins
were wrong.

**r2 replay observed output (excerpt, `/tmp/opencode/replay-treeless-r2.txt`):**

> Chapter 6 — Decomposition Strategies for Turning Epics into Stories
>
> No document content was retrieved for this chapter (its detected page range
> contains no body text), so no summary could be generated.
> Content in this chapter's detected page range self-identifies as chapter 7
> and was summarized under chapter 7's heading.
>
> Chapter 7 — Prioritization and Release Slicing
> [walking skeleton / masking-tape release slicing content — now under its own heading]
>
> Chapter 8 — Facilitation and Collaboration Best Practices
> [real 8.1/8.2 facilitation content — false placeholder gone]
>
> Coverage note: the detected chapter roster does not include chapter(s) 1–5
> — they may exist but were not located in the document's structure; this
> overview covers only the chapters listed above.

The guard also caught two more v1 mislabels the evaluation transcript had not
flagged: chapter 10's bucket content self-identifies as chapter 11 (now
placeholder + reason; the adaptation content summarized under Chapter 11),
and chapter 13's as chapter 12. Chapters 9, 12, 14, 15 keep their (correct)
summaries. Exactly one coverage note, last block, naming 1–5.

Residual, by design (non-goal): chapter 6's own true content (pages 6–7,
decomposition strategies) is not in any bucket — the upstream page-range
pins are still wrong for this document; the guard makes that harmless and
honest (placeholder + reason) instead of mislabeling. The operational remedy
is the stored-tree path via re-ingest.

## 3.3 Tree-backed replay — BLOCKED (not runnable on this host)

- `secondbrain ingest /data/workspace/uploads/story_mapping_epics_report.pdf`
  → `PATH does not exist`: the PDF was ingested elsewhere; only the path
  string survives as store metadata, so the structure-tree backfill cannot
  run from this machine.
- The store holds no other document (`list all sources` → 1 source) and
  `structure_nodes` is empty, so no tree-backed live replay is possible.
- Tree-path regression evidence in lieu: `pytest tests/unit/rag
  test_structure_tree_query.py test_anthology_pipeline.py -q` → 37 passed,
  including the wrapper-guard integration against the exported hcd-report
  fixture (whose `BASELINE_WINDOW_OVERRIDES` was updated with a documented
  mechanism-(3) comment: an `18.3` text-marker chunk previously dropped by
  single-key delegations is now reassigned into rostered chapter 18).
- User follow-up (operational): re-ingest the report from wherever the file
  lives (`secondbrain ingest <real path>`); the stored-tree path then drives
  enumeration with its own no-cross-chapter guarantee, and the guard runs as
  a safety net there too.

## 4.6 r2 live replay — PASS (see 3.2 excerpt; session `chapter-label-verify-r2`)
