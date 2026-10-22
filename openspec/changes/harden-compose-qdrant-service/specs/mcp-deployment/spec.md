# MCP Deployment

## ADDED Requirements

### Requirement: Bundled Qdrant is a managed dependency

The production compose stack's `qdrant` service SHALL declare a healthcheck, SHALL persist vector data in a named
volume, and SHALL NOT publish a host port by default (internal network communication only).

#### Scenario: Qdrant reports healthy

- **WHEN** `docker compose up -d` starts the qdrant service
- **THEN** its healthcheck passes on Qdrant's own health endpoint

#### Scenario: Vector data persists

- **WHEN** the qdrant container is recreated
- **THEN** the named volume's vector data survives

#### Scenario: No default host port

- **WHEN** the stack is up with default configuration
- **THEN** no host port is bound for qdrant (the port-publish block remains available, commented, for local access)
- **AND** `docker compose config --quiet` passes
