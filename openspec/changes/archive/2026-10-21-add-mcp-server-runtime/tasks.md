# MCP Server Runtime Behaviors (serving) — Tasks

## 1. Serving implementation

- [x] 1.1 Replace the `main.rs` shell: build config, build the axum router with `GET /healthz` → 200 `application/json` `{"status":"ok"}`, bind `SECONDBRAIN_MCP_HTTP_BIND_ADDR`, serve until killed (no signal handling in this unit)
- [x] 1.2 Add deps: `axum = "0.8"`, `tokio = { version = "1", features = ["full"] }`

## 2. Tests proving the unit of work

- [x] 2.1 `tests/common/mod.rs` helper: boot the server on an ephemeral port (`127.0.0.1:0`) and return its address for integration tests
- [x] 2.2 `tests/health.rs`: `GET /healthz` → 200, `application/json`, `status == "ok"`
- [x] 2.3 `tests/bind.rs`: custom `SECONDBRAIN_MCP_HTTP_BIND_ADDR` is honored (default-bind covered by the scaffold's config unit tests)
