# Proposal

## Why

Project todo d4fd93ec (from `fix-chapter-bucket-sampling`): "with a real
top-k probe, a dense page's body chunks can all outrank a lone chapter
heading, so that chapter silently drops from the roster and never gets a
bucket/summary." The diagnosis for this change reproduced the drop
end-to-end at unit level — and found the recorded mechanism does not exist.

There is no ranking anywhere in the probe chain. `_probe_document_structure`
(`_structure_mixin.py:1622-1686`) is a metadata-filtered, page-ascending
scroll with a limit in every implementation (Qdrant scroll sorted by
`page_number`, `qdrant.py:864-914`; mock, protocol, and both test doubles
alike) — no vectors, no scores, no threshold. The dense book's probe sample
is complete: all 18 chunks including ch3's lone heading.

The drop's actual decision point is the "Chapter N" ceiling in
`_derive_chapter_numbers`: pass 1 captures "Chapter 2 …" from the dense
page's banner chunk, `auth_max` becomes 2 (`_structure_mixin.py:1262`), and
pass 2 then finds the bare-number heading "3 Gamma Convolution Pipelines"
— a real `chunk_role="heading"` chunk — but the ceiling guard
`major > auth_max` (`_structure_mixin.py:1316`; also `:1401`, `:1422`)
silently refuses it. Chapter 3 never enters the roster, the D5 gap note
cannot see it (`_missing_chapter_numbers` only scans `1..max(roster)`), and
the two-chapter roster flips the flow into `single_section_mode`
(`_pipeline.py:1559`) — a lossless two-chapter fetch that absorbs ch3's
page into ch2's bucket. The variant matrix proves the ceiling is the
decision point: removing the word "Chapter" from the banner (auth_max
stays 0) or labeling ch3 "Chapter 3" (auth_max rises to 3) both restore the
3-chapter roster, while merging the heading into the probe sample alone
does not (the ceiling refuses it anyway), and density is irrelevant.

So the todo's candidate fix ("reserve a slot for heading evidence in probe
ranking, or floor chapter headings' rank") has nothing to act on. Its
intent — a lone chapter heading must not lose its chapter to the probe's
sampling — lands at the derivation instead: heading evidence must be
admissible above the labeled-chapter ceiling, and the derivation must see
heading chunks regardless of what the bounded probe sample happens to
contain.

A secondary, genuinely top-k-shaped hazard was measured and is explicitly
out of scope: the probe's fallback limit (`top_k=400`, page-ordered) can
truncate marker-less oversized books (a 600-chunk book sampled 400 chunks
and derived chapters 1–4 of 6). That is a page-window truncation of the
scroll limit, not this defect; it is recorded as a follow-up.

## What changes

- The `auth_max` ceiling no longer refuses bare-number chapter matches (and
  banner-shaped matches) found on `chunk_role == "heading"` chunks; body
  text above the ceiling stays refused, preserving the ceiling's original
  purpose (noisy "12 Selection and Assignment" prose in Chapter-N-labeled
  books must not fabricate chapters).
- The derivation's chunk sample gains a heading-role channel merged in
  independently of the probe sample (the same probe-independence pattern
  the opener-evidence scan already uses at `_pipeline.py:1580-1598`), so a
  heading beyond the probe's page window still derives.
- Above-ceiling refusals are logged (debug: number, source, shape) instead
  of vanishing silently.

## Scope

- `_structure_mixin.py` (ceiling guards + logging) and `_pipeline.py`
  (heading-channel merge into the derivation input). Query-time only; no
  ingest or annotation changes.
- Non-goals: redesigning the probe as ranked retrieval (nothing in the
  product needs it); the fallback-limit truncation hazard for marker-less
  oversized books (follow-up todo); making the D5 gap note see
  above-roster-max chapters (the debug log is the surfacing for now);
  `ft_catch` ToC-row captures keep their ceiling (they are ToC-flattening
  artifacts by design, and above-ceiling ToC rows are phantoms).
