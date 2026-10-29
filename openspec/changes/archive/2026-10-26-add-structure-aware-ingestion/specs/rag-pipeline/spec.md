# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Stored tree drives chapter enumeration

When the queried document has a stored structure tree containing chapter or
section nodes, broad-coverage chapter/section enumeration SHALL resolve
chapter maps and ranges from the tree (SQL lookup → page-range or ID filters
through the existing retrieval machinery) and SHALL NOT run the legacy
regex-based reconstruction for that document. A tree chapter whose page range
holds no body content SHALL be emitted with the existing placeholder note.

#### Scenario: Previously failing report enumerates fully

- **WHEN** the user asks to summarize a document whose stored tree covers
  every chapter (the HCD report case)
- **THEN** the output names every chapter with a real page range
- **AND** no chapter is a false placeholder
- **AND** no chapter's summary draws content from another chapter's pages

#### Scenario: Chapter question answers from the tree

- **WHEN** the user asks which page a chapter starts on, or to list sections
- **THEN** the answer is derived from the stored tree, not from regex scans

### Requirement: Legacy reconstruction is fallback only

When the queried document has no stored tree, the tree lookup fails, or the
tree carries no chapter/section nodes, the pipeline SHALL use the legacy
heuristic path unchanged — including anthology detection and the
chapter-range agreement gate. The legacy path's behavior on treeless
documents SHALL remain byte-identical to its pre-change behavior.

#### Scenario: Treeless document keeps legacy behavior

- **WHEN** a document ingested before this change is summarized
- **THEN** the legacy chapter path (and, where applicable, the anthology path
  and agreement gate) produces the same output as before

#### Scenario: Lookup failure degrades to legacy

- **WHEN** the structure store errors during lookup
- **THEN** the query proceeds through the legacy path
- **AND** the failure is logged, not surfaced as a query error
