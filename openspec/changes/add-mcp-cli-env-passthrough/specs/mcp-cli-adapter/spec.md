# MCP CLI Adapter

## ADDED Requirements

### Requirement: Environment passthrough and overrides

The adapter SHALL pass the server's full environment to the CLI process on every call, and SHALL apply per-call
environment overrides on top of it without mutating global state or leaking into subsequent calls.

#### Scenario: Inherited environment

- **WHEN** the server runs with `SECONDBRAIN_QDRANT_URL=https://qdrant.example:6333` in its environment
- **THEN** a CLI subprocess observes that variable (verified with an env-dumping stub)

#### Scenario: Per-call override

- **WHEN** a call specifies the override `SECONDBRAIN_SHOW_THINKING=0`
- **THEN** the child observes the overridden value

#### Scenario: No override leakage

- **WHEN** an override is applied on one call and a further call is made without it
- **THEN** the further call's child observes the inherited value, not the override
