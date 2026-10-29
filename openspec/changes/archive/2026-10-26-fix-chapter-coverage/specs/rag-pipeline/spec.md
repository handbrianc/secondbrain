# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Stored-tree chapter map integrity

The chapter map derived from a stored structure tree SHALL be built only from
chapter-shaped nodes whose page range lies outside the document's
table-of-contents page span. A candidate chapter range whose stored chunks
are dot-leader-dense (ToC-like) SHALL NOT contribute a chapter-map entry.
When the surviving number-keyed map covers fewer chapters than the tree's
chapter-shaped nodes support, the pipeline SHALL treat the map as degenerate
and fall back to the legacy chapter path with the guards of "Legacy chapter
title and window guards" — it SHALL NOT enumerate chapters from a partial
map whose ranges are known to sit inside the ToC span.

#### Scenario: ToC-span node cannot define a chapter

- **WHEN** a stored tree carries a chapter node numbered 1 whose page range
  lies inside the document's table-of-contents span (e.g. pages 3–8 of a
  ToC spanning pages 3–22), as observed for `pve-admin-guide-9.1.pdf`
- **THEN** that node contributes no chapter-map entry with that range
- **AND** chapter 1's summary window covers the chapter's body pages, never
  the table-of-contents pages

#### Scenario: Degenerate map falls back instead of mis-summarizing

- **WHEN** the number-keyed tree map covers 2 of 21 chapter-shaped nodes
  (both with ToC-span ranges)
- **THEN** the pipeline falls back to the legacy guarded chapter path
- **AND** the multi-chapter output still names every roster chapter, with
  summaries drawn from real body content — never from the 2 bogus ranges

#### Scenario: Healthy tree enumerates unchanged

- **WHEN** a stored tree's chapter map covers every chapter with body-page
  ranges (the HCD-report case of the tree-driven enumeration requirement)
- **THEN** map construction behaves exactly as today
- **AND** no additional fallback or guard fires

### Requirement: Legacy chapter title and window guards

Wherever the legacy chapter path runs, a heading with a dotted number prefix
(e.g. "1.1 Central Management") SHALL NOT supply a chapter's title; the
chapter's title SHALL come from the document's ToC listing for that chapter
number when one is recovered, else the entry header SHALL show the chapter
number only. A chapter's legacy page window SHALL end at the next chapter's
derived start (minus one page) when that boundary is derivable and lies
beyond the window's current end — the clamp only extends an undershooting
window, never shrinks or overruns into the next chapter. Documents whose
chapter headings all parse as today SHALL keep byte-identical legacy output.

#### Scenario: Dotted heading does not title chapter 1

- **WHEN** the legacy scan's first parseable heading for chapter 1 is the
  section heading "1.1 Central Management" (the chapter's own heading chunk
  failed to parse)
- **THEN** chapter 1's entry is titled "Introduction" from its ToC listing,
  or "Chapter 1" when no listing is available
- **AND** it is never titled "1.1 Central Management"

#### Scenario: Undershooting window extends to the next chapter

- **WHEN** chapter 1's own heading chunk is unparseable but chapter 2's start
  is derived (page 10 of a 9-page chapter 1)
- **THEN** chapter 1's window extends to chapter 2's start page
- **AND** its summary draws on sections 1.1 through 1.13, not only 1.1

#### Scenario: Healthy legacy documents are unchanged

- **WHEN** every chapter's heading parses as today and windows reach their
  next-chapter boundaries already
- **THEN** titles, windows, and emitted summaries are byte-identical to the
  pre-change legacy behavior
