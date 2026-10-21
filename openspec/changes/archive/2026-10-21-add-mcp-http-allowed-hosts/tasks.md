# MCP HTTP Host Allow-List — Tasks

## 1. Configuration

- [x] 1.1 In `mcp-server/src/config.rs`: parse `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` as comma-separated entries, each trimmed, whitespace-only entries skipped; empty/unset = `None` (rmcp's `localhost`/`127.0.0.1`/`::1` default stays active); a value with no valid entry is a `ConfigError` naming the variable
- [x] 1.2 In `mcp-server/src/main.rs`: when the field is set, apply `StreamableHttpServerConfig::with_allowed_hosts(...)` on the existing construction; `None` leaves rmcp defaults; the existing `with_legacy_session_mode(false)` + `with_json_response(true)` are untouched
- [x] 1.3 Unit tests (inline in `config.rs`): unset → `None`; single host; multiple hosts with surrounding whitespace; entry with port preserved verbatim; whitespace-only entries skipped; entries-only-whitespace → error naming the variable

## 2. Tests proving the unit of work

- [x] 2.1 `mcp-server/tests/common/mod.rs`: `http_request` honors an explicit `Host` header (exactly one Host header on the wire)
- [x] 2.2 `mcp-server/tests/allowed_hosts.rs` (new): foreign `Host` with default config → 403 "Forbidden: Host header is not allowed"; configured host → 200 with the tool registry; a configured list replaces the localhost default (loopback then 403); portless entry matches any port; ported entry matches exactly (200 on match, 403 on mismatch)

## 3. Documentation

- [x] 3.1 `mcp-server/README.md`: `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` row in the `SECONDBRAIN_MCP_*` reference table (DNS-rebinding purpose, replace-not-merge, port semantics) + one sentence after the table
- [x] 3.2 `docs/developer-guide/mcp.md`: troubleshooting row mapping `403 Forbidden: Host header is not allowed` on `/mcp` to this variable or localhost; server-settings sentence names the host allow-list
- [x] 3.3 `.env.docker`: commented `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` entry with a style-matching note
  *Amended 2026-10-21 (deployment decision): the entry ships ACTIVE for this
  deployment's LAN hostname (redacted from the repository — placeholder
  `mcp.internal.example.com` in the committed file, real hostname in the
  uncommitted local copy) so remote MCP clients can call /mcp; the
  explanatory note above it remains commented as written. The variable's
  semantics are unchanged.*

## 4. Verification

- [x] 4.1 `cargo fmt --check` clean; `cargo clippy --all-targets -- -D warnings` clean; `cargo test` — 20/20 binaries green: 161 passed, 0 failed, 2 ignored (real-CLI round trips, unchanged)
- [x] 4.2 `pytest tests/test_docs/` — 5 passed (the doc-test parser picks the new variable up from `config.rs` and anchors its README row)
