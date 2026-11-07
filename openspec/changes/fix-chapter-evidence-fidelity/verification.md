# Verification — fix-chapter-evidence-fidelity

## A3 diagnosis: tree persistence (stale data, no wiring defect)

- The capture→persist wiring landed together in commit `28f3205` (2026-10-24)
  and is structurally unchanged since (git `-S`); the sync CLI ingest path
  persists the captured tree and annotates points correctly (evidence below).
- Root cause of the observed empty store: the affected source's original
  ingest predates tree persistence (the host DB
  `~/.secondbrain/secondbrain.db` held zero structure rows). Not a wiring
  defect — outcome (2) of design D4.
- Silent-drop points found during diagnosis and closed by observability:
  the store-unavailable return in `_persist_worker_structure` (now warns
  with source + node count) and the zero-node-after-successful-save case
  (now warns). The async twin (`_async.py`) mirrors both warnings after the
  same diagnosis flagged its silent drops. Report-only: the wait-bound
  expiry path discards worker results wholesale (no tree exists to persist
  at that point).
- New fixture `tests/unit/document/test_structure_persistence_wiring.py`:
  capture→persist through the real `_process_parallel_with_progress` and a
  real `StructureStore` — happy path reaches the store; zero-node / failed /
  store-unavailable each warn with source and node count while ingest still
  succeeds.

## Store-state evidence and remedy (task 4.2)

Pre-remedy state (probed 2026-11-01, host):

- One qdrant source key `/data/workspace/uploads/hcd_best_practices_report.pdf`
  with 160 points re-annotated at 08:28 by pre-change code — the page-10
  Krippendorff chunk carried `node_id=ch10` (the page-granular defect).
- The structure tree existed only in the container DB
  (`/data/secondbrain/secondbrain.db`, 56 nodes); the host DB the CLI and
  chat read was treeless, so every host-side chat ran the legacy path on
  this document.

Remedy executed (delete-first: text-hash dedup could otherwise leave a
re-ingested key with zero stored points):

1. `secondbrain delete --source /data/workspace/uploads/hcd_best_practices_report.pdf --yes`
   → "Deleted 160 chunk(s)".
2. `secondbrain ingest /home/bchand/hcd_best_practices_report.pdf` → success
   (160 points stored; one embedding batch, 10.6 s).

Post-remedy store (probed):

- Exactly one source key: `/home/bchand/hcd_best_practices_report.pdf`.
- Host-DB tree: 56 nodes, 21 top-level chapters, numbers 1–21 complete
  (bookmark outline; synthesis is not needed on the outline path).
- Position-aware annotation confirmed: the page-10 chunk carrying
  Krippendorff content is annotated `node_id=ch09`, `chapter_id=9`,
  `heading_path="Chapter 9 — Krippendorff's Semantic Turn: Designing for
  Meaning…"` (previously `ch10`).
- Note: the container DB retains its stale tree row for the deleted key
  (a different SQLite file, not consulted by host chats) — harmless
  residue, recorded for completeness.

## Reconciliation: the legacy hcd baseline (oracle ruling, D6-r4)

