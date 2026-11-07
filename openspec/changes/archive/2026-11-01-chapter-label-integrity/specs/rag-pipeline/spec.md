# RAG Pipeline (delta)

## ADDED Requirements

### Requirement: Chapter buckets carry only self-identified content

In the multi-chapter overview funnel, a chapter's summary SHALL NOT be written
over content whose own structural identity names a different chapter. A
chunk's identity SHALL be read in deterministic priority order from its own
payload — the structured `section_id` prefix (dotted `7.1` or bare `11`),
then the numeric `chapter_id`, then the `Chapter N` prefix of `heading_path`,
and only when none of those yield a chapter number, a heading-shaped
line-initial `N.M` text marker in the chunk's first lines (dot-leader-free,
ToC-noise-guarded; the front-matter page floor applies to the text fallback
only, never to structured fields, which are ingest-time evidence). Before any
chapter heading streams, the pipeline SHALL partition each bucket by this
identity: chunks naming a different chapter M SHALL move to chapter M's
bucket when M is in the enumeration's roster, and SHALL be dropped from
chapter N otherwise; chunks naming their own chapter or carrying no
identifying marker SHALL stay. A chapter whose bucket becomes empty through
this guard SHALL appear with the existing placeholder note extended by a
deterministic reason line naming the chapter its detected content was
reassigned to. On the legacy coverage path, which delegates one chapter per
call, the guard SHALL run once over the full roster before the per-chapter
delegation — a single-chapter delegation must never drop reassigned content
merely because its target chapter is not in that delegation's roster. The
guard SHALL run once per overview, SHALL be deterministic, and SHALL NOT
change buckets whose chunks all self-identify with their own chapter.

#### Scenario: Structured identity overrides wrong page-range pins

- **WHEN** chapter 6's detected page range yields chunks whose payload says
  `chapter_id=7`, `section_id=7.1` (the treeless report case, 17 pages, no
  text markers)
- **THEN** those chunks are summarized under chapter 7's heading, not
  chapter 6's
- **AND** chapter 6's heading shows the placeholder note with the reassignment
  reason rather than a summary of foreign content

#### Scenario: Mislabeled text-marker content is reassigned

- **WHEN** a chapter's detected page range yields chunks whose heading-shaped
  text markers read `7.1`, `7.2` (magazine-style docs without payload
  identity) and chapter 7 is in the roster
- **THEN** those chunks are summarized under chapter 7's heading, not the
  wrong one's

#### Scenario: Foreign marker with no roster target is dropped, not mislabeled

- **WHEN** a bucket's chunk identity names a chapter that is not in the
  roster (including on a single-chapter delegation whose roster is only that
  chapter)
- **THEN** the chunk is dropped from the bucket
- **AND** the bucket, if left empty, shows the placeholder note instead of a
  summary under the wrong chapter heading

#### Scenario: Clean buckets proceed byte-identically

- **WHEN** every chunk in every bucket either carries no identity marker or
  self-identifies with its own chapter
- **THEN** the overview output is identical to the pre-guard behavior

### Requirement: Enumeration acknowledges roster gaps

When the multi-chapter enumeration's roster skips chapter numbers within its
span (the lowest detected chapter is above 1, or consecutive detected numbers
have gaps), the output SHALL include a coverage note naming the chapter
numbers that were not located, stating that the overview covers only the
listed chapters. A contiguous roster SHALL produce no note, and rosters of
fewer than three chapters (single-chapter and small-document full-fetch
paths) SHALL produce no note. On the legacy coverage path, which delegates
one chapter per call, the note SHALL be emitted once for the full roster —
not per delegation — and SHALL stream through the same channel as the chapter
headings so the stored answer matches what the reader saw.

#### Scenario: Roster starting above 1 is acknowledged

- **WHEN** chapter detection yields the roster 6–15 for a document whose
  overview is requested (chapters 1–5 not located)
- **THEN** the output contains a note that chapters 1–5 were not located in
  the document's detected structure and the overview covers the listed
  chapters only

#### Scenario: Contiguous roster stays silent

- **WHEN** the detected roster is 1–15 with no gaps
- **THEN** no coverage note appears

#### Scenario: Gap inside the roster is acknowledged

- **WHEN** the detected roster is 1–4, 6–15 (chapter 5 not located)
- **THEN** the coverage note names chapter 5 as not located

#### Scenario: Per-chapter delegation still yields one roster note

- **WHEN** the legacy coverage path delegates the enumeration one chapter per
  call for a roster of 6–15
- **THEN** exactly one coverage note naming chapters 1–5 appears in the
  output, not one per chapter
