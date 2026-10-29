# Vector Storage (delta)

## MODIFIED Requirements

### Requirement: Structural payload fields populated

When a document has a stored structure tree, every stored chunk point SHALL
carry structural payload fields: `node_id`, `heading_path`, `chapter_id`,
`section_id`, `section_label` (alongside the existing `chunk_role`,
`element_type`, and page fields). Documents without a tree SHALL store chunks
without these fields. `chunk_role` SHALL join the indexed payload fields so
role filters are index-backed. Chunk annotation SHALL resolve ownership by reading order when the caller
guarantees it: a chunk that does not itself match a heading form SHALL
inherit, in precedence order, the previously annotated node (sticky owner)
when its range contains the chunk's position, else the most recently started
range-containing candidate — instead of being left unannotated because two
sibling nodes share the chunk's page. Callers that cannot guarantee reading
order keep the conservative containment-only behavior. Annotation SHALL only
add payload keys and SHALL NOT change chunk text, pages, or hashes.

#### Scenario: Annotated chunks store their structural fields

- **WHEN** chunks of a tree-ful document are stored
- **THEN** each point payload carries `node_id`, `heading_path`,
  `chapter_id`, `section_id`, `section_label`
- **AND** a payload index exists on `chunk_role`

#### Scenario: Treeless chunks omit the fields

- **WHEN** chunks of a document without a tree are stored
- **THEN** the structural fields are absent from their payloads

#### Scenario: Unanchored body chunk inherits the sticky owner

- **WHEN** a body chunk's page is shared by two sibling nodes and the
  previously annotated node is one of them (its range contains the chunk's
  page)
- **THEN** the chunk is annotated with the sticky owner's node, not left
  unannotated

#### Scenario: Unanchored chunk without a sticky owner inherits the most
  recently started candidate

- **WHEN** a body chunk has range-containing candidates, no anchor match,
  and no applicable sticky owner (none yet, or its range ended)
- **THEN** the chunk is annotated with the most recently started candidate
  (greatest start, then level, then reading order)

#### Scenario: Reading order is not guaranteed keeps conservative behavior

- **WHEN** annotation is invoked without reading-order context and the
  chunk's page is shared by two sibling nodes outside one ancestor chain
- **THEN** the chunk stays unannotated (no node keys added)

#### Scenario: Oscillating page falls back safely

- **WHEN** a later chunk's page falls back before the sticky owner's range
  (overlap windows may oscillate pages)
- **THEN** the sticky owner is not applied unless its range contains the
  chunk's page
- **AND** the chunk resolves through the same rules as an unordered call

### Requirement: Structural payload refresh on re-ingest

Re-ingest SHALL refresh the structural payload fields of the re-ingested
document's stored points so dedup-skipped points become queryable and
stale annotations are corrected, without regenerating embeddings. The
refresh SHALL annotate the document's **full point set** (payload-only
read; vectors are never round-tripped) — not only points missing `node_id`
— because a filtered subset lacks the heading anchors and reading-order
continuity the annotation needs. Points SHALL be sorted on
`(page_number, page_pos)` before the single ordered annotation pass; only
points whose stored annotation keys are missing or differ from the fresh
annotation SHALL be written (targeted payload update by explicit point ids),
and annotation keys the fresh annotation no longer carries SHALL be removed
(targeted key deletion), so a repeated refresh against an unchanged tree and
content writes nothing. Points that resolve no node SHALL be left untouched.

#### Scenario: Dedup-skipped points gain structure

- **WHEN** a document is re-ingested and all its chunk texts hash-match
  already-stored points
- **THEN** the stored points' payloads gain the structural fields
- **AND** no embeddings are regenerated for them

#### Scenario: Refresh reconstructs reading order

- **WHEN** unannotated points of a document are refreshed and their stored
  order is not reading order
- **THEN** they are sorted on `(page_number, page_pos)` before annotation
- **AND** a body chunk following a section heading gains that section's
  annotation

#### Scenario: Stale annotations are corrected

- **WHEN** a document is re-ingested after its structure tree changed (e.g.
  the heading gate altered the tree) and stored points carry annotation
  keys from the older tree
- **THEN** the refresh re-annotates the full point set against the current
  tree
- **AND** points whose stored annotation differs are rewritten with the
  current annotation, while already-correct points are not rewritten
- **AND** annotation keys the current annotation no longer carries are
  removed, so a repeated refresh with an unchanged tree rewrites nothing

#### Scenario: Filtered subsets are not used for annotation

- **WHEN** the refresh runs
- **THEN** it reads the document's full point set (payload only) rather than
  only points with an empty `node_id`, so heading chunks already carrying
  annotations still anchor the reading-order pass
