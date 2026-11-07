# Design

## Context

The affected document (`hcd_best_practices_report.pdf`, 25 pages, 21
chapters) is stored with 158 body chunks, page-granular annotations, and an
empty structure tree despite a complete 56-node PDF outline. Three defects
were root-caused against the live store; the fixes split into an ingest lane
and a query-time lane with disjoint file scopes.

## Decisions

### D1 — Position-aware annotation state machine (A1)

`structure_annotate.py` currently assigns chunk ownership from outline page
spans. The machine adds in-chunk evidence, evaluated in stored-chunk order:

- Scan each chunk's text for a numbered chapter-heading form via
  `heading_forms` (dotted `N.M` and dot-required bare `N.`).
- A form found in the chunk's **first half** (character offset < len(text)/2,
  measured at the form's line start) anchors the chunk — and subsequent
  chunks until the next evidence — to that chapter.
- A form found in the **second half** makes the chunk the last one of the
  prior chapter (pending switch); ownership changes starting with the next
  chunk.
- Page-granular outline spans fill the gaps only where no in-chunk evidence
  exists; spans never override anchored evidence. Chunks with no heading
  forms anywhere keep today's span behavior byte-identically (guards the
  re-annotation regression surface).
- The same machine serves both capture paths (outline tree and docling
  headings) because it keys on chunk text, which also fixes the same-page
  flaw (chapters 3 and 4 both span `pg4` in the outline).

### D2 — Shared `document/heading_forms.py` contract (A2)

One module owns numbered-heading recognition and title extraction so ingest
synthesis and query-time guards cannot drift:

- `match_numbered_heading(line) -> (chapter: int|None, section: int|None,
  rest: str|None)` — dotted `N.M` section form; bare `N.` chapter form with
  the dot REQUIRED ("7 Wikipedia" is not a heading; "9. Krippendorff's" is).
  Negative guards carried from `_chunk_section_marker`: dot-leader rows,
  trailing page numbers, inline prose positions.
- `capture_title(lines) -> str|None` — line-boundary capture: the heading's
  own line, plus at most one continuation line when the first line ends
  without sentence punctuation and the next line does not itself match a
  heading/list form. No `\s`-class cross-line gluing.
- `trim_title(title, cap) -> str` — word-boundary trim at the cap (never
  mid-word).
- Pure functions, stdlib-only, no imports from pipeline or storage code.

The orchestrator writes this module and its unit tests before the lanes
dispatch; lanes integrate it.

### D3 — Synthesis integration (A2)

In `structure_capture.py`, after parser headings are collected
(`capture_docling_headings` → `_build_nodes_from_headings`), scan the
document text stream for chapter forms the parser missed and synthesize
heading nodes for them. Parser-produced nodes win by number: a synthesized
node is added only when no parser node carries the same chapter number. The
docling text iteration (`_iter_docling_texts`) supplies the stream. For the
HCD report this recovers chapters 3, 5, 9, 12, 13, 14, 20.

### D4 — Tree persistence diagnosis and observability (A3)

Diagnosis first: reproduce the original ingest path in a fixture and locate
where the 56-node capture is dropped (capture → persist →
`structure_sqlite.save_structure`). Two outcomes:

- A wiring defect exists → fix it; persistence failure/zero-node write is
  logged with source and node count.
- The original ingest predates tree persistence (stale data) → no wiring
  defect; still add the zero-node/failed-persist log so loss is never
  silent.

Either way the remedy for the affected document is a re-ingest — no
tree-rebuild-from-store code is written.

### D5 — Marker floor 20 → 3 (B1)

`_BUCKET_MARKER_MIN_PAGE` in `_structure_mixin.py` drops to 3. The floor's
job is excluding title/ToC front matter (pages 1–2); the dot-leader and
page-suffix guards already carry the real noise defense, so 20 is
over-calibrated for short reports. Expected churn: baseline windows in
`tests/unit/rag/_chapter_fixture_storage.py` that relied on the floor are
updated deliberately, with the diff reviewed.

### D6 — Roster-title hygiene (B2)

