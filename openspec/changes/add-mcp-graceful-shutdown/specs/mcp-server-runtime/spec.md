# MCP Server Runtime

## ADDED Requirements

### Requirement: Graceful shutdown

The server SHALL shut down gracefully on SIGINT and SIGTERM, finishing in-flight requests before exit.

#### Scenario: Container-style termination

- **WHEN** the server receives SIGTERM while idle
- **THEN** it stops accepting connections and exits with status 0

#### Scenario: In-flight request completes

- **WHEN** the server receives SIGTERM while a request is being handled
- **THEN** the in-flight response is delivered before the process exits

#### Scenario: SIGINT termination

- **WHEN** the server receives SIGINT (interactive stop)
- **THEN** it exits with status 0 like on SIGTERM
