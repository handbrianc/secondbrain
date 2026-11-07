# Document Structure (delta)

## ADDED Requirements

### Requirement: Chunk annotation follows in-chunk heading position

When ingest annotates stored chunks with chapter identity, a chunk whose own
text carries a numbered chapter-heading form SHALL anchor that chunk to the
numbered chapter when the form appears in the chunk's first half, and SHALL
switch ownership starting with the next chunk when the form appears in the
chunk's second half (the chunk itself stays with the prior chapter). A chunk
that opens a page with chapter M's heading SHALL be annotated for chapter M
even when a page-granular outline span assigns that page to another chapter.
Chunks carrying no heading-form text SHALL follow outline-span ownership as
today, except that an evidence-armed chapter assignment SHALL carry through
subsequent heading-free chunks — across page boundaries, ahead of
outline-span fill — until the next chunk-anchored heading re-arms ownership.
An assignment is evidence-armed when it comes from a first-half heading
anchor or from the switch a second-half heading starts with the next chunk;
outline-span fill alone arms nothing. Annotation SHALL remain deterministic.

#### Scenario: Heading on the page's first chunk anchors it

- **WHEN** a chapter's printed heading (e.g. "9. Krippendorff's …") sits at
  the start of page 10's first chunk while the outline span assigns page 10
  to chapter 10
- **THEN** that chunk is annotated `chapter 9` with heading-path naming
  chapter 9's title
- **AND** chapter 10's annotation starts at chapter 10's own heading
  position, not at the page boundary

#### Scenario: Second-half heading switches with the next chunk

- **WHEN** a chunk's text carries the next chapter's heading form in its
  second half (the chapter opens mid-chunk after body text)
- **THEN** that chunk remains annotated for the prior chapter
- **AND** the following chunk is annotated for the new chapter

#### Scenario: Heading-free chunks keep span ownership

- **WHEN** a document's chunks carry no numbered heading forms (the parser
  also missed them and nothing was synthesized)
- **THEN** annotation follows outline-span ownership exactly as today
- **AND** previously-annotated documents re-annotate identically when their
  chunks carry no heading-form text

#### Scenario: Armed assignment carries across the page break

- **WHEN** chapter 10's heading ("10. Co-Creation: …") anchors page 10's
  last chunk, chapter 10's outline span covers only page 10, and chapter
  11's heading appears later on page 11
- **THEN** page 11's heading-free chunks before chapter 11's heading are
  annotated for chapter 10 (the evidence-armed inheritance), not chapter
  11's span fill
- **AND** chunks from chapter 11's own heading onward are annotated for
  chapter 11

### Requirement: Numbered headings missed by the parser are synthesized

When the document parser's heading detection misses numbered chapter headings
that are present in the document's text stream, structure capture SHALL
synthesize heading nodes for them using the shared heading-form extraction
(dotted `N.M` section forms and bare `N.` chapter forms, the bare form
requiring the separating dot), so the stored tree's chapter roster matches
the document's printed roster. Synthesized nodes SHALL carry the same payload
shape as parser-produced nodes and SHALL NOT displace parser-produced
headings for the same number.

#### Scenario: Missed chapter headings are synthesized

- **WHEN** the parser misses chapter headings (the report case: 7 of 21 —
  chapters 3, 5, 9, 12, 13, 14, 20 — missed by docling)
- **THEN** the stored tree contains heading nodes for the missed chapters
  synthesized from the text stream
- **AND** the tree's chapter roster covers every printed chapter

#### Scenario: Register rows are not headings

- **WHEN** the text stream contains a source-register row like
  "7 Wikipedia — The Design of Everyday Things (Doet…)" (no separating dot
  after the number)
- **THEN** no heading node is synthesized from it

#### Scenario: Parser-produced headings are not displaced

- **WHEN** the parser already produced a heading node for chapter N and the
  text stream also contains chapter N's printed heading form
- **THEN** the parser-produced node is kept unchanged
- **AND** no duplicate node for the same number is added

### Requirement: Captured structure trees persist observably

When structure capture succeeds for an ingested document, the captured tree
SHALL be persisted to the structure store for that source. A persistence
failure SHALL be logged with the source and node count rather than silently
leaving a captured tree unpersisted.

#### Scenario: Outline capture reaches the store

- **WHEN** a PDF with a 56-node bookmark outline is ingested
- **THEN** the structure store holds those nodes for the source
- **AND** query-time structure lookups see the stored tree

#### Scenario: Persistence failure is visible

- **WHEN** persisting a captured tree raises or writes zero nodes after a
  successful capture
- **THEN** the ingest logs the failure with the source and node count
- **AND** the failure is not silent in the logs
