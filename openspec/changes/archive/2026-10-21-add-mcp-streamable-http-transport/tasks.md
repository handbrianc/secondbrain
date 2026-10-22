# MCP Streamable HTTP Transport — Tasks

## 1. Service construction

- [x] 1.1 Create `mcp-server/src/server.rs`: `#[tool_router]` / `#[tool_handler(name = "secondbrain-mcp", version = env!("CARGO_PKG_VERSION"), instructions = ...)]` ServerHandler with an **empty** tool router; instructions summarize ingestion, search, chat sessions
- [x] 1.2 In `main.rs`, construct `StreamableHttpService` with `StreamableHttpServerConfig::default().with_legacy_session_mode(false).with_json_response(true)` and mount via `axum::Router::nest_service("/mcp", service)` alongside `/healthz`

## 2. Tests proving the unit of work

- [x] 2.1 `tests/transport.rs` (raw HTTP, ephemeral port, per rmcp's `test_streamable_http_json_response.rs` pattern):
  - POST `tools/list` with `Accept: application/json, text/event-stream` → 200, `application/json`, empty `tools` array, `serverInfo.name == "secondbrain-mcp"`, instructions mention all three capability groups
  - POST `tools/call` unknown tool → JSON-RPC error result (no crash)
  - POST without acceptable `Accept` header → 406
  - GET `/mcp` → 405; DELETE `/mcp` → 405
- [x] 2.2 `tests/transport.rs`: stateless assertions — request with no initialize and no `Mcp-Session-Id` header succeeds; response carries no `Mcp-Session-Id` header
- [x] 2.3 `tests/interop.rs`: rmcp client via `StreamableHttpClientTransport::from_uri(...)` performs `tools/list` → succeeds
- [x] 2.4 Confirm `cargo clippy -- -D warnings` and `cargo test` stay green (CI workflow from the scaffold picks these up automatically)
