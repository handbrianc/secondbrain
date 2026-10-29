# Spec Delta: conversational-rag

## ADDED Requirements

### Requirement: Reasoning streams render under one policy on every path

All code paths that render a streamed chat answer SHALL apply a single
policy to LLM reasoning ("thinking") content: reasoning MAY be displayed
only as a distinct, collapsed element (a terminal fold or a one-line
collapsed summary), never interleaved into the answer text stream as if it
were answer content, and expansion of the full reasoning text SHALL be
available only on explicit user opt-in. This policy SHALL hold identically
for the guarded per-window generation path and for the overview/reduce
summarization path; no path may forward raw reasoning deltas into the
answer stream by default.

#### Scenario: Reduce-path reasoning collapses instead of streaming inline

- **WHEN** a document summary generates through the overview/reduce
  streaming path and the provider emits reasoning deltas between answer
  sections
- **THEN** the terminal shows each reasoning block as a collapsed element
  (or one-line collapsed summary), visually distinct from the answer
- **AND** no reasoning text is concatenated into the answer text stream
  by default

#### Scenario: Guarded-path behavior does not regress

- **WHEN** a chat answer generates through the guarded per-window path
- **THEN** reasoning continues to be consumed internally (spiral
  detection) and is never forwarded to the terminal, as today

#### Scenario: User opts in to full reasoning text

- **WHEN** the user enables the explicit show-thinking option
- **THEN** the full reasoning text is displayed under the collapsed
  element treatment
- **AND** with the option disabled (default), only the collapsed form
  appears

### Requirement: Stored history carries the finalized answer text

The assistant message persisted to session history SHALL be the finalized
overview text (content channel only, never reasoning).  The overview/reduce
path SHALL stream committed content to the terminal live while the draft
forms.  On the happy path, where finalization makes no mutation, the stored
message equals the displayed text byte for byte, so `secondbrain chat
--history` reproduces exactly the answer the user saw — without reasoning
blocks.  Repair passes (leak-scrub hold replacement, low-temperature
retries, dead-stream continuation, finalize post-pass trims) MAY leave the
terminal showing draft text the stored finalized answer supersedes; that
divergence SHALL be documented and pinned by tests rather than hidden.

#### Scenario: History reproduces the displayed answer on a clean stream

- **WHEN** a streamed chat answer finishes with no repair mutation and is
  saved to session history
- **THEN** the stored assistant message text equals the content that was
  written to the terminal, byte for byte
- **AND** `chat --history` shows the answer without the reasoning blocks
  that streamed

#### Scenario: Repair passes may supersede already-streamed draft text

- **WHEN** the streaming leak-scrubber or a retry pass alters the
  accumulated draft before the answer is finalized
- **THEN** the stored message is the finalized text (reasoning-free)
- **AND** any divergence between the earlier-streamed draft text and the
  stored final text is an accepted, test-pinned behavior, not a silent
  corruption of the stored message
