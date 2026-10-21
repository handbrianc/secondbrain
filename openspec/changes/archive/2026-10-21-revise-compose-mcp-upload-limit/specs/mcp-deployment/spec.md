# MCP Deployment

## ADDED Requirements

### Requirement: 100 MB upload cap in the production stack

The production stack SHALL accept `upload_document` submissions with decoded
content up to 104857600 bytes (100 MB), configured via
`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` in `.env.docker`. The derived `/mcp`
request-body budget SHALL continue to be computed from the cap as
`ceil(cap × 4/3) + 1 MiB` and SHALL be enforced at both the rmcp transport
and the axum body-limit layer. The CLI's own 100 MiB per-file processing cap
SHALL remain the ceiling applied at ingest time.

#### Scenario: A large PDF uploads in one call

- **WHEN** a client submits a file larger than the compiled-in 10 MB default
  (but at most 104857600 bytes decoded)
- **THEN** the submission passes the tool's budget check, is staged, and is
  ingested — no HTTP 413 and no over-cap tool error

#### Scenario: The body budget scales with the cap

- **WHEN** a `/mcp` request body exceeds the derived budget
  (`ceil(104857600 × 4/3) + 1 MiB` ≈ 141 MB)
- **THEN** the request is rejected with HTTP 413 by both enforcement points
  before reaching a tool handler

#### Scenario: Over-cap decoded content still fails cleanly

- **WHEN** a submission's decoded content exceeds 104857600 bytes while its
  base64 body fits the derived budget
- **THEN** `upload_document` returns an error result naming
  `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`, nothing is stored, and the process
  continues serving
