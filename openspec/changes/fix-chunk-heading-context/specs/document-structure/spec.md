# Document Structure (delta)

## ADDED Requirements

### Requirement: Heading plausibility gate at capture

Docling-detected heading items SHALL become structure-tree nodes only when
their text passes a heading plausibility test. A heading is plausible when it
starts with a section-number prefix, or when it is short (under ~120
characters), carries no trailing sentence punctuation (`.`, `:`, `,`, `;`),
and has no "command - description" synopsis shape. Implausible items (run-in
labels such as "Restart chrony:", sentence fragments, synopsis lines such as
"pvesubscription - Subscription Management") SHALL NOT create tree nodes.
Outline/bookmark-derived nodes SHALL NOT be gated: outline evidence stays
authoritative. Gating SHALL NOT alter, reorder, or drop any text item — it
only decides which docling-detected headings become nodes.

#### Scenario: Run-in label is not a tree node

- **WHEN** a parsed document contains a docling section header whose text is
  "Restart chrony:"
- **THEN** no tree node is created for it
- **AND** its text still appears in the document's chunk stream unchanged

#### Scenario: Numbered headings always pass the gate

- **WHEN** a docling section header starts with a section number (e.g.
  "19.2 pveperf")
- **THEN** a tree node is created for it regardless of other shape signals

#### Scenario: Outline-derived nodes are not gated

- **WHEN** a PDF outline (bookmark tree) contains an entry whose title would
  fail the plausibility test
- **THEN** the outline-derived node is still created

#### Scenario: Short all-caps run-in heading stays a node

- **WHEN** a docling section header's text is a short, punctuation-free
  run-in heading (e.g. "GENERAL BTRFS ADVANTAGES")
- **THEN** a tree node is created for it
