# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Scope-faithful attribution in per-chapter summaries

When the system writes a brief per-chapter summary over content in which the
same item name appears under more than one sibling scope (for example,
identically named subsections — such as backup modes — listed once under a
virtual-machine block and again under a container block), each item's
description in the summary SHALL be attributed to the scope it appears under
in the source. Descriptions SHALL NOT be swapped, merged, or reused across
same-named items belonging to different scopes. The instruction the
summarizer receives for per-chapter brief summaries SHALL state this
attribution guard explicitly.

#### Scenario: Parallel same-named sections stay attributed to their own block

- **WHEN** a chapter's summarized content contains two sibling sections with
  the same item names (e.g. "stop / suspend / snapshot mode" under both a VM
  block and a container block) and the system writes that chapter's brief
  summary
- **THEN** each item's attributed description matches the facts that appear
  under its own scope block
- **AND** no fact from one scope's item is presented as another scope's
  same-named item

#### Scenario: The brief-summary instruction carries the attribution guard

- **WHEN** the system builds the instruction for a per-chapter brief summary
- **THEN** the instruction explicitly requires scope-faithful attribution of
  repeated item names and prohibits attributing one scope's facts to another
  scope's same-named item

#### Scenario: Chapters without repeated item names are unaffected

- **WHEN** a chapter's content contains no repeated item names across scopes
- **THEN** its brief summary is written under the same length and style
  constraints as before

### Requirement: Structural scope labels in formatted summary context

When the system formats chunks into summarization context, each chunk's
source line SHALL include the chunk's structural heading path when its stored
payload carries one, so scope markers travel with every chunk rather than
depending on a separate heading chunk appearing adjacent in the window.
Chunks whose payload carries no heading path keep the existing source line.

#### Scenario: Chunk with a heading path is labeled

- **WHEN** a chunk whose stored payload carries a heading path is formatted
  into summary context
- **THEN** its source line identifies the heading path in addition to the
  source file and page

#### Scenario: Chunk without a heading path is unchanged

- **WHEN** a chunk's stored payload carries no heading path (e.g. legacy
  stored data)
- **THEN** its source line shows the source file and page only, as before

#### Scenario: Labels are per chunk, not per window

- **WHEN** a summary window contains several chunks from different scopes
- **THEN** each chunk's own source line carries its own scope label

### Requirement: Deterministic, density-aware admission in the legacy multi-chapter sampler

In the legacy (structure-tree-less) multi-chapter sampler, within-page
admission SHALL follow document order (ascending position within the page)
rather than storage enumeration order, so the admitted window is a
deterministic function of the stored content. The per-page admission bound
SHALL scale with the page's body-chunk density within a bounded range, so a
page holding many body chunks is not reduced to the same fixed small share as
a sparse page, while the per-chapter limit continues to bound each chapter's
admitted window. Existing window-purity guarantees (in-range-only admission,
one-page boundary-straddle tolerance) are unchanged.

#### Scenario: Document order decides within a page

- **WHEN** two candidate chunks share a page and both fall within that
  page's admission bound
- **THEN** the chunk earlier in document order (lower within-page position)
  is admitted first, regardless of the order the storage returned the chunks

#### Scenario: A dense page contributes more than the base per-page bound

- **WHEN** a page holds substantially more body chunks than the base per-page
  admission bound
- **THEN** the sampler may admit more chunks from that page than the base
  bound, scaled to the page's density within a bounded maximum

#### Scenario: A sparse page is unaffected

- **WHEN** a page holds no more body chunks than the base per-page admission
  bound
- **THEN** all of its in-range chunks remain admissible exactly as before

#### Scenario: The per-chapter limit still wins

- **WHEN** density scaling would admit more chunks than the chapter's
  per-chapter limit allows
- **THEN** the per-chapter limit prevails and no additional chunks are
  admitted

#### Scenario: Sampling is reproducible across runs

- **WHEN** the same stored chapter content is sampled twice, even if the
  storage returns the chunks in a different order
- **THEN** the admitted window is identical both times
