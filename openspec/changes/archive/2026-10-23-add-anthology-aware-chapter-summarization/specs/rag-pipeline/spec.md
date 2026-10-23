# Rag Pipeline

## ADDED Requirements

### Requirement: Anthology documents summarize per part

The broad-coverage chapter pipeline SHALL detect anthology-shaped documents
(compilations of sub-reports that each restart their section numbering) and,
for those documents, SHALL construct per-part chapter maps and emit one
summary per part instead of a single global chapter map. Every part SHALL be
represented in the output; a part whose page range contains no body chunks
SHALL appear with the existing placeholder note.

#### Scenario: Compilation summarizes by its parts

- **WHEN** the user asks to summarize an anthology document whose 16
  sub-reports each restart numbering at 1
- **THEN** the output contains one correctly-titled entry per sub-report
  (e.g. "I.1 — From Vague Requirements to Well-Defined Epics (pages 3–13)")
- **AND** no entry summarizes content from a different sub-report's pages
- **AND** no entry carries the "no document content was retrieved"
  placeholder when the part's pages contain body text

#### Scenario: Single-book document keeps legacy chapter enumeration

- **WHEN** the user asks to summarize a single book with one monotone chapter
  sequence (e.g. a manual with "Chapter N" banners)
- **THEN** the pipeline uses the existing chapter-enumeration behavior
  unchanged

### Requirement: Anthology detection requires multi-signal agreement

The anthology detector SHALL claim a document only when at least 3
part-opener headings are present AND at least 2 parts' first numbered section
restarts at 1 AND the part count and per-part body support exceed a minimum
scale. Documents failing any signal SHALL take the legacy path.

#### Scenario: Part openers with restarts are detected

- **WHEN** heading-role chunks include ≥3 part openers
  ("I.1 · …", "II.1 · Volume 0 — …") and ≥2 parts restart at section 1
- **THEN** the document is routed to the per-part path

#### Scenario: Book without part openers is not detected

- **WHEN** a document has no part-labeled headings (single-book shapes:
  "Chapter N" banners or bare 1..N chapters)
- **THEN** the detector claims nothing and the legacy chapter path runs

### Requirement: Per-part maps pin sections from part-scoped headings

For an anthology, part boundaries SHALL derive from part-opener heading pages
(each part spans to the next opener; the last part to end of document), and
each part's sections SHALL be rostered and pinned from heading-role chunks
inside that part's page range. A section's pin SHALL be its own heading page.

#### Scenario: Section pins at its heading page inside its part

- **WHEN** part I.1 spans pages 3–12 and its section 5 heading sits on page 7
- **THEN** section 5's page range starts at page 7 and stays within the part

#### Scenario: Part boundaries from opener pages

- **WHEN** part openers sit on pages 3, 13, 22 (and the next on 37)
- **THEN** the parts' ranges are 3–12, 13–21, 22–36

### Requirement: Chapter-range agreement gate vets legacy maps

When the legacy chapter path derives a map with at least four chapters
comparable against first-section heading evidence, the pipeline SHALL
validate the map against that evidence (a chapter agrees when its final range
start stays within 2 pages of its provisional first-section heading pin).
Documents without at least four comparable evidence pins SHALL keep the
legacy path unchanged. If the agreement score falls below the calibrated
threshold, the pipeline SHALL NOT emit per-chapter summaries and SHALL fall
back to a whole-document overview. The gate SHALL NOT alter pins, ranges, or
the legacy path's own behavior when it passes.

#### Scenario: Known-good book passes the gate

- **WHEN** a single book's final range starts stay within 2 pages of the
  chapters' first-section heading pins (calibrated on corpus fixtures)
- **THEN** per-chapter enumeration proceeds exactly as before

#### Scenario: Document without section-heading evidence keeps legacy behavior

- **WHEN** a document's headings carry no first-section (`N.1`) shapes
  (fewer than four comparable evidence pins)
- **THEN** the gate does not run and legacy enumeration proceeds unchanged

#### Scenario: Wrong map degrades to a whole-document overview

- **WHEN** the derived ranges diverge from the document's first-section
  heading pins (e.g. chapters pinned from cross-reference text in an
  unrecognized anthology-like document)
- **THEN** the output is a whole-document overview (optionally with a note
  that per-chapter mapping was unavailable)
- **AND** no per-chapter entries summarize pages from the wrong chapter

### Requirement: Roster titles preserve quoted phrases

Chapter roster title capture SHALL include double-quote characters so titles
containing quoted phrases are captured whole.

#### Scenario: Quoted title survives capture

- **WHEN** a heading reads `2 First Principles: What "Well-Defined" Actually
  Means`
- **THEN** the roster title is the full heading text, not truncated at the
  quote
