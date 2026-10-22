# MCP Structured Logging — Tasks

## 1. Implementation

- [x] 1.1 In `main.rs`: initialize `tracing-subscriber` with a filter built from the config's log level before binding; emit lifecycle events (startup, bind address, shutdown path readiness) via `tracing`
- [x] 1.2 Add deps: `tracing`, `tracing-subscriber`

## 2. Tests proving the unit of work

- [x] 2.1 `tests/logging.rs`: run the server with `SECONDBRAIN_MCP_LOG_LEVEL=warn`, make a request, capture stderr → no debug/info events present, warn/error events are
- [x] 2.2 `tests/logging.rs`: run with `debug` → debug-level request events present
