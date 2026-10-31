# Spec Delta

## ADDED Requirements

### Requirement: Map-reduce summary windows cover the full source

When a summary source exceeds the single-pass budget, the map pass SHALL
cover the complete source within the configured map-call limit: the source
SHALL be re-split into windows sized to the source (larger windows for
larger sources, each still within the per-window context budget) so every
part of the source reaches a map call. The pipeline SHALL NOT drop trailing
windows, or any other contiguous slice of the source, to satisfy the
map-call limit.

#### Scenario: Oversized chapter maps in full

- **WHEN** a chapter's source exceeds the single-pass budget and splits into
  more windows than the map-call limit at the default window size (e.g. 99
  windows for a ~197-page chapter)
- **THEN** the source is re-split into at most the map-call limit of windows
  covering the chapter's full page range
- **AND** the map call count stays within the limit
- **AND** every page of the chapter is represented in at least one map window

#### Scenario: Small sources keep single-pass behavior

- **WHEN** a summary source fits within the single-pass budget
- **THEN** one streamed call covers the complete source as today, with no
  map pass

### Requirement: Partial summary coverage is disclosed honestly

When full coverage is impossible because the source needs more map windows
than the limit allows even at the per-window size ceiling, the pipeline
SHALL take an evenly spaced, page-ordered sample across the full source —
never a head-truncation slice — and SHALL emit an explicit partial-coverage
note ahead of the summary, in the style of the existing whole-document
fallback note. The note SHALL be part of the stored answer as well as the
displayed output, preserving the summary path's display/storage parity
contract. The reduce-stage framing SHALL reflect actual coverage: the
"cover every part in order" instruction SHALL be used only when the parts
cover the complete source; partial runs SHALL use framing that presents the
input as an evenly spread sample.

#### Scenario: Floor-limited source degrades to a sampled overview with a note

- **WHEN** a source exceeds the single-pass budget and cannot fit the
  map-call limit even at the per-window size ceiling
- **THEN** the map pass windows are sampled evenly across the source's full
  page range
- **AND** a partial-coverage note precedes the summary on screen and in the
  stored answer
- **AND** the reduce prompt does not claim complete sequential coverage

#### Scenario: Full coverage keeps framing and no note

- **WHEN** the re-split source fits within the map-call limit completely
- **THEN** no partial-coverage note is emitted or stored
- **AND** the reduce framing instructs covering every part in order, as
  today

#### Scenario: Display/storage parity holds with the note

- **WHEN** a partial-coverage summary completes
- **THEN** the stored history answer contains the same coverage note and
  overview text the terminal displayed
