# MCP TLS Support — Tasks

## 1. Implementation

- [x] 1.1 Create `mcp-server/src/tls.rs`: load `RustlsConfig::from_pem_file(cert, key)` from the config; typed errors naming `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` / `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH`
- [x] 1.2 In `main.rs`: when TLS disabled → `axum::serve` (unchanged path); when enabled → `axum_server::bind_rustls(addr, config)` serving the same router with the same graceful-shutdown token (SIGINT/SIGTERM)
- [x] 1.3 Add deps: `axum-server = { version = "0.8", features = ["tls-rustls"] }`; dev-dependency `rcgen` for test certs

## 2. Tests proving the unit of work

- [x] 2.1 Test helper: generate a self-signed cert/key pair in a temp dir via `rcgen` (PEM files) for the ephemeral-port tests
- [x] 2.2 Integration `tests/tls.rs`:
  - TLS-enabled server: HTTPS `GET /healthz` → 200 `{"status":"ok"}` (reqwest with rustls roots; `danger_accept_invalid_certs` for the self-signed test cert)
  - TLS-enabled server: HTTPS POST `tools/list` → 200 (skipped if transport proposal not yet merged — gate with a feature/compile-time check per dependency order)
  - plaintext request to the TLS port fails to complete a valid HTTP exchange
- [x] 2.3 Startup validation tests: enabled with no paths → exits before binding naming the missing variable; enabled with garbage cert file → exits naming `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH`; disabled → binds plaintext; disabled with garbage cert/key paths set → starts normally (variables ignored)
- [x] 2.4 `cargo clippy -- -D warnings` stays green
