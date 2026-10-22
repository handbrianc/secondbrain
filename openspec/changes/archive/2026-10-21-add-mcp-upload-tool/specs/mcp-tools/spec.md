# MCP Tools

## ADDED Requirements

### Requirement: Upload tool

The MCP server SHALL expose an `upload_document` tool that stores a submitted document inside the workspace and
ingests it by driving the same confined CLI ingest invocation the `ingest_documents` tool uses. Its input schema
SHALL declare `filename` (string, required), `content_base64` (string, required), `skip_existing` (boolean,
optional), `chunk_size` (integer, optional), `chunk_overlap` (integer, optional), `batch_size` (integer, optional),
and `cores` (integer, optional), and the tool description SHALL state that the document is stored in the workspace
and ingested.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `upload_document`
- **AND** its input schema declares `filename` and `content_base64` as required strings plus the optional ingest
  parameters

#### Scenario: Successful upload-and-ingest

- **WHEN** the tool is called with a valid filename and base64 content, the file is stored, and the CLI ingest
  exits 0
- **THEN** the tool result is success carrying text with the stored path relative to the workspace root and the
  CLI's ingest summary
- **AND** the staged file is deleted from the upload directory

#### Scenario: Ingest parameters map to the CLI

- **WHEN** the tool is called with `skip_existing: false` and `chunk_size: 1024`
- **THEN** the CLI is invoked with `--no-skip-existing` and `--chunk-size 1024` (verified against the shared argv
  tests used by `ingest_documents`)

### Requirement: Upload content validation

The server SHALL validate submitted content before storing anything: `content_base64` MUST decode as base64, and
the decoded size MUST NOT exceed `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (default 10485760 bytes = 10 MB — a
conservative floor below the CLI's 100 MiB per-file processing cap; raise the variable to admit larger files).
Invalid base64 or oversize content SHALL produce a tool error and nothing SHALL be stored.

#### Scenario: Oversize content is rejected

- **WHEN** the decoded content exceeds `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Invalid base64 is rejected

- **WHEN** `content_base64` is not valid base64
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Default limit applies when unset

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is unset or empty
- **THEN** the effective decoded-size limit is 10485760 bytes

#### Scenario: Configured limit overrides the default

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is set to a positive value (e.g. 52428800)
- **THEN** the effective decoded-size limit is that value

### Requirement: Upload storage

The server SHALL store uploads under `SECONDBRAIN_MCP_UPLOAD_DIR`, defaulting to `uploads` inside
`SECONDBRAIN_MCP_WORKSPACE_ROOT`. The configured directory SHALL be validated at startup to resolve inside the
workspace root (fail-fast config error naming the variable otherwise, including via symlink) and SHALL be created on
demand when absent. The stored filename SHALL be the provided `filename` reduced to its bare name (directory
components stripped); a filename that is empty or reduces to `.` or `..` SHALL be rejected. When the derived path
already exists, the server SHALL reject the call with a tool error naming the existing path and SHALL NOT overwrite
the existing file.

#### Scenario: Default location

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_DIR` is unset
- **THEN** uploads are stored in `<workspace root>/uploads`

#### Scenario: Upload dir outside the workspace root fails startup

- **WHEN** `SECONDBRAIN_MCP_UPLOAD_DIR` resolves (lexically or through symlinks) outside
  `SECONDBRAIN_MCP_WORKSPACE_ROOT`
- **THEN** the server fails to start with a config error naming `SECONDBRAIN_MCP_UPLOAD_DIR`

#### Scenario: Directory components are stripped

- **WHEN** the tool is called with `filename: "nested/report.pdf"`
- **THEN** the file is stored as `report.pdf` under the upload directory

#### Scenario: Unusable filename is rejected

- **WHEN** `filename` is empty or reduces to `.` or `..`
- **THEN** the tool result is an error and nothing is stored

#### Scenario: Collision is rejected without overwrite

- **WHEN** the upload dir already contains `report.pdf` and another upload derives the same name
- **THEN** the tool result is an error naming the existing path and the existing file is unchanged

### Requirement: Ingestion after upload

After storing the file, the server SHALL ingest it through the shared ingest invocation of `ingest_documents`
(resolve → confine → argv → CLI adapter), mapping `skip_existing` (default true), `chunk_size`, `chunk_overlap`,
`batch_size`, and `cores` to the CLI flags. The server SHALL NOT introduce a new ingestion pipeline. When the CLI
exits 0, the server SHALL delete the stored file — the upload directory is transient staging and the ingested
content lives in the knowledge base — while keeping the stored path in the result; a deletion that itself fails
SHALL be reported inside the otherwise-successful result and SHALL NOT fail the call. When the CLI
exits non-zero after the file was stored (e.g. unsupported extension, Qdrant unreachable), the tool result SHALL be
an error carrying the stored path and the CLI's captured output, and the stored file SHALL remain in place for
later re-ingest via `ingest_documents`.

#### Scenario: Ingest failure after successful storage

- **WHEN** the file is stored but the CLI ingest exits non-zero
- **THEN** the tool result is an error carrying the stored path and the CLI's captured output for diagnosis
- **AND** the stored file remains in place

#### Scenario: Staged file deleted after a successful ingest

- **WHEN** the CLI ingest exits 0 after the file was stored
- **THEN** the stored file is deleted from the upload directory
- **AND** the tool result still carries the stored path as the source path recorded in the knowledge base

#### Scenario: A failed deletion is reported without failing the call

- **WHEN** the CLI ingest exits 0 but deleting the stored file fails
- **THEN** the tool result remains a success carrying the ingest summary
- **AND** the result reports the deletion failure and that the file remains in place

#### Scenario: Ingestion reuses confinement

- **WHEN** the stored file's path is passed to the ingest invocation
- **THEN** it passes the same workspace-root confinement check as any `ingest_documents` path before the CLI starts
