# MCP Deployment

## ADDED Requirements

### Requirement: Bundled Qdrant is a managed dependency

The production compose stack's `qdrant` service SHALL declare a healthcheck, SHALL persist vector data in a named
volume, and SHALL carry an explicit, documented host-port decision (this deployment publishes 6333 for host-side
CLI tooling; commenting the ports block makes the service internal-only).

#### Scenario: Qdrant reports healthy

- **WHEN** `docker compose up -d` starts the qdrant service
- **THEN** its healthcheck passes on Qdrant's own health endpoint

#### Scenario: Vector data persists

- **WHEN** the qdrant container is recreated
- **THEN** the named volume's vector data survives

#### Scenario: Host port publish is explicit and documented

- **WHEN** the stack is up with the shipped configuration
- **THEN** Qdrant's 6333 port is published for host-side CLI tooling, with the in-file note documenting that
  commenting the ports block makes the service internal-only
- **AND** `docker compose config --quiet` passes
