# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Heading-role evidence is admissible above the labeled-chapter ceiling

The "Chapter N" ceiling (`auth_max`) SHALL refuse above-ceiling chapter
numbers only from chunks that do not carry `chunk_role == "heading"`. A
bare-number chapter match (and a banner-shaped match) on a heading-role
chunk SHALL claim its roster entry even when its number exceeds the highest
"Chapter N"-labeled capture, provided the other guards pass. `ft_catch`
ToC-row captures keep the ceiling unconditionally.

#### Scenario: The dense book keeps its third chapter

- **WHEN** the legacy derivation runs over a book whose page-30 banner
  chunk is dense and labeled "Chapter 2 …", and ch3's lone heading "3
  Gamma Convolution Pipelines" (a heading-role chunk on page 40) carries a
  bare number above `auth_max = 2`
- **THEN** chapter 3 claims and the roster is {1, 2, 3}
- **AND** the flow stays in multi-chapter mode with a bucket and a summary
  for chapter 3 instead of degrading to the two-chapter lossless fetch

#### Scenario: Body-text noise above the ceiling stays refused

- **WHEN** a Chapter-N-labeled book's body prose contains a bare-number
  line like "12 Selection and Assignment" above the highest labeled
  chapter, on a chunk whose role is not heading
- **THEN** the ceiling refuses it as before and the roster is unchanged

#### Scenario: ToC-row captures keep their ceiling

- **WHEN** a flattened ToC row yields an `ft_catch` match above the ceiling
- **THEN** the ceiling refuses it regardless of chunk role

### Requirement: The derivation sees heading chunks independent of the probe sample

The legacy roster derivation's chunk sample SHALL be merged with a
heading-role scan (`find_structural_chunks` with `chunk_roles=["heading"]`
and the same source prefix), deduplicated by chunk id, before
`_derive_chapter_numbers` runs — the same probe-independence the
opener-evidence scan already applies — so a chapter's heading chunk is
derivable even when the bounded probe sample truncated the page window it
sits in.

#### Scenario: A heading beyond the probe's page window still derives

- **WHEN** the probe sample for an oversized role-marked book ends before a
  late chapter's heading chunk, but the heading-role scan returns it
- **THEN** the merged derivation sample contains the heading chunk and the
  chapter claims into the roster

### Requirement: Above-ceiling refusals are surfaced

When the ceiling refuses a chapter match, the derivation SHALL log a debug
record naming the refused number, the source, and the matching shape
(bare / banner / ToC-row), instead of dropping silently.

#### Scenario: A refusal leaves a trace

- **WHEN** the ceiling refuses any chapter match
- **THEN** a debug log line records the number, source, and shape
