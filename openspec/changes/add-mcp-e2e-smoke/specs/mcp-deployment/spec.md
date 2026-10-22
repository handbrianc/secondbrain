# MCP Deployment

## ADDED Requirements

### Requirement: End-to-end MCP smoke across both stacks

A parameterized smoke script SHALL drive a real MCP client flow over HTTP(S) against either compose stack (`test` or
`prod`): health → `tools/list` → `ingest_documents` of a fixture document → `search` returns the ingested document →
`chat_send` (only when a test LLM is configured), with teardown on exit (including failure).

#### Scenario: Full ingestion-search cycle on the test stack

- **WHEN** `scripts/mcp_e2e_smoke.sh --stack test` runs
- **THEN** it starts the test stack, waits for health, lists tools, ingests the fixture document through the MCP tool,
  and a subsequent MCP search returns that document's content
- **AND** the stack is torn down on exit

#### Scenario: Chat smoke when an LLM is configured

- **WHEN** the smoke runs and the test environment provides a usable LLM configuration
- **THEN** the `chat_send` step executes and returns a non-empty answer bound to a session id
- **WHEN** no LLM configuration is available
- **THEN** the chat step is skipped with an explicit warning and the rest of the smoke still validates

#### Scenario: Production stack smoke parity

- **WHEN** `scripts/mcp_e2e_smoke.sh --stack prod` runs
- **THEN** the same flow completes against the production stack (chat step gated identically)
