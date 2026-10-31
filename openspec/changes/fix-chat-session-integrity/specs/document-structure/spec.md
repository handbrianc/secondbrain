# Document Structure (delta)

## ADDED Requirements

### Requirement: ToC-page heading suppression at capture

At capture time, heading candidates that lie on a document's table-of-
contents page span SHALL NOT become chapter or section nodes whose page
ranges sit inside that span. A candidate heading whose physical page falls
within the detected ToC page span and whose text corresponds to a ToC
listing row SHALL be suppressed from node creation (recording the
suppression in capture metadata), rather than captured as a node and left
for query-time filtering. Suppression SHALL NOT remove genuine chapter
nodes whose page range starts at or after the end of the ToC span.

#### Scenario: ToC rows detected as headings produce no ghost nodes

- **WHEN** a PDF whose table-of-contents rows are detected as section
  headings (e.g. `1 Introduction`, `7 Proxmox VE Storage` on the ToC pages
  of `pve-admin-guide-9.1.pdf`) is ingested
- **THEN** the stored tree carries no chapter node whose page range lies
  inside the ToC page span and whose title matches a ToC listing row
- **AND** capture metadata records the suppressed candidates

#### Scenario: Real chapters survive suppression

- **WHEN** ghost suppression runs on a document whose real chapter nodes
  begin at body pages after the ToC span
- **THEN** every real chapter node is preserved
- **AND** number-less real chapters remain eligible for numbering recovery

## MODIFIED Requirements

### Requirement: Chapter numbering recovery from ToC listings

When captured node titles carry no numbering token (for example a PDF
bookmark outline whose titles omit section numbers), the system SHALL recover
chapter and section numbers for the affected tree nodes by matching their
titles against the document's own table-of-contents listings, and persist the
recovered numbers in the stored tree. A match SHALL be accepted only when the
normalized title matches exactly one listing at the same outline position
(document order and nesting level agree); ambiguous or unmatched nodes SHALL
stay number-less. Recovery SHALL NOT overwrite a number already parsed from a
node's title, and a recovered chapter number SHALL be the leading component
of its descendants' recovered section numbers. A recovered number SHALL be
assigned to a node only when the node's physical page range is consistent
with the listing's printed page number mapped through the document's page
labels within a bounded tolerance; when a document lacks usable page labels,
recovery SHALL bound the offset by consistency across sibling listings
instead of assuming a fixed mapping. An assignment whose mapped page collides
with an already-assigned chapter SHALL be refused rather than guessed, even
when the number is otherwise free because a ToC-span ghost previously held it.

#### Scenario: Number-less outline yields a numbered tree

- **WHEN** a PDF whose bookmark titles omit numbering tokens is ingested and
  its table of contents lists "1 Introduction", "1.1 Central Management",
  … "1.13 Translating Proxmox VE"
- **THEN** the stored tree carries a chapter node numbered 1 titled
  "Introduction" spanning the bookmark's page range, with section nodes
  numbered 1.1–1.13 beneath it
- **AND** the chapter map built from the tree covers every chapter, not only
  the few whose headings were parsed from ToC-page text

#### Scenario: Printed page maps through page labels to the right node

- **WHEN** a ToC listing prints "7 Proxmox VE Storage … 153" and the
  document's page labels map printed page 153 to physical page 163, where
  the real chapter node spans physical pages 163–194
- **THEN** recovery assigns number 7 to that node
- **AND** no node whose range sits on the ToC pages receives the number

#### Scenario: Colliding assignment is refused

- **WHEN** two nodes both plausibly match the same listing's title and page
  (e.g. a leftover ToC-span ghost and the real chapter)
- **THEN** recovery assigns neither (or only the physically consistent one,
  refusing the ghost's range)
- **AND** the stored tree never carries two chapter nodes with the same
  recovered number

#### Scenario: Parsed numbers are never overwritten

- **WHEN** a node's title already carries a numbering token
  (e.g. "2.3 Using the Proxmox VE Installer")
- **THEN** the parsed number is kept as-is and recovery does not touch it

#### Scenario: Ambiguous match stays unnumbered

- **WHEN** a node title matches multiple ToC listings equally, or matches none
- **THEN** the node is persisted without a number
- **AND** no wrong number is introduced by the recovery pass
