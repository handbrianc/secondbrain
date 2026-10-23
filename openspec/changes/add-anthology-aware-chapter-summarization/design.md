# Design: Anthology-Aware Chapter Summarization

## Verified failure record (from the live store)

Chapter map computed by the current pipeline for
`/data/workspace/uploads/Consolidated_Knowledge_Compilation.pdf` (120 pages,
real part openers on pp. 3, 13, 22, 37, 61, 66, 73, 77, 81, 86, 91, 95, 101,
106, 109, 115):

```
{5:(1,1), 6:(2,12), 7:(13,14), 8:(15,17), 9:(18,18), 12:(19,19), 13:(20,20),
 15:(21,25), 16:(26,30), 17:(31,32), 18:(33,10^6),
 1,2,3,4,10,11,14,19,20,21: (0,-1) sentinel}
```

Only ch9, ch13, ch17 landed correctly — by accident of title provenance. The
roster (21 entries) mixed titles from reports I.1 (ch 1–8, 11, 12), I.2
(ch 9, 10, 13–15), I.3 (ch 16–21). Pin provenance was traced with debug
instrumentation of the real run:

- pre-monotone candidates `{1:60, 9:18, 10:18, 12:12, 13:20, 14:20, 15:21,
  16:19, 17:31, 18:33, 19:34, 20:35, 21:21}`; `_select_monotone_pins` kept
  `{9:18, 13:20, 15:21, 17:31, 18:33, 19:34, 20:35}` — dropping the correct
  ch12@12 as a monotone violation;
- the `N.x` body scan pinned ch5@1 ("I.1 §§2.2, 7 · II.11 (BDD)…" on p1) and
  ch6@2 (front-matter cross-reference matrix, p2), ch21@52 ("21.9 min"
  availability-SLA table value);
