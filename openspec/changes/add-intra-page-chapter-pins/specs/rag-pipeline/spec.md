# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Derivation claims carry intra-page positions

The legacy chapter derivation SHALL record, for every roster claim it makes
from a bare-number heading match, the claim's position: the chunk's
`page_number` and `page_pos`, the match's character offset inside the chunk
text, and which half of the chunk the offset falls in (`char_offset <
len(text) / 2` → first half, mirroring `structure_annotate`). The claim map
SHALL travel with the roster to the pipeline so pin and range assembly can
consume it. A title capture whose match ends at the chunk's final character
SHALL NOT claim during the scan — it is a tail-truncated capture (the line
is incomplete at the chunk boundary) and MAY claim only after the full scan,
and only if the number is still unclaimed.

#### Scenario: hcd-report claims all 21 chapters with positions

- **WHEN** the legacy derivation runs over the hcd-report fixture
- **THEN** the roster is chapters 1–21 and the claim map carries, for
  example, ch1 at (page 2, pos 0, first half), ch4 at (page 4, pos 2,
  second half), ch6 at (page 5, pos 4, first half), and ch7 at (page 6,
  pos 3, first half)

#### Scenario: A tail-truncated fragment never steals a title

- **WHEN** a chunk ends with "7. The IDEO" (the heading line truncated at
  the chunk boundary) and a later chunk carries the complete "7. The IDEO
  Field Guide: Mindsets, Phases, and Methods" heading
- **THEN** the complete capture claims chapter 7 during the scan with the
  full title
- **AND** the truncated fragment claims nothing

### Requirement: The "the" carve-out admits colon-less real headings but not license prose

The D6-r3 "the"-carve-out SHALL admit a dot-shaped "The …" bare-number title
without requiring a colon, provided the captured title does not match
sentence-case license vocabulary (multi-word license phrases such as
"Project Gutenberg", "Free Software Foundation", "MIT License", "GNU Free
Documentation", "origin of this software", "endorse or promote", "eBook of",
"redistribution(s) of", "documentation license"). Colon-bearing "The …"
titles keep today's unconditional carve-out. All-caps license captions stay
rejected by the existing boilerplate gate; lowercase-start and non-heading
shapes stay rejected by the existing guards.

#### Scenario: hcd-report chapter 4 is detected

- **WHEN** the derivation scans the page-4 chunk containing "4. The Four
  Phases of HCD Work" (dot-shaped, title without a colon, no license
  vocabulary)
- **THEN** chapter 4 claims with the title "The Four Phases of HCD Work"
- **AND** the roster run filter keeps chapters 1–21 as one consecutive run

#### Scenario: License prose keeps its rejection

- **WHEN** the derivation scans license paragraphs like "13. The Free
  Software Foundation may publish revised and/or …", "2. The MIT License",
  or "1. The Project Gutenberg eBook of …"
- **THEN** none of them claims a roster entry
- **AND** the user-manual fixture's derived roster is unchanged

### Requirement: Claim pins fill unmoored roster chapters

The pipeline SHALL run a fill-only claim pin tier after the existing pin
tiers: a roster chapter of the selected source with a recorded claim and no
page pin gets pinned at its claim page, guarded by the existing window-fit
check and skipped on ToC-killed chapters, boilerplate pages, and ToC-like
pages. Existing tier pins are never overwritten.

#### Scenario: Chapters 1–3 gain their first pins

- **WHEN** the hcd-report fixture runs the pin assembly
- **THEN** ch1 pins at page 2, ch2 at page 3, and ch3 at page 4
- **AND** every chapter the other tiers already pinned keeps its pin

### Requirement: Same-page and mid-page chapter starts split their page

The pipeline SHALL build an intra-page cut map from roster chapters whose
claim page equals their final pin page (or their recovered range's start
page): each cut records (page, page_pos, half, after-chapter, and whether
the before-chapter's pre-extension range contains the page). At bucket
admission, a chunk on a cut page SHALL be assigned by walking the page's
cuts in reading order — chunks before a cut's position go to the
before-chapter; the cut's own chunk goes to the after-chapter when the
heading is in the first half, and to the before-chapter when the heading is
in the second half and the before-chapter's pre-extension range contains
the page, otherwise to the after-chapter; chunks after the last cut go to
the last cut's after-chapter. When a cut's owner has no range containing
the page, or the page has no cuts, admission falls back to today's
first-range-wins rule.

#### Scenario: Page 4 splits between chapters 3 and 4

- **WHEN** the hcd-report legacy buckets assemble with the cut at (page 4,
  pos 2, second half, after ch4) and ch3's range containing page 4
- **THEN** page 4's chunks at pos 0–2 belong to ch3's bucket (the pos-2
  chunk stays with ch3, mirroring `structure_annotate`'s second-half rule)
- **AND** pos 3–5 ("Build understanding of the problem…", the phase table)
  belong to ch4's bucket, matching the live annotations

#### Scenario: Page 5 splits between chapters 5 and 6

- **WHEN** the cut at (page 5, pos 4, first half, after ch6) applies
- **THEN** pos 0–3 belong to ch5 and pos 4 belongs to ch6, matching the
  live annotations

#### Scenario: Page 6's table returns to chapter 6

- **WHEN** ch7's claim cut at (page 6, pos 3, first half, after ch7)
  applies and ch6's range extends onto page 6
- **THEN** page 6's pos 0–2 — the marker-less phase table ("Phase Methods
  Output Common failure…") — belong to ch6's bucket
- **AND** pos 3–6 belong to ch7

#### Scenario: Second-half heading on a page the previous chapter no longer owns

- **WHEN** ch16's heading sits in the second half of page 14's first chunk
  and ch15's pre-extension range ends at page 13
- **THEN** that chunk belongs to ch16 (the after-chapter), matching the
  live annotation
- **AND** ch11's second-half heading in page 11's pos-2 chunk belongs to
  ch11 while pos 0–1 stay with ch10, matching the live annotations

### Requirement: Ranges extend onto cut pages and sentinel chapters recover

Chapter range ends SHALL extend onto the next chapter's cut page when the
cut's position is greater than the page's first chunk position (pre-heading
chunk positions exist); a cut at the page's first chunk position extends
nothing. A roster chapter of the selected source with a recorded claim but
no page pin and no range SHALL gain a recovered range — starting at its
claim page and ending at the next roster boundary, extended onto that
boundary's cut page by the same rule — instead of the `(0, -1)` sentinel.

#### Scenario: The four sentinel chapters gain real ranges

- **WHEN** the hcd-report legacy ranges assemble
- **THEN** ch6 = (5, 6), ch10 = (10, 11), ch13 = (12, 13), and ch15 =
  (13, 13), and no hcd chapter carries the (0, -1) sentinel
- **AND** ch10's extension onto page 11 places its pre-heading chunks
  (pos 0–1) in ch10's bucket, matching the live annotations

#### Scenario: A first-chunk cut extends nothing

- **WHEN** ch5's claim cut sits at page 5's pos 0 (first half)
- **THEN** ch4's range ends at page 4 and none of page 5 leaks into it