The "the"-carve-out's empirical gates resolved differently than predicted:
the colon gate admits ch3 and ch5 as well (their headings are textually
identical to ch7's — dot + colon + "The"), so the legacy roster becomes
5..21 (the longest-consecutive-run filter drops the front-matter
contaminated [1,2,3]), and ch5/ch6 both claim page 5, so ch6 takes the
enumeration sentinel (0,-1). The 18/19 boundary shift proved
roster-independent. @oracle ruled (design D6-r4):

- **Bless the r3 state**: roster 5..21, ch5 admitted with its real heading,
  ch6 sentinel with its real title, ch7 titled from its real heading.
  Reverting the carve-out was rejected as a strict regression (ch6 AND ch7
  would vanish from the legacy roster); intra-page pins rejected for this
  change (right mechanism, wrong change — filed as a follow-up).
- **Baseline diffs are classified by provenance**, not "blessed" as truth:
  ground-truth-verified (register row can no longer title ch7; ch5/ch7
  real titles; ch5's content under ch5) vs artifact-removal shifts,
  accepted (18/19: the old @20 pin was sustained by the removed `\s`
  cross-line gluing artifact; the new provenance — a 150-char head-window
  tier plus a later-tier @21 pin — is understood but unvalidated as
  correct).
- **18/19 deferred** to a follow-up (filed on the knowledge backlog and
  scoped in design D6-r4; not scaffolded as an OpenSpec change because its
  spec deltas require the oracle-informed design first): complete the tier
  diagnosis using the live store's position-aware annotations as a
  ground-truth oracle, then design intra-page pins against it, then
  regenerate baselines once.
- **ch3's run-filter drop is documented behavior**: the change strictly
  improved ch3 (banned → admitted, named by the coverage note); even a
  perfect ch3 pin could not be represented (ch3/ch4 share page 4).
- **Named residual (accepted)**: ch6's marker-less phase-table body
  (page-6 chunks) derives into ch7's bucket on the legacy path; the
  render-time bucket guard recovers only the heading-bearing page-5
  chunk. The live document is unaffected (tree-driven).

## Lane results

- Lane A (ingest: `structure_annotate.py`, `structure_capture.py`,
  `heading_forms.py` integration): `pytest tests/unit/document -q` → 467
  passed (all 32 pre-existing annotate tests and 196 capture/wiring tests
  unmodified — the byte-identity gate held); ruff clean, mypy clean.
  Real-file proof: all 21 chapters + 23 outline section forms survive the
  synthesis scan on the real PDF; both observed false-positive shapes are
  rejected.
- Lane B (query-time): B1 floor proven byte-identical on all four books
  (three-way probe); B2 title hygiene shipped through r1 (on-line anchor
  — footer/empty-marker phantoms dead), r2 (banner carve-out — shipped
  dotted-title-guard tests restored), r3 (the-carve-out — register row
  and real heading verified at unit and document level); 55 bucket-label
  tests green; ruff/mypy clean. Baseline regeneration per the oracle
  ruling in flight (B2-r4).

## Round 2: live replay #1 defects and the D-3 resolution (task 5.1)

Replay #1 ran the LEGACY path (defect D-1, in Lane B's hands) and showed
glued roster titles. D-3 (shared module, this session):

- Defect: `heading_forms.capture_title` joined the next line for any
  non-sentence-terminal title — body prose glued into roster titles
  (ch12/13/16/18/20/21).
- Rule shipped: one continuation line, taken only when the title ends
  dangling (trailing comma, dash, open parenthetical, or trailing
  connective word) OR the next line is a single word (a wrapped heading's
  orphan word). All six verified true joins preserved (IDEO "…Phases,
  and"+Methods; "…Make,"+Validate; "…Designing for"+Meaning; ch6 "…Common"
  +Failures; ch15 "…HCD"+Theater; ch9 earlier verified); all glue shapes
  (3-7-word uppercase body lines) rejected.
- Four-book derived-title probe (`/tmp/opencode/probe_titles.py`): the
  three clean books byte-identical pre/post (old join rules ≡ new rules on
  every site — no single-word-continuation sites exist there); hcd titles
  now match the tree's clean node titles for ch6/12/13/15/16/18/20/21;
  ch19 truncates at "(OpenAPI" (source `\ufffe` corruption — recorded
  verbatim).
- **18/19 boundary resolved as a D-3 side effect** (supersedes the D6-r4
  deferral): ch19's real heading is physically on page 20 (chunk char 326;
  stored tree's ch19 node spans 20-21 — double-sourced). The glued title's
  whitespace-insensitive anchor needle spanned the `\ufffeFirst Tooling)`
  corruption and could not match the real heading, so the title-anchor
  tier failed and a later tier pinned @21; D-3's short needle ("…
  (OpenAPI") matches and pins @20. Ranges 18:(19,19), 19:(20,21) are
  ground truth; hcd baselines regenerated (ranges/buckets/titles) with the
  provenance block in `tests/unit/rag/_chapter_fixture_storage.py`
  upgraded accordingly (boundary moved from artifact-accepted to
  ground-truth-verified; the intra-page-pin follow-up stays scoped to the
  same-page chapter starts and ch6's marker-less page-6 residual).
- Tests: `heading_forms` 48 passed (5 new D-3 tests); rag gluing
  characterization rewritten to the sharpened rule (complete heading +
  body → no join; dangling comma wrap → one-line join);
  `tests/unit/rag -q` → 693 passed; `tests/unit/document -q` → 475
  passed; ruff/mypy clean.

### D-1 (Lane B): number-less title root exempt from the degeneracy check

`_guarded_tree_chapter_map`'s degeneracy comparison
(`len(ranges) < len(kept)`) counted the number-less document-title root
node (kind=chapter, parent_id=None, pages 1-1) as a lost chapter, so every
outline tree with a title node — including the perfectly healthy hcd tree —
degenerated to `({}, {})` and the replay ran the legacy path. Shipped
exemption: number-less ROOT (`parent_id is None`) kept nodes PRECEDING the
first numbered kept node are front matter and exempt; with no numbered kept
node nothing is exempt (the 19-survivor pinned test still degenerates);
interleaved number-less nodes still count. The probe loop, the plain-map
build, the repeated-number bail-out, and the log line are byte-unchanged.

- Gates: the four shipped ToC-guard/degeneracy tests ran UNMODIFIED
  against the changed code (7 passed at lane time; `git diff` shows zero
  changed lines in their bodies); two new tests — the hcd shape (title
  root + 21 numbered chapters → guarded map returns all 21 entries, no
  degenerate log) and the interleaved variant (second number-less root
  between chapters → still degenerates).
- Live proof: the guarded map on the live hcd tree now returns the full
  21-chapter roster (1..21, no sentinels) — `_tree_chapter_query` takes
  the tree-driven path; the legacy scan does not run.
- `tests/unit/rag -q` → 695 passed (693 + 2); ruff/format clean; mypy
  clean on `_structure_mixin.py`.

### D-2 (Lane A): evidence-armed carry across the page break

An `armed_owner` slot in `_annotate_all` (ordered page mode only): armed
by a first-half heading anchor, by the switch a second-half heading starts
(effective next chunk), or by the legacy forms anchor; cleared only by new
anchor/switch evidence (never resurrects); the armed assignment carries
through subsequent heading-free chunks — across page boundaries, ahead of
outline-span fill — via `_armed_candidate` (armed node exists, has a
`page_start` at or before the chunk position); offered only to heading-free
chunks; a chunk with no containment candidates stays unannotated
(refreshable); fill/sticky assignments arm nothing; unordered and audio
paths never engage.

- Gates: all 39 pre-existing annotate tests ran UNMODIFIED (ran
  immediately after the source edits, before appending tests); 8 new
  cross-page tests (`TestArmedCarryAcrossPageBreak`) reproduce the live
  ch10 and ch13 shapes; `tests/unit/document -q` → 483 passed; ruff/mypy
  clean.
- Live proof (task 5.4 refresh): `refresh_structural_payload` on the live
  hcd key with the unchanged tree (no re-ingest) wrote 27 points, of which
  exactly the three diagnosed identity corrections: page-11 chunks 0-1
  (pre-ch11-heading) `sec11.02 → ch10`, page-13 chunk 0 `ch15 → ch13`; no
  collateral identity changes; second refresh → 0 (idempotent). The other
  writes are diff-gate completions against the pre-change annotation run.

### Refresh-wiring reconciliation (test_qdrant_structure_refresh.py)

The armed carry reached two pre-existing refresh tests (outside both
lanes' gates); reconciled with intent preserved, zero removed test lines
in lane files:

- `test_annotates_legacy_points_and_completes_partial_annotations`:
  `legacy-2` (page 11, heading-free) now asserts the armed-carry identity
  (`sec05.02`, section 5.2, chapter 5) even though page 11 lies outside
  the section's span — the D-2 precedence, documented in-test; refreshed
  == 3 and the idempotent second refresh == 0 are preserved.
- `test_set_payload_failure_degrades_to_partial_count`: under the armed
  carry all three points had shared one annotation group (one
  `set_payload` batch), so the fail-on-second-batch hook never fired. The
  page-11 point now carries its own "5. Installing" heading line (a
  chapter-5 annotation distinct from the 5.2 group), restoring the two
  batch groups `[2, 1]`, the failed second batch, the partial count 2,
  and the refreshable failed point. File: 16 passed; ruff/format clean
  (one mypy union-attr note on an untouched pre-HEAD line — pre-existing,
  out of scope).

### Live replay #3 — the tree-driven run (tasks 4.3 and 5.4)

`secondbrain chat "summarize by chapter hcd best practices report"
--session chapter-evidence-verify` after D-1/D-2/D-3 + live refresh
(excerpt at `/tmp/opencode/replay3.txt`; three runs total — #1 exposed
D-1/D-2/D-3, #2 mid-round-2 still legacy, #3 final):

- **Tree-driven path confirmed (D-1)**: all 21 chapters enumerated
  (1..21), no coverage note. Decisive: chapter 19's title renders as
  "Agentic API-Contract Documentation (OpenAPI-First Tooling)" — the full
  stored tree-node title, which only exists on the tree-driven path (the
  legacy derivation truncates at "(OpenAPI" on the source `\ufffe`
  corruption).
- **D-2 confirmed in output**: chapter 10 carries real page-11 content
  (naming, error messages, and user stories as design surfaces — the
  chunks the round-1 replay mis-annotated into ch11); chapter 13 carries
  its page-12 content plus the page-13 flowed takeaway ("small, repeated,
  well-scripted tests beat occasional large ones") with no ch15 leakage;
  chapter 15 is pure governance diagnostics (five ISO-derived audit
  questions).
- **D-3 confirmed in output**: roster titles clean everywhere — ch6
  "…Working Table and Common Failures", ch15 "…from HCD Theater",
  ch12 "Running Usability Testing Well", ch13 "Where HCD Pays Off — and
  Where It Doesn't", ch16 "Quick-Reference Checklist", ch20 "…(Companion
  Report)", ch21 "Source Register" — no glued body prose in any title.
- **Accepted residual, visible and recorded**: chapter 6's summary is
  thin (its marker-less page-6 table body still derives into ch7's
  bucket); recovery requires the intra-page-pin follow-up (knowledge todo
  `0a501dd6`), out of scope here. Chapter 9 summarizes under its own
  heading as required by the original acceptance line.

### Round-2 suite totals

`tests/unit/rag + tests/unit/document` → 1178 passed; storage refresh
file → 16 passed; full fast suite `pytest -m "not integration and not
chaos" -q` → **4527 passed, 3 skipped, 0 failed**; `openspec validate`
green (known pre-existing 2.6 numbering warning).
