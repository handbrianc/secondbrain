# MCP HTTP Host Allow-List — Proposal

## Why

rmcp 3.5.1's `StreamableHttpService` ships DNS-rebinding protection: requests to `/mcp` whose `Host` header is
outside its built-in allow-list (`localhost`, `127.0.0.1`, `::1`) are rejected with `403 Forbidden: Host header is
not allowed`. This protection was silently active in the server delivered by `add-mcp-streamable-http-transport`
(the default `StreamableHttpServerConfig` was used verbatim), which surfaced in real use: a client addressing the
server by its LAN hostname (`mcp.internal.example.com`) got every `/mcp` request rejected while `/healthz`
(owned by the axum router, outside the rmcp service) kept answering. A hostname must be configurable, but turning
the protection off must not be the easy path — the allow-list needs to be a configuration surface with the secure
default preserved.

## What Changes

- **New config variable** `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` in the `SECONDBRAIN_MCP_*` table:
  - Comma-separated `Host`-header entries for `/mcp`, each trimmed; whitespace-only entries are skipped.
  - **Empty/unset = unset** (the table's uniform rule) → rmcp's built-in `localhost`/`127.0.0.1`/`::1` default stays
    active — the secure behavior is the default.
  - A value with no valid entry at all is a fail-fast `ConfigError` naming the variable (the table's fail-fast
    contract).
  - When set, the list **replaces** rmcp's default (it is passed to `StreamableHttpServerConfig::with_allowed_hosts`).
- **Matching semantics** (rmcp, pinned by tests): an entry without a port matches that host on any port; an entry
  with a port must match exactly; the check applies only to the rmcp `/mcp` service — `/healthz` is unaffected.
- **No wildcard support**: there is no `*` entry, and `disable_allowed_hosts()` (empty list = accept any Host) is
  deliberately not exposed — disabling DNS-rebinding protection entirely remains a code-level decision.
- **Tests**: config unit tests (parsing, trimming, fail-fast) and integration tests pinning the 403 contract
  (foreign Host rejected by default), the configured-host path (200 through the tool registry), replace-not-merge
  semantics, and port-exact matching.
- **Docs**: `mcp-server/README.md` config-table row, `docs/developer-guide/mcp.md` troubleshooting row
  (403 → this variable or localhost), `.env.docker` commented entry.

No Python changes. The implementation landed as post-verification follow-up work and is already green
(161 passed / 2 ignored Rust, docs tests 5/5); this proposal records the unit of work and its capability spec.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime**: adds the Host-header allow-list requirement to the MCP endpoint surface.

## Dependencies

- Requires: `add-mcp-server-scaffold` (the `SECONDBRAIN_MCP_*` configuration table and its fail-fast contract),
  `add-mcp-streamable-http-transport` (the rmcp `/mcp` service whose default allow-list this configures).

**Depended on by:** nothing (self-contained hardening/configuration follow-up).

## Impact

**Code**: `mcp-server/src/config.rs` (variable, field, parsing, unit tests), `mcp-server/src/main.rs`
(conditional `with_allowed_hosts`), `mcp-server/tests/common/mod.rs` (`http_request` honors an explicit `Host`
header), `mcp-server/tests/allowed_hosts.rs` (new).

**Docs/config**: `mcp-server/README.md`, `docs/developer-guide/mcp.md`, `.env.docker`.

**Dependencies**: none beyond existing (rmcp 3.5.1 already in tree).

**Verification already run**: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`
(20/20 binaries green — 161 passed, 0 failed, 2 ignored real-CLI round trips), `pytest tests/test_docs/` (5 passed).

## Non-goals

- Disabling Host validation via configuration (code-level decision only).
- Wildcard host patterns.
- Origin-header configuration (`allowed_origins` remains rmcp's default; browser-origin policy is out of scope).
- Changes to `/healthz`, auth, TLS, or the tool registry.
