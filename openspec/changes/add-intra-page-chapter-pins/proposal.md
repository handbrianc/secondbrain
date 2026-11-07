# Proposal

## Why

The legacy (treeless) chapter fallback derives page-granular chapter ranges,
so two chapters whose headings start on the same page cannot both be
represented. On the hcd-report fixture the derivation scan claims 21 chapter
headings, and five pairs share a page — {3,4}@4, {5,6}@5, {9,10}@10,
{12,13}@12, {14,15}@13. `_select_monotone_pins` (`pg_j >= pg_i` → reject)
structurally drops the later chapter of every pinned pair (ch6, ch10, ch13,
ch15 — exactly the four `(0, -1)` sentinel ranges in the shipped baselines),
and ch3/ch4 never reach the pin tiers at all. A sentinel chapter's bucket
stays empty except for the marker guard's heading-bearing chunks, and its
content lands in a neighbor's bucket: ch6's marker-less page-6 phase table
("Phase Methods Output Common failure…") derives into ch7's bucket. This was
accepted as a known limitation when `fix-chapter-evidence-fidelity` shipped
(D6-r4) because the live document is tree-driven; this change removes the
limitation for treeless documents.

Two detection defects compound the page-granularity limit:

1. **ch4 is never detected.** Its real heading "4. The Four Phases of HCD
   Work" (page 4, pos 2, char 259) is rejected by the D6-r3 "the"-carve-out,
   which admits a dot-shaped "The …" title only when the captured title
   carries a colon; ch4's title has none. (The backup register-row claim for
   number 4 on page 23 dies on `title[0].islower()`, so nothing claims ch4.)
   With ch4 undetected, the post-validation run filter in
   `_derive_chapter_numbers`' tail (longest consecutive run ≥ 60% of
   entries) drops the {1,2,3} prefix run, and chapters 1–4 vanish from the
   roster entirely.
2. **Detected chapters get no pins.** Every pin tier is blind to chapters
   1–4: the `chapter_n_re` scan finds no "Chapter N" text;
   `_detect_chapter_openings` skips every page < 20; the sec-header
   head-window scan finds no `N.M` header in the first 150 chars of their
   chunks; the loose-digit rescue floors at page ≥ 10. The derivation scan
   itself sees each claimed heading with its page, page_pos, and character
   offset — and throws the position away.

## What changes

- Pass-2 bare-number claims record the claim's intra-page position (page,
  page_pos, character offset, first/second half). The "the"-carve-out
  admits dot-shaped "The …" titles without a colon unless the title matches
  sentence-case license vocabulary, and tail-truncated captures (a title
  class that runs to the chunk's last character) defer to complete captures
  so the spurious "7. The IDEO" page-6 fragment cannot steal ch7's title.
- `_derive_chapter_numbers` returns the claim map; the pipeline gains a
  fill-only claim pin tier (a roster chapter no other tier pinned gets its
  claim page, behind the usual guards), so ch1–3 pin at pages 2–4.
- Same-page starts and mid-page boundary headings become intra-page cuts.
  Bucket admission splits the shared page at the cut with the
  first-half/second-half rule mirroring `structure_annotate`, with one
  refinement the live oracle dictates: a second-half boundary chunk stays
  with the previous chapter only while that chapter's pre-extension range
  still contains the cut page.
- Range ends extend onto the next chapter's cut page when pre-heading chunk
  positions exist there (ch6 gains page 6 up to ch7's heading); roster
  chapters with a claim but no page pin gain a real recovered range instead
  of the `(0, -1)` sentinel.
- Baselines regenerate once. The legacy-derived split is verified against
  the live tree annotations captured during diagnosis (the ground truth the
  follow-up todo names).

## Scope

- Query-time legacy path only (`_structure_mixin.py`,
  `_pipeline.py`). The tree-driven path, ingest, and stored annotation are
  untouched; the live hcd document stays tree-driven and its answers do not
  change.
- Non-goals: section-level cut evidence beyond what the pin tiers already
  see (the single-chunk p6.p2 divergence from the live oracle is documented
  and accepted in design.md); the sentinel behavior of chapters with no
  claim at all; the probe-ranking question tracked separately in
  `fix-chapter-heading-probe-rank`.
