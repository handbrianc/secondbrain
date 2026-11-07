# Proposal

## Why

A chat-session evaluation of the treeless `story_mapping_epics_report.pdf` found
the multi-chapter overview presenting chapter 7's content under the
"Chapter 6" heading (and chapter 8's under "Chapter 7") while the model's own
thinking note recorded the mismatch ("content is from Chapter 7 sections") and
the per-chapter instruction still forbade correcting it. The same document,
replayed two days apart, produced the identical wrong labels, silently omitted
chapters 1–5 entirely (no heading, no placeholder, no note — the roster
detection dropped them before the placeholder path could speak), and emitted
empty-bucket placeholders for chapters 8 and 11. The stored-tree path already
guarantees "no chapter's summary draws content from another chapter's pages"
(`add-structure-aware-ingestion`), but this document has no stored tree, so the
legacy path ran with no content-level guard at all: the existing
`_chapter_range_gate` compares pins against pins and explicitly does nothing
when a document carries 0 evidence pins — exactly this report's case.

## What Changes

- Chapter buckets gain a content-consistency guard in the shared
  `_generate_multi_chapter_summary` funnel (legacy AND stored-tree callers):
  bucket chunks whose own heading-shaped section marker (`N.M` line-initial
  heading) names a different chapter are reassigned to that roster chapter's
  bucket, or dropped when that chapter is not in the roster, so a chapter
  heading is never summarized over content that self-identifies as another
  chapter.
- A chapter emptied by the guard shows the existing placeholder note, extended
  with a deterministic reason line naming where its content was reassigned.
- The multi-chapter overview gains a roster-gap acknowledgment: when the
  detected chapter roster skips numbers (begins above 1 or has internal gaps),
  the output states which chapter numbers were not located instead of
  presenting a partial overview as complete.
- Unchanged: the per-chapter instruction's grounding and no-hedging rules
  (the pipeline fixes the label, not the model's voice), the agreement gate,
  anthology detection, the single-section (≤2 chapters) full-fetch path,
  ingestion, and stored data.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `rag-pipeline`: new requirements for (1) chapter buckets carrying only
  self-identified content (marker-driven reassignment with honest
  placeholders), and (2) the enumeration acknowledging roster gaps instead of
  silently omitting chapters the detection never found.

## Impact

- `src/secondbrain/rag/pipeline/_fallback_mixin.py` — `_generate_multi_chapter_summary`
  gains the pre-loop guard/reassign pass and the roster-gap note; both
  funnel callers (legacy multi-chapter and stored-tree paths) inherit it.
- `src/secondbrain/rag/pipeline/_structure_mixin.py` — heading-shaped
  section-marker extraction helper (module-level static, mirroring
  `_detect_chapter_openings` guards), plus new calibration constants beside
  `_CHAPTER_GATE_*`.
- No CLI/API surface changes; no changes to stored vector data; the streamed
  transcript and the stored answer stay byte-identical to each other (notes
  stream through the same `_on_chunk` path as headings).
- Tests: new `tests/unit/rag/test_chapter_bucket_labels.py`; regression
  acceptance replays the live treeless store for `story_mapping_epics_report.pdf`.
- Operational follow-up (out of scope here): re-ingesting the report to capture
  its structure tree exercises the already-shipped tree path.
