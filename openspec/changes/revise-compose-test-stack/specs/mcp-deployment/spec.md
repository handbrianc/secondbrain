# MCP Deployment

## ADDED Requirements

### Requirement: Test compose stack includes the MCP server

The test compose stack SHALL include an `mcp-server` service built from the project Dockerfile, wired to the test
Qdrant instance and the repository's test configuration (mock embedding provider, fixture workspace, isolated SQLite
path), exposed on a host port distinct from the production stack (8081).

#### Scenario: Test stack brings up the server

- **WHEN** `docker compose -f docker-compose.test.yml up -d` runs
- **THEN** the `mcp-server` service starts and becomes healthy against the test Qdrant
- **AND** the existing test Qdrant service behavior (host port 6334, test volume) is unchanged

#### Scenario: Test stack configuration validates

- **WHEN** `docker compose -f docker-compose.test.yml config --quiet` runs
- **THEN** it passes

### Requirement: Test services entry point stays coherent

The local test-services script SHALL bring up the extended test stack so the Python test suite and MCP verification
share one environment.

#### Scenario: Local developer workflow

- **WHEN** `scripts/start_test_services.sh` runs
- **THEN** both the test Qdrant and the test `mcp-server` service are started and awaited healthy