- the loose-digit scan pinned ch7@13 (bare "7" in I.2's opening prose) and
  ch12@19 (p19 body text);
- interpolation filled ch8@15, ch16@26;
- the duplicate-first-word dedup then deleted ch19@34, ch20@35, ch21@52
  (first words "agentic"/"bridging"/"source" collide with ch17/ch13/ch15).

The document's true openers exist as clean heading-role chunks ("5 Step 3 —
Story Mapping: The Engine That Removes Vagueness" @p7, etc.), i.e. the data
needed for a correct map was present the whole time.

## 1. Anthology shape detector

New `_StructureMixin` method, called in `_iterative_query` after the source is
selected and the heading-chunk stream is fetched (reuse that fetch; no extra
storage round trip). Signals, all required:

1. **Part openers**: ≥3 heading-role chunks matching a part-opener pattern —
   roman/decimal part labels followed by a separator: `^[IVXLCDM]+ \. \d+
   [ ·—-]`, `^Part\s+[IVX\d]+`, `^Part\s+[A-Z]`. For the corpus compilation:
   16 openers (`I.1 ·` … `II.12 · Volume 11 — …`).
2. **Numbering restarts**: ≥2 parts whose first section heading inside the
   part is numbered `1` (e.g. I.1 §1 @p3 and I.2 §1 @p13 both restart).
3. **Scale**: ≥3 parts and each part ≥2 body-bearing pages.

False-positive analysis: single-book documents have no part-labeled headings
(UserManual uses "Chapter N" banners; PVE uses bare numbered chapters), so
signal 1 fails and the detector claims nothing. A false positive would need a
book with ≥3 "X.Y ·" headings *and* ≥2 restarts — at which point per-part
mapping is semantically the right model anyway.

On detection the anthology path returns before the roster/pinning machinery
runs; the legacy path is untouched.

## 2. Per-part chapter map and summaries

- Part ranges: opener-heading pages in document order; part spans
  `[opener_page, next_opener_page - 1]`, last part to end of document.
- Per-part roster: heading chunks within the part matching the existing
  section-title shapes; a section pins at its own heading page (±0; heading
  chunks are the reliable anchor in this shape). Sub-sections (`N.M`) group
  under `N`.
- Summaries: one call per part via the existing bounded-window machinery
  (`_split_bounded` / `_summarize_bounded` / `_on_chunk` streaming), bucket =
  body chunks in the part range with the same page-cap/per-part-limit sampling
  constants as the legacy multi-chapter path (page_cap 3, limit 8).
- Part heading format: `I.1 — <title> (pages 3–13)`. An empty part (no body
  chunks) emits the existing placeholder note.

Contract between modules (both lanes implement against it):

```python
# _pipeline.py builds, _fallback_mixin.py consumes
parts = [
    {
        "label": "I.1",  # part label as printed ("I.1", "II.12")
        "title": "From Vague Requirements to Well-Defined Epics",
        "start_page": 3,
        "end_page": 13,
        "sections": [...],  # per-part section map (for prompt context)
        "chunks": [...],  # sampled body chunks for the part
    },
    ...,
]
answer = self._generate_anthology_summary(parts)  # streams via self._on_chunk
```

Fallback when the detector misses an anthology (gate fires, §3): the legacy
path must NOT emit per-chapter output; it falls back to a whole-document
overview (`_generate_whole_document_overview(chunks)`: page-spread sample →
`_summarize_bounded` with an overview instruction) — honest output instead of
wrong-page chapters.

## 3. Chapter-range agreement gate

Runs on the legacy path only, right after `chapter_ranges_` is derived
(sentinel insertion included, before bucket filling):

- **Metric — evidence-pin divergence.** The pipeline already pins every
  chapter provisionally at its first `N.1` section-heading page
  (`evidence_pin_pg_`, in scope at the gate site) before any ToC override or
  scan runs — the strongest heading evidence the document offers. The gate
  compares each final range's start page against that evidence pin:
  a chapter agrees when `|final_start − evidence_pin| ≤ 2` (pins are
  documented provisional ±1; ToC-resolved offsets may shift one more page).
  Score = agreeing / compared (chapters present in both maps).
- **Evidence-conditional.** The gate runs only when ≥ 4 chapters are
  comparable. Documents whose headings carry no `N.1` shapes at all (e.g. the
  HCD report: 0 evidence pins) have no evidence to disagree with and keep the
  legacy path unchanged — the gate must not veto on absence of evidence.
- **Calibrated threshold (fixture baselines, `baselines.json`):** UserManual
  1.00 (18/18 within ±2), PVE 1.00 (19/19), compilation 0.25 (2/8,
  divergences −39/−13/−9/−32). Threshold 0.7 with ≥ 4 compared chapters.
- **On failure**: skip bucket filling and `_generate_multi_chapter_summary`;
  emit the whole-document overview fallback instead (§2). Sentinel-only maps
  (every range empty) already degrade via placeholders — the gate adds the
  missing protection for *populated but wrong* maps, which is the harmful case.
- **Rejected metric (recorded negative result):** squashed roster-title
  containment in the range's heading chunks. Measured on the fixtures:
  UserManual scores 0.278 (its docling-flattened ToC titles differ from the
  banner headings) while the compilation's garbage map scores 0.818 (its
  ranges happen to contain the very headings the bad pins came from). It
  vetoes the good book and passes the bad map — unusable.

## 4. Rider: roster titles preserve quoted phrases

`_derive_chapter_numbers`'s `bare_chapter_re` title class omits `"`
(`[A-Za-z0-9\s\-\(\),'/:.–—]{4,80}`), so `2 First Principles: What
"Well-Defined" Actually Means` captures only "First Principles: What". Extend
the class with `"` (and typographic quotes) — display-only; no pin logic
reads quotes.

## 5. Fixtures and regression evidence

- `tests/fixtures/chapter_map/<name>.json` — per-source chunk dumps (fields:
  `chunk_text`, `page_number`, `page_pos`, `chunk_role`, `element_type`,
  `source_file`) exported once from the live Qdrant store for: UserManual,
  pve-admin-guide, hcd report, the compilation.
- `tests/fixtures/chapter_map/baselines.json` — pre-change legacy chapter
  maps (ranges + bucket first-chunk pages) for the reference books and the
  gate scores, captured before any code change.
- Tests assert: reference books' legacy maps unchanged by this change; the
  compilation is detected as an anthology and maps 16 parts with correct
  boundaries; the gate passes known-good books and vetoes the synthetic
  garbage map; end-to-end `_iterative_query` on the compilation fixture
  streams per-part summaries with no placeholder notes.

## 6. Risks

- **Gate rejects a legit book** → mitigated by calibration on the two corpus
  books + fixtures in CI; threshold conservative (0.6) and gate only skips the
  *chapter* presentation (whole-doc overview still answers).
- **Detector hijacks a single book** → requires part-opener headings AND
  restarts; corpus negatives tested.
- **`_iterative_query` complexity** → additions are cohesive call sites;
  logic lives in new methods (repo intentionally defers C901; audit-review
  model documented in AGENTS.md).
