# Spec Delta: rag-pipeline

## ADDED Requirements

### Requirement: Chapter windows admit only in-range source chunks

When the broad-coverage per-chapter pipeline assembles the generation
context for one chapter, it SHALL admit source chunks only from that
chapter's own derived page range. A chunk whose page lies outside the
range SHALL NOT be admitted, except for a chunk that straddles the range
boundary, which MAY be admitted under a bounded one-page boundary
tolerance. Content from a neighboring chapter (e.g. a previous chapter's
closing sections) SHALL NOT fill a chapter's window.

#### Scenario: Tail of the previous chapter does not bleed in

- **WHEN** a book is summarized by chapter and chapter N's derived range
  begins at page 433 while chapter N−1's content (e.g. its closing
  "Cluster Resource Scheduler" sections) occupies pages 432–433
- **THEN** chapter N's generation context contains no chunks from outside
  chapter N's range beyond the boundary tolerance
- **AND** chapter N's summary is built from chapter N's own material
  (backup storage and backup modes), not from chapter N−1's material

#### Scenario: Boundary-straddling chunk is tolerated

- **WHEN** a body chunk opens at the last page of chapter N−1 and carries
  chapter N's opening sentence
- **THEN** the chunk may be admitted to chapter N's window under the
  one-page boundary tolerance
- **AND** chapter N−1's summary remains unchanged

### Requirement: Coverage gaps in chapter windows are surfaced explicitly

For each chapter whose generation context is assembled, the pipeline SHALL
compute window-composition statistics (count and share of in-range versus
foreign-range chunks). When a chapter's window is empty of in-range
content, or its foreign-range share dominates the window, the pipeline
SHALL surface an explicit coverage note in that chapter's output entry —
in the same style as the existing "no document content was retrieved"
placeholder — instead of silently emitting a summary built from foreign
material. Chapters with healthy window composition SHALL keep the current
output unchanged.

#### Scenario: Foreign-dominated window produces a coverage note

- **WHEN** a chapter's window contains almost exclusively chunks from
  outside the chapter's derived range (e.g. the neighboring chapter's
  closing sections)
- **THEN** the chapter's entry carries an explicit note that the chapter's
  own content could not be retrieved and the summary is partial
- **AND** the entry does not present foreign content as if it were the
  chapter's content

#### Scenario: Healthy window keeps current behavior

- **WHEN** a chapter's window is composed predominantly of in-range chunks
- **THEN** the chapter's summary is emitted exactly as today, with no
  coverage note
