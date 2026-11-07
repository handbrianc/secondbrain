# Verification — fix-chapter-heading-probe-rank

## Diagnosis correction (the todo's premise, corrected with evidence)

Project todo d4fd93ec recorded: "with a real top-k probe, a dense page's
body chunks can all outrank a lone chapter heading, so that chapter
silently drops from the roster". The diagnosis reproduced the drop
end-to-end at unit level (dense book from
`test_chapter_window_purity.py::TestDensePageDocumentOrder` rerun with the
REAL `_probe_document_structure`: probe returns 18/18 chunks including
ch3's heading; roster {1,2}; flow degrades into `single_section_mode`'s
two-chapter lossless fetch that absorbs ch3's page) — and found **no
ranking exists anywhere in the probe chain**. The probe is a
metadata-filtered, page-ascending scroll with a limit in every
implementation (Qdrant scroll sorted by page_number; mock, protocol, and
both test doubles alike). The drop's actual decision point is the
"Chapter N" ceiling in `_derive_chapter_numbers`: pass 1 captures the
dense banner's "Chapter 2 …" → `auth_max=2`; pass 2 then refuses ch3's
bare-number heading (a real `chunk_role="heading"` chunk) at the silent
ceiling guard. The variant matrix (design.md) proves the ceiling is the
decision point: V3/V4 (moving `auth_max`) restore {1,2,3}; V6 (heading
merge alone) does not; density is irrelevant. Double silence confirmed:
the ceiling logged nothing, and the D5 gap note scans only
`1..max(roster)`.

The todo's candidate fix ("reserve a slot for heading/roster evidence per
chapter in probe ranking, or floor chapter headings' rank") has no ranking
to act on; its intent lands at the derivation instead.

## Implementation results

- **D1 role-gated exemption**: the bare-number and banner loops' ceiling
  clause refuses above-ceiling numbers only from chunks whose role is not
  `heading`; `ft_catch` ToC-row captures keep the unconditional ceiling;
  the tail-deferral post-scan keeps its unconditional ceiling too (a
  truncated above-ceiling capture would claim a corrupt title — refusal
  is safer and now logged). All other guards untouched.
- **D3 surfacing**: every ceiling refusal logs
  `"Ceiling refused chapter %d for %s (bare|banner|toc-row match)"`;
  range/`seen` checks run first so already-rostered numbers don't log
  spurious refusals.
- **D2 heading channel**: the derivation sample merges
  `find_structural_chunks(chunk_roles=["heading"], source_prefix=…)`
  probe-independently (dedupe by chunk id, probe copy preferred,
  page order preserved, the opener scan's exact error shape for degraded
  storage). An empty probe with a non-empty heading scan now proceeds to
  derivation (degenerate probe-independence, accepted in design.md).
- **Dense book, real probe**: roster {1,2,3}; ranges 1:(20,29),
  2:(30,39), 3:(40,…); ch3 bucketed `[(41, 0)]`; ch2's window stays on
  {30,31}; three roster lines; no coverage notes; **no single-section
  degradation** (3 chapters > 2 → round-robin).

## Corpus reconciliation (task 3.1)

Fixture probe before/after
(`/tmp/opencode/probe_apply_actuals.json`): all four books' rosters,
titles, and good-nums **byte-identical** for both the probe-only and the
merged (end-to-end) sample; 0 ceiling refusals logged, 0 above-ceiling
heading-role bare/banner matches observed; `baselines.json` untouched —
no regen needed. The exemption widens admission only where a real
heading-role chunk sits above a labeled ceiling; no fixture has one.
S5 spot-check: claimed titles byte-identical in all four books.

## Test reconciliation (sanctioned, reviewed by the orchestrator)

`test_pipeline.py::test_spaced_title_backfill_replaces_glued_roster_title`
pinned `_probe_document_structure` to two ToC rows, artificially hiding
the stub storage's heading chunks from the derivation — the dependency D2
removes (with the real probe, the pre-B sample already contained those
headings, and the pre-B unpinned run yields the same roster {4} the
post-B pinned run now yields). Reconciled: setup lines only — headings
switched to the sibling's glued-label convention (defeats `chapter_n_re`,
`auth_max` stays 0, backfill machinery stays under test) and the probe
re-pinned to `[*toc_probe, *headings]` (the real probe's shape). All
three assertion lines byte-identical and passing; premise-change comments
added. No other existing test touched
(`git diff` on `test_chapter_window_purity.py`: pure append, 0 removed
lines).

## Gates

- `pytest tests/unit/rag -q` → **730 passed, 0 failed** (8 new tests:
  `TestHeadingCeilingExemption` — real-probe dense book, body-noise
  regression, ft_catch above-ceiling refused on a heading chunk, three
  refusal shapes asserted via caplog, deferred-tail refusal surfaced
  (exact message list) — plus `TestHeadingChannelMerge` — truncated-probe
  double still derives via the channel; dedupe preference).
- ruff check + format clean; mypy clean on both touched source files.
- Full fast suite + live replay: see "Suite totals" / "Live replay"
  (shared with add-intra-page-chapter-pins; B does not touch the
  tree-driven path).

## Suite totals

Full fast suite `pytest -m "not integration and not chaos" -q` →
**4562 passed, 3 skipped, 0 failed** (57 s) — shared with
add-intra-page-chapter-pins (applied sequentially in the same tree; the
+35 delta over the prior recorded baseline is exactly that change's 27
new tests plus this change's 8).

## Live replay

`secondbrain chat "summarize by chapter hcd best practices report"
--session pins-probe-verify` (exit 0): all 21 chapters enumerated with
clean titles, no coverage note, and chapter 19 rendering the full stored
tree title — the tree-driven path is unchanged by this change (the
derivation it modifies is only consulted on the legacy path; the live
document's enumeration never calls it). Excerpt:
`/tmp/opencode/replay_pins.txt`.

## Post-review hardening (review round, same day)

Two accepted non-blocker findings, both fixed in the channel this change
owns; suites re-run after:

- **Silent channel failure now surfaces.** The channel's degraded-storage
  except (`_pipeline.py` derivation call site) returned `[]` without
  logging while its model, the opener scan (`:791-798`), warns with
  `exc_info` — a degraded-storage failure would have silently reverted
  exactly this change's fix. Now:
  `logger.warning("Heading-channel scan failed for %s; deriving from the
  probe sample only", source_filter, exc_info=True)`.
- **Truncation-boundary order inversion closed.** The probe sorts by
  `page_number` only (`storage/qdrant.py:908`, mock `:388` — stable, so
  within-page order is the store's scroll order) and truncates after that
  sort, so its cut can land mid-page and exclude a heading whose
  `page_pos` precedes included same-page chunks; appending scan-only
  chunks wholesale then placed that heading behind its own page's body
  chunks, where a same-number body claim could shadow it
  (first-claim-wins). `_merge_heading_channel` now weaves scan-only
  chunks in at their `(page_number, page_pos)` position (stable sort;
  the probe's own chunk order is never disturbed; pageless chunks keep
  the historical append-at-end placement). The helper docstring's
  "concatenation keeps the global page order" claim — only conditionally
  true — replaced by the actual invariant.

Evidence: new regression test
`test_chapter_window_purity.py::TestHeadingChannelMerge::test_scan_only_heading_woven_before_shadowing_body_claim`
with `_ScrollOrderedStorage` (models within-page scroll order ≠ pos
order; probe cut drops the (30,0) heading behind the included (30,2) body
row; asserts the woven order `[0, 2]`, the heading's claim at
`claims[3] = (src, 30, 0, …)`, and the heading's title winning the
first-claim race). The weave is identity whenever the scan dedupes empty —
all four fixture books — so `baselines.json` is untouched and A's
geometry is unaffected.

Gates re-run after the fixes: `pytest tests/unit/rag -q` → 731 passed,
0 failed (the +1 is the new boundary test); full fast suite
`pytest -m "not integration and not chaos" -q` → 4563 passed, 3 skipped,
0 failed (52 s); ruff check + format clean; mypy clean on
`_pipeline.py`.
