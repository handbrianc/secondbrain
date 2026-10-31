# Rag Pipeline (delta)

## ADDED Requirements

### Requirement: Per-source resolution of numbered chapter and section queries

In a collection with multiple ingested sources, resolving a numbered chapter
or section request against stored structure trees SHALL be per-source. When
the requested number exists in more than one source and the query names no
source, the pipeline SHALL produce per-source results (each labeled with its
source) or refuse with an explicit ambiguity prompt naming the candidate
sources; it SHALL NOT silently select a single source by an internal
heuristic such as per-document chunk count. When the query resolves a source
mention, resolution SHALL scope chapter and section resolution to that
source. When the requested number exists in exactly one source, resolution
SHALL proceed against that source directly.

#### Scenario: Same chapter number in two sources, no source mention

- **WHEN** chapter 15 exists in both an ingested VirtualBox manual and an
  ingested Proxmox VE guide, and the query is "summarize chapter 15" with no
  source mention
- **THEN** the pipeline resolves chapter 15 per source (per-source summaries
  each labeled with their source) or prompts for disambiguation naming both
  sources
- **AND** neither source's chapter 15 (High Availability vs VBoxManage) is
  silently answered for the other

#### Scenario: Source mention scopes resolution

- **WHEN** the query mentions a source that resolves via the document router
  (e.g. "in the proxmox guide, summarize chapter 15")
- **THEN** chapter and section resolution scope to that source alone
- **AND** a larger unrelated source cannot outrank it

#### Scenario: Number unique to one source resolves directly

- **WHEN** the requested number exists in exactly one ingested source
- **THEN** resolution proceeds against that source without prompting

### Requirement: Cross-source window purity and attribution

A chapter or section summary window assembled from a stored tree SHALL
contain chunks from exactly one source. When a multi-source answer combines
per-source parts, each part SHALL be attributed to its source in the
formatted context, so the generated answer can carry per-source attribution.
Chunks from a second source SHALL NOT silently fill or extend a window of
another source.

#### Scenario: Window never mixes sources

- **WHEN** a chapter window for one source is assembled from a collection
  holding two sources whose chapter numbers collide
- **THEN** the window contains chunks from that source only
- **AND** chunks of the colliding chapter from the other source are excluded

#### Scenario: Multi-source answer carries per-source attribution

- **WHEN** a per-source result set is formatted as generation context
- **THEN** each part's context lines identify its source (file name)
- **AND** the model can attribute each section of the answer to its source
