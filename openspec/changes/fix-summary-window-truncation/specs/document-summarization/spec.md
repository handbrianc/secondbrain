# Spec Delta

## Purpose

The bounded-window document summarizer behind the `secondbrain summarize`
CLI command: when a chapter's source exceeds the single-call input budget it
is summarized from multiple windows, and the summarizer must cover the full
source within its window cap while disclosing — never silently hiding — any
partial coverage.

## ADDED Requirements

### Requirement: Windowed summarization covers the full source

When the source excerpts exceed the single-call input budget, the
summarizer SHALL distribute window boundaries across the complete source
within its window cap (adaptive window size, each window within the
per-call input budget) instead of dropping trailing excerpts. The
summarizer SHALL NOT silently drop any contiguous tail of the source to
satisfy the window cap.

#### Scenario: Oversized chapter summarizes from spread windows

- **WHEN** a chapter's excerpts exceed the single-call budget and the
  default-size window count exceeds the window cap (e.g. ~393k chars against
  a 16k × 8 = 128k hard budget)
- **THEN** the windows cover the full source within the window cap (windows
  sized to the source)
- **AND** the merged summary draws on the chapter's late sections as well as
  its early ones

#### Scenario: Fully covered summary carries no note

- **WHEN** the windows cover the complete source within the window cap
- **THEN** the returned summary carries no coverage note

### Requirement: Impossible full coverage is disclosed

When the source exceeds what the window cap can hold even at the per-call
input budget, the summarizer SHALL sample evenly across the source's full
extent (never head-truncation) and SHALL prepend an explicit
partial-coverage note to the returned summary, so the CLI output labels the
summary as partial.

#### Scenario: Beyond-cap source is sampled and labeled

- **WHEN** the source exceeds the window cap's maximum total budget
- **THEN** the summarizer samples evenly across the source's full extent
- **AND** the returned summary begins with an explicit partial-coverage note
  before the summary body
