# Document Structure (delta)

## ADDED Requirements

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
of its descendants' recovered section numbers.

#### Scenario: Number-less outline yields a numbered tree

- **WHEN** a PDF whose bookmark titles omit numbering tokens is ingested and
  its table of contents lists "1 Introduction", "1.1 Central Management",
  … "1.13 Translating Proxmox VE"
- **THEN** the stored tree carries a chapter node numbered 1 titled
  "Introduction" spanning the bookmark's page range, with section nodes
  numbered 1.1–1.13 beneath it
- **AND** the chapter map built from the tree covers every chapter, not only
  the few whose headings were parsed from ToC-page text

#### Scenario: Parsed numbers are never overwritten

- **WHEN** a node's title already carries a numbering token
  (e.g. "2.3 Using the Proxmox VE Installer")
- **THEN** the parsed number is kept as-is and recovery does not touch it

#### Scenario: Ambiguous match stays unnumbered

- **WHEN** a node title matches multiple ToC listings equally, or matches none
- **THEN** the node is persisted without a number
- **AND** no wrong number is introduced by the recovery pass
