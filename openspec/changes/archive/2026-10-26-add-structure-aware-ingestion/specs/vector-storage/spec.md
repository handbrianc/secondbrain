# Vector Storage (delta)

## ADDED Requirements

### Requirement: Structural payload fields populated

When a document has a stored structure tree, every stored chunk point SHALL
carry structural payload fields: `node_id`, `heading_path`, `chapter_id`,
`section_id`, `section_label` (alongside the existing `chunk_role`,
`element_type`, and page fields). Documents without a tree SHALL store chunks
without these fields. `chunk_role` SHALL join the indexed payload fields so
role filters are index-backed.

#### Scenario: Annotated chunks store their structural fields

- **WHEN** chunks of a tree-ful document are stored
- **THEN** each point payload carries `node_id`, `heading_path`,
  `chapter_id`, `section_id`, `section_label`
- **AND** a payload index exists on `chunk_role`

#### Scenario: Treeless chunks omit the fields

- **WHEN** chunks of a document without a tree are stored
- **THEN** the structural fields are absent from their payloads

### Requirement: Structural payload refresh on re-ingest

Re-ingest SHALL refresh the structural payload fields of already-stored points
for the re-ingested document (batched read-modify-write targeted at points
missing `node_id`) so dedup-skipped points become queryable without
regenerating their embeddings.

#### Scenario: Dedup-skipped points gain structure

- **WHEN** a document is re-ingested and all its chunk texts hash-match
  already-stored points
- **THEN** the stored points' payloads gain the structural fields
- **AND** no embeddings are regenerated for them
