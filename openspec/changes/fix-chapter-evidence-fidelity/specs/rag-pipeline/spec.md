# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Text-marker identity floor scales to short documents

The chapter-bucket guard's text-marker fallback SHALL apply a front-matter
page floor of 3 (chapters starting from page 3 onward contribute in-chunk
heading-shaped markers) rather than the previous floor of 20, so short
reports of a dozen-odd pages are covered by text markers. Pages 1–2 (title
page, table of contents) remain excluded. The dot-leader and page-suffix
noise guards remain the defense against ToC-shaped lines. Structured payload
identity (`section_id`, `chapter_id`, `heading_path`) remains floor-free, as
before.

#### Scenario: Short report's in-chunk markers apply

- **WHEN** a 25-page report's chapter heading ("9. Krippendorff's …") opens
  a chunk on page 10 and the chunk's structured payload carries no chapter
  identity
- **THEN** the text-marker fallback reads chapter 9 from that heading
- **AND** the bucket guard treats the chunk as chapter 9's content

#### Scenario: Title and ToC pages stay excluded

- **WHEN** a dot-leader ToC row like "3. The ISO 9241-210 Standard ....... 4"
  appears on page 2 of a report
- **THEN** the text-marker fallback reads no chapter identity from it
- **AND** bucket partitioning is unchanged for front-matter pages

#### Scenario: Long books keep the marker behavior they had

- **WHEN** a book's chapter heading appears on page 30
- **THEN** the marker is read as before (page 30 is above both floors)

### Requirement: Roster titles come from chapter headings, not register rows

Roster-title capture for the legacy chapter path SHALL capture the title from
the number's own line — a numbered line carrying no title text on that line
(footer-adjacent empty list-marker runs like "1. ⏎ 2. ⏎ …") SHALL NOT match,
except the shipped banner shape: a number line with no title that is directly
followed by a dotted `N.M` section heading, which the existing dotted-section
guard converts to an empty-title entry (the section never titles the
chapter). The capture SHALL use at most one bounded continuation line, and
only when the heading line ends dangling — a trailing comma, dash, or open
parenthetical, or a trailing connective word ("… Mindsets, Phases, and" /
"… Designing for") — or when the next line is a single word, a wrapped
heading's orphan word ("… Working Table and Common" ⏎ "Failures"). A
complete title followed by multi-word body prose ("… Testing Well" +
"Usability testing means observing users as they") never takes one, so body
lines cannot glue into a title. The capture SHALL trim the captured title
at a word boundary rather than a fixed character cap that cuts mid-word,
and SHALL reject citation-shaped rows — a bare-number line whose
captured title carries a spaced dash citation separator with a compact,
comma- or year-bearing, or unclosed parenthetical ("7 Wikipedia — The Design
of Everyday Things (D. Norman, 1988/2013)" is a source-register entry, not a
chapter heading). When no clean title is available for a chapter, the entry
header SHALL show the chapter number only. (The dot-less "2 First
Principles: …" heading shape stays capturable — see "Roster titles preserve
quoted phrases".)

#### Scenario: Register row does not title a chapter

- **WHEN** a page-23 source-register row reads
  "7 Wikipedia — The Design of ⏎ Everyday Things (D. Norman, ⏎ 1988/2013)"
  and chapter 7's real heading exists elsewhere
- **THEN** the roster title for chapter 7 comes from the real heading
- **AND** the register row never supplies a chapter title

#### Scenario: Footer-adjacent empty list markers claim nothing

- **WHEN** a chunk carries an empty list-marker run
  "1. ⏎ 2. ⏎ … N. ⏎" followed by a running footer line
  ("… Report Page 9 of 25")
- **THEN** no chapter claim is produced from the markers or the footer
- **AND** the detected roster and ranges match the pre-change baselines

#### Scenario: Banner number above its section keeps the chapter

- **WHEN** a chunk carries a chapter banner number alone on its line directly
  above its dotted section heading ("1 ⏎ 1.1 Central Management")
- **THEN** chapter 1's entry survives with an empty title — the existing
  dotted-section guard converts the captured section heading exactly as
  before
- **AND** the roster never titles chapter 1 with the section heading

#### Scenario: Wrapped heading joins after a dangling end

- **WHEN** a chapter heading wraps after a connective ("7. The IDEO Field
  Guide: Mindsets, Phases, and" ⏎ "Methods", "9. Krippendorff's Semantic
  Turn: Designing for" ⏎ "Meaning", "5. The Methods Library: Discover,
  Decide, Make," ⏎ "Validate") or leaves an orphan word ("6. Phase-by-Phase
  Working Table and Common" ⏎ "Failures", "15. Governance: Telling Real HCD
  from HCD" ⏎ "Theater")
- **THEN** the captured title joins the one continuation line ("… Mindsets,
  Phases, and Methods", "… Designing for Meaning", "… Make, Validate",
  "… Common Failures", "… from HCD Theater")

#### Scenario: Complete titles take no continuation line

- **WHEN** a chapter's own heading line is complete ("12. Running Usability
  Testing Well", "13. Where HCD Pays Off — and Where It Doesn't", "16.
  Quick-Reference Checklist", "20. Bridging to Story Mapping (Companion
  Report)", "21. Source Register") and the next line is ordinary body prose
- **THEN** the captured title stays the heading line's own text
- **AND** body text never glues into a roster title

#### Scenario: Title trim lands on a word boundary

- **WHEN** a captured title exceeds the length cap mid-word
- **THEN** the title is trimmed back to the last whole word
- **AND** no roster title ends mid-word (e.g. "…(D…")

#### Scenario: Clean documents keep byte-identical output

- **WHEN** every chapter's title parses cleanly under the new rules exactly
  as under the old ones
- **THEN** roster titles and emitted summaries are unchanged

## MODIFIED Requirements

### Requirement: Stored-tree chapter map integrity

The chapter map derived from a stored structure tree SHALL be built only from
chapter-shaped nodes whose page range lies outside the document's
table-of-contents page span. A candidate chapter range whose stored chunks
are dot-leader-dense (ToC-like) SHALL NOT contribute a chapter-map entry. A
number-less chapter-shaped root node that precedes every numbered
chapter-shaped node — the document's title or cover — is front matter, not a
lost chapter, and SHALL NOT count toward the degenerate-map comparison;
number-less chapter-shaped nodes interleaved with numbered chapters still
count. When the surviving number-keyed map covers fewer chapters than the
tree's chapter-shaped nodes support, the pipeline SHALL treat the map as
degenerate and fall back to the legacy chapter path with the guards of
"Legacy chapter title and window guards" — it SHALL NOT enumerate chapters
from a partial map whose ranges are known to sit inside the ToC span.

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

#### Scenario: Number-less title root does not degenerate the map

- **WHEN** a stored tree opens with a number-less chapter-shaped root node
  carrying the document's title (pages 1–1) followed by 21 numbered chapter
  nodes whose ranges all key (the `hcd_best_practices_report.pdf` case)
- **THEN** the tree map drives chapter enumeration
- **AND** the legacy scan does not run merely because the title node carries
  no number