`bare_chapter_re` keeps its dot-optional number part (the dot-less
"2 First Principles" shape is a shipped spec — quoted-phrase scenario — and
must stay capturable); the fixes, as built after characterization feedback:
the number→title separator admits horizontal whitespace only, so the title
must sit on the number's own line (footer-adjacent empty list-marker runs
"1. ⏎ 2. ⏎ …" plus running footers produced phantom chapter claims when the
separator could cross the newline) — with one shipped carve-out: the banner
shape (a number line with no title, directly followed by a dotted `N.M`
section heading) still captures cross-line through a dedicated banner
pattern feeding the existing dotted-section guard, which converts it to an
empty-title entry exactly as before ("1⏎1.1 Central Management" keeps its
chapter slot; the shipped dotted-title-guard tests pin it). The title class
stops at line boundaries (no `\s` cross-line gluing) with a raised cap (200)
that lets the word-boundary trim decide the final length; at most one
bounded continuation line joins via `heading_forms.capture_title`; the
captured title is trimmed at a word boundary instead of the mid-word
80-class cut; and the citation-shape guard
(`heading_forms.looks_like_citation_row`: spaced en/em dash plus a compact,
comma- or year-bearing, or unclosed parenthetical) rejects source-register
rows like "7 Wikipedia — The Design of Everyday Things (D. Norman,
1988/2013)" without banning prose parentheticals ("(The Basics)"). A
rejected row `continue`s without consuming the `seen` slot, so a real
heading elsewhere can still claim the chapter (the originally planned
earliest-page match preference is dropped: rejected rows already free the
slot, and footer phantoms claim earlier pages, so page-preference would not
have helped). Cleanly-parsing documents must produce byte-identical titles.

### D6-r3 — "the"-carve-out restores the hcd legacy roster

With the register row citation-rejected (the intended fix), chapter 7's real
heading "7. The IDEO Field Guide: Mindsets, Phases, and Methods" turns out
to be the ONLY claim candidate left — and it is collaterally rejected by the
pre-existing `legal_starts` article ban ("the"; installed for license/boilerplate
headers like "1. The Project Gutenberg eBook of …"). Left alone, the hcd
legacy roster shrinks 6..21 → 8..21 (ch6 dies as a run-filter singleton
without ch7; ch1/ch2 are real claims that stay outside the longest
consecutive run) — an unintended side effect of the approved citation fix.
The carve-out: a `legal_starts` "the" match is allowed when the bare-number
match is dot-shaped (separator carried the dot) AND the captured title
contains a colon — real chapter titles carry colons ("The IDEO Field Guide:
…"), license/boilerplate headers do not ("The Project Gutenberg eBook of
Alice…"). Expected consequences, verified empirically before acceptance:
pre-filter {1,2,6,7,8..21} → longest run [6..21] restored (ch6 survives,
chapters 1/2 stay outside the roster, the shipped coverage-note scenario
naming 1–5 holds), ch7's title becomes the real heading (the ONE documented
baseline edit — the baseline records the register-derived polluted title),
and ch18/19 ranges must return to (19,19)/(20,21); the four-book probes
(user-manual, pve-admin-guide, knowledge-compilation) must stay
byte-identical. Collateral license-header risk is bounded by the colon gate
and verified by the shipped boilerplate/license tests.

### D6-r4 — Oracle reconciliation: bless the r3 legacy state (α)

