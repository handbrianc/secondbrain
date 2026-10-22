# MCP Graceful Shutdown — Tasks

## 1. Implementation

- [x] 1.1 In `main.rs`: add the graceful-shutdown future (`tokio::signal::ctrl_c` + SIGTERM listener) and `axum::serve(...).with_graceful_shutdown(...)`

## 2. Tests proving the unit of work

- [x] 2.1 `tests/shutdown.rs`: send SIGTERM to a running server → process exits 0 after draining
- [x] 2.2 `tests/shutdown.rs`: in-flight request variant — start a slow-holding request (e.g. a streaming probe route or concurrent request), send SIGTERM, assert the response completes and exit status is 0
- [x] 2.3 `tests/shutdown.rs`: SIGINT variant → exit 0
