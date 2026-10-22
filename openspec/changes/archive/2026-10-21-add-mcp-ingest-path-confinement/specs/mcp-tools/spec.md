# MCP Tools

## ADDED Requirements

### Requirement: Workspace path confinement

The ingest tool SHALL only ingest paths inside `SECONDBRAIN_MCP_WORKSPACE_ROOT`: the resolved target and the root
are canonicalized, and any target that escapes the root — including via `..` traversal, absolute paths outside the
root, or symlinks pointing outside — SHALL be rejected as a tool error before the CLI is invoked. Valid paths inside
the root continue to work as before.

#### Scenario: Valid paths still ingest

- **WHEN** the tool is called with a relative or absolute path that canonicalizes inside the workspace root
- **THEN** ingestion proceeds exactly as in the base ingest tool behavior

#### Scenario: Traversal escape is rejected

- **WHEN** the tool is called with `path: "../etc/passwd"` (resolving outside the workspace root)
- **THEN** the tool result is an error before any CLI subprocess starts
- **AND** the error describes the confinement rule and names `SECONDBRAIN_MCP_WORKSPACE_ROOT`

#### Scenario: Absolute escape is rejected

- **WHEN** the tool is called with an absolute path outside the workspace root
- **THEN** the tool result is an error before any CLI subprocess starts

#### Scenario: Symlink escape is rejected

- **WHEN** the workspace contains a symlink pointing outside the root and the tool is called with that symlink's path
- **THEN** the tool result is an error (canonicalization resolves the symlink to a path outside the root)
