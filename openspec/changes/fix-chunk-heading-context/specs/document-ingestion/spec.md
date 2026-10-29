# Document Ingestion (delta)

## ADDED Requirements

### Requirement: Implausible heading labels bind to body text

At chunk assembly, a parser-labeled heading segment whose text fails the
heading plausibility test SHALL be treated as body text: it SHALL join the
adjacent accumulation (so a label stays bound to the description or command
text it introduces, e.g. "Restart chrony:" with the commands that follow)
instead of being flushed as a standalone structural segment. Such a joined
chunk SHALL NOT carry a heading element type. Heading-plausible segments keep
the current behavior — flushed standalone with their structural role — and
their chunk text streams SHALL remain byte-identical to the pre-change
behavior. Table, caption, TOC-entry, and navigation segments are unaffected.

#### Scenario: Run-in label joins the following text

- **WHEN** a document contains a heading-labeled segment "Restart chrony:"
  followed by the commands it introduces
- **THEN** the label is merged with the adjacent body accumulation instead of
  forming a standalone heading chunk
- **AND** the resulting chunk is classified `body` and carries the structural
  annotation of the enclosing section

#### Scenario: Plausible heading keeps standalone behavior

- **WHEN** a heading-labeled segment passes the plausibility test (e.g.
  "FSYNCS/SECOND")
- **THEN** it is still flushed standalone with its structural role and its
  chunk text is unchanged from the pre-change behavior

#### Scenario: Unlabeled and table streams are unchanged

- **WHEN** a document's segments carry no heading labels, or only table /
  caption / TOC-entry labels
- **THEN** the produced chunk text stream is byte-identical to the
  pre-change behavior
