# MCP Documentation

## ADDED Requirements

### Requirement: Documentation integrated into the docs site

The project documentation site SHALL include an MCP server guide (`docs/developer-guide/mcp.md`) linked from the
navigation, and the Docker guide SHALL reflect the MCP server as the container's primary function.

#### Scenario: Docs build gate

- **WHEN** `mkdocs build --strict` runs
- **THEN** it passes with the MCP pages included and no broken links

#### Scenario: Docker guide accuracy

- **WHEN** a reader consults the Docker guide
- **THEN** it describes the MCP-server-primary container and env-file configuration,
  with no stale "application runs natively / Docker only for Qdrant" statement