The carve-out's empirical gates resolved differently than D6-r3 predicted:
the colon gate admits ch3 and ch5 as well (their headings are textually
identical to ch7's shape — dot + colon + "The"), the roster becomes 5..21
(longest-consecutive-run filter drops the front-matter-contaminated
[1,2,3]), and ch5/ch6 both claim page 5, so ch6 gets the enumeration
sentinel (0,-1). The 18/19 boundary shift is roster-independent (present in
every B2 state). Oracle ruling (session `ses_e6897f2eeffe1GzIGanEg8aOCe`):

- **Bless r3** (roster 5..21, ch5 admitted, ch6 sentinel, ch7 titled from
  its real heading). γ (revert) is a strict regression — ch6 AND ch7
  vanish; β (intra-page pins in the fallback) is the right mechanism in
  the wrong change — filed as a follow-up, not built here.
- **Baselines record behavior, not truth** — regenerate the hcd baseline
  section from the r3 state with diffs classified by provenance:
  *ground-truth-verified* (register-row death; ch5/ch7 real titles;
  ch5's own content under ch5) vs *artifact-removal shifts, accepted*
  (the 18/19 boundary move: the old @20 pin was sustained by the removed
  `\s` cross-line gluing artifact; the new provenance — a 150-char
  head-window tier plus a later-tier @21 pin — is understood as a
  mechanism but unvalidated as correct).
- **18/19 deferred**: not fixed in this change. Follow-up (new change):
  complete the tier diagnosis using the live store's position-aware
  annotations as a free ground-truth oracle, then design intra-page pins
  against that oracle, then regenerate baselines once.
- **ch3's run-filter drop is documented behavior**: the change strictly
  improved ch3 (banned → admitted; the coverage note names it); [1,2,3]
  losing to [5..21] is the pre-existing filter working at coarse
  fidelity, and even a perfect ch3 pin could not be represented (ch3/ch4
  share page 4 — the same page-granular limit as ch5/ch6).
- **Named residual (accepted)**: the render-time bucket guard recovers
  only the heading-bearing page-5 chunk; ch6's marker-less phase-table
  body (page-6 chunks) derives into ch7's bucket and cannot be recovered
  by text guards — the strongest argument for the intra-page-pin
  follow-up. The live document is unaffected (tree-driven).

### D8 — Round-2 replay defects (D-1/D-2/D-3) and the 18/19 resolution

Live replay #1 (task 4.3 first run) exposed three defects; diagnosis tied
each to one side of the ingest/query boundary:

- **D-1 (query-time)**: `_guarded_tree_chapter_map`'s degeneracy check
  counts the number-less document-title node (kind=chapter, number=None,
  pages 1-1, a real bookmark every outline tree carries) as a lost
  chapter, so `len(ranges) < len(kept)` fires for every tree with a
  title node → empty map → the replay ran the LEGACY path (proven by
  glued titles + the "1–4" coverage note). Fix (Lane B): the degeneracy
  comparison exempts number-less ROOT front matter preceding the first
  numbered chapter — interleaved number-less nodes still count, so the
  shipped ToC/degenerate guards keep their semantics (all four pinned
  tests unchanged). No re-ingest needed.
- **D-2 (ingest)**: formless chunks follow outline-span fill even when an
  evidence-armed sticky assignment under-covers across a page boundary —
  ch10's page-11 content annotated into sec11.02/ch11; page-13 ppos0
  annotated ch15 instead of sticky ch13. Fix (Lane A): evidence-armed
  assignment carries through heading-free chunks across page breaks,
  ahead of span fill, until the next chunk-anchored heading re-arms.
  Gates: 32 pre-existing annotate tests unmodified; new cross-page tests.
- **D-3 (shared)**: `capture_title` joined the next line for ANY
  non-sentence-terminal title, gluing body prose into roster titles
  (ch12/13/16/18/20/21). Verified rule: join only when the title ends
  dangling (comma, dash, open parenthetical, trailing connective word) OR
  the next line is a single word (a wrapped heading's orphan word —
  "… Common" + "Failures", "… from HCD" + "Theater"). Corpus-verified:
  all six true joins preserved, all glue shapes (3-7-word body lines)
  rejected; the three clean books stay byte-identical (probe
  `/tmp/opencode/titles_pre_d3.json` vs `titles_post_d3b.json`).
- **18/19 resolved as a D-3 side effect** (supersedes the D6-r4
  deferral for the boundary): ch19's real heading is physically on page
  20 (chunk char 326; the stored tree's ch19 node spans 20-21 —
  double-sourced ground truth). The pre-D-3 glued title needle spanned
  the `\ufffeFirst Tooling)` corruption and could not match the real
  heading, so the title-anchor tier failed and a later tier pinned @21;
  D-3's short needle ("… (OpenAPI") matches and pins @20. Ranges
  18:(19,19), 19:(20,21) are ground truth. The intra-page-pin follow-up
  remains scoped to the same-page chapter starts (ch5/ch6, ch3/ch4) and
  ch6's marker-less page-6 residual.

### D7 — Scope boundaries

- Tree-rebuild-from-store is out of scope (remedy = re-ingest from
  `/home/bchand/hcd_best_practices_report.pdf`; afterward delete the stale
  `/data/workspace/uploads/hcd_best_practices_report.pdf` source key to
  avoid duplicate sources).
- Two fixer lanes run in parallel with disjoint scopes:
  Lane A (ingest): `structure_annotate.py`, `structure_capture.py`,
  `tests/unit/document/`.
  Lane B (query-time): `_structure_mixin.py`, `tests/unit/rag/`.
- Untouched: the user's in-progress edits (`logging/slow_call.py`,
  `tests/test_logging/test_slow_call.py`, the `fix-chat-session-integrity`
  spec delta) and all shipped `chapter-label-integrity` guard behavior.

## Risks / Trade-offs

- **Churn in fixture baselines** (D5): accepted; reviewed diff.
- **State-machine ambiguity** (D1): a heading form inside quoted/prose text
  could mis-anchor; mitigated by reusing the line-initial + noise guards and
  by the "no heading forms → byte-identical" regression case.
- **Synthesis over-reach** (D3): numbered list items could synthesize false
  headings; mitigated by the dot requirement, line-initiality, and
  list-marker guards in `heading_forms`.
- **Live replay cost**: each overview replay is a real LLM call (~1 min) on
  a scratch session id; one replay is budgeted after the suites pass.

## Migration

No stored-data migration. The affected source is re-ingested from the
original file; the stale upload-path key is deleted after verification.
