# MCP Tools

## ADDED Requirements

### Requirement: Ingest tool

The MCP server SHALL expose an `ingest_documents` tool that ingests a file or directory by driving the secondbrain
CLI (`ingest <path>` with mapped optional flags) through the CLI adapter.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `ingest_documents`
- **AND** its input schema declares `path` (string, required), `recursive` (boolean, optional), `skip_existing`
  (boolean, optional), `chunk_size` (integer, optional), `chunk_overlap` (integer, optional), `batch_size` (integer,
  optional), `cores` (integer, optional)

#### Scenario: Successful ingest returns the CLI summary

- **WHEN** the tool is called with a path to an ingestable file and the CLI exits 0
- **THEN** the tool result is success carrying the CLI's stdout (its human-readable summary) as text content

#### Scenario: Relative paths resolve against the workspace root

- **WHEN** the tool is called with `path: "docs/report.pdf"` (existing file relative to `SECONDBRAIN_MCP_WORKSPACE_ROOT`)
- **THEN** the CLI is invoked with the resolved absolute path under the workspace root

#### Scenario: Absolute paths are passed through

- **WHEN** the tool is called with an absolute path
- **THEN** the CLI is invoked with that path as provided (validation is the confinement proposal's unit)

#### Scenario: Flags map to the CLI

- **WHEN** the tool is called with `recursive: true`, `skip_existing: false`, `chunk_size: 1024`,
  `chunk_overlap: 100`, `batch_size: 10`, `cores: 2`
- **THEN** the CLI is invoked with `-r`, `--no-skip-existing`, `--chunk-size 1024`, `--chunk-overlap 100`,
  `-b 10`, `-c 2` (verified against the argv-building unit tests)

#### Scenario: Missing path surfaces as a tool error

- **WHEN** the tool is called with a path that does not exist
- **THEN** the tool result is an error carrying the CLI's captured output (the CLI exits non-zero on missing paths)

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero for any reason (e.g. unsupported file, Qdrant unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis
