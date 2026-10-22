# RAG Pipeline — Chapter Enumeration Anchoring Delta

## ADDED Requirements

### Requirement: Chapter pins derive from first-section heading evidence

The chapter-enumeration pipeline SHALL pin chapter N provisionally at the
page of its first `N.1`-shaped heading-role chunk (minus one page when
that page carries body chunks, else at the heading's own page), before any
fuzzy anchor or digit-scan tier runs. Pins from this tier SHALL respect the
front-matter page floor, boilerplate-page exclusions, and a dot-leader
density guard so ToC-like heading chunks never pin. Pins from stronger
exact evidence (ToC listing rows, recovered run-on ToC rows, both resolved
through a validated printed→stored offset) SHALL override these
provisional pins; fuzzy anchors and digit scans SHALL NOT.

#### Scenario: Banner-less numbered book pins every chapter

- **WHEN** a book whose chapter openers carry no banner or title heading
  (e.g. a manual where docling drops them) is summarized by chapter
- **AND** every chapter's first numbered section heading exists as a
  heading-role chunk
- **THEN** every roster chapter receives a page pin within one page of its
  true opener
- **AND** the enumeration output names every chapter

#### Scenario: ToC-like heading chunks do not pin

- **WHEN** a dot-leader-dense page carries heading-role chunks shaped like
  `N.1` ToC rows
- **THEN** the evidence tier refuses to pin from that page

#### Scenario: Exact ToC evidence overrides provisional pins

- **WHEN** recovered run-on ToC rows give chapter N's printed opener page
  and the printed→stored offset validates against section-heading evidence
- **THEN** chapter N's pin is the ToC-derived page, replacing the
  provisional section-heading pin

### Requirement: Footer offsets resolve bare-number footers and offset 0

The footer-offset resolver SHALL parse footers with an optional
`/total` suffix (both `"78 / 634"` and bare `"29"`), SHALL accept
`printed == physical` (offset-0 books), and SHALL return the majority
offset only under the existing agreement gates (≥3 sampled pages, ≥80%
agreement). Roman-numeral and non-page footer texts SHALL be ignored.

#### Scenario: Offset-0 book resolves from bare footers

- **WHEN** a book's footers equal its physical page numbers (printed page
  == stored page, no `/total` suffix)
- **THEN** `footer_page_offset` returns `0`
- **AND** run-on ToC rows map to their exact stored pages

#### Scenario: Consistent-offset book still resolves

- **WHEN** footers read `"78 / 634"` on physical page 96 (offset −18)
- **THEN** the resolver returns the majority offset as before

### Requirement: Run-on ToC offset validates against body evidence

When the footer offset is unavailable, the run-on ToC tier SHALL derive the
printed→stored offset as the majority of (first-section heading page −
recovered printed page) across recovered chapters, and SHALL pin through it
only when a strict majority agrees. When no majority exists the tier SHALL
stay disabled rather than pin from an unvalidated offset.

#### Scenario: Footer-less book pins from evidence-validated offset

- **WHEN** a book has no navigation/footer chunks but recovered ToC rows
  and first-section heading evidence agree on a constant offset
- **THEN** chapters pin at their printed ToC pages plus that offset

#### Scenario: Conflicting evidence disables the tier

- **WHEN** recovered rows imply several conflicting offsets with no
  majority
- **THEN** no ToC-derived pins are made
- **AND** chapters remain for the interpolation and placeholder fallbacks

### Requirement: Heading-title anchors match at token granularity

The heading-title anchor pass SHALL match a roster chapter title to a
heading chunk only when every title token appears as a whole, case-folded
token in the heading text (whitespace-squash comparison retained for
glued/spaced variants), with a bounded token-count slack for version
suffixes. Sub-word matches (`REFERENCES` for "Reference") and
sentence-like headings that merely contain title words ("Change logs are
also available at:") SHALL NOT anchor. ToC listing/run-on pins SHALL take
precedence over anchor pins.

#### Scenario: All-caps opener still anchors

- **WHEN** a book's chapter opener headings are ALL-CAPS
  ("INSTALLING VIRTUALBOX") against roster title "Installing VirtualBox"
- **THEN** the anchor matches at token granularity

#### Scenario: Unrelated heading does not anchor

- **WHEN** a heading "REFERENCES" (license appendix) faces roster title
  "Reference"
- **THEN** no anchor is produced for that chapter from that heading

### Requirement: Scan tiers refuse front-matter and cross-reference noise

The section-number and loose-digit scans SHALL skip dot-leader-dense
(ToC-like) pages, and the body-title scan SHALL refuse matches followed by
a `on page N` cross-reference, matching the guard the section scan already
applies.

#### Scenario: ToC rows in the body stream do not pin chapters

- **WHEN** a book's flattened ToC rows are stored as body chunks carrying
  `N.M` section numbers
- **THEN** the section-number scan pins no chapter from those pages

#### Scenario: Cross-reference sentence does not anchor a title

- **WHEN** a body chunk contains "15 VBoxManage on page 271, the
  command-line interface…"
- **THEN** the body-title scan does not pin chapter 15

### Requirement: Enumeration emits every roster chapter

The multi-chapter enumeration SHALL emit an entry for every roster chapter.
A chapter with no derived page range SHALL be emitted with the explicit
"no document content was retrieved for this chapter" placeholder rather
than omitted silently.

#### Scenario: Rangeless chapter appears as placeholder

- **WHEN** chapter detection yields no page range for a roster chapter
  (e.g. an unnumbered tail chapter in a book whose ToC did not parse)
- **THEN** the output contains that chapter's heading followed by the
  placeholder note

### Requirement: Enumeration prompt is count-agnostic

The RAG system prompt's chapter-enumeration rule SHALL NOT hard-code a
chapter count; it SHALL require enumerating every chapter present in the
provided context regardless of number.

#### Scenario: Prompt does not reference a fixed count

- **WHEN** the RAG system prompt is rendered for any document
- **THEN** no specific chapter count ("21") appears in the enumeration rule
