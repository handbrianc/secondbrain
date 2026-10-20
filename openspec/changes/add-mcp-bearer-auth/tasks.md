# MCP Bearer Auth — Tasks

## 1. Implementation

- [x] 1.1 Create `mcp-server/src/auth.rs`: tower middleware/layer reading `SECONDBRAIN_MCP_AUTH_TOKEN` from config; skip when unset/empty; skip path `/healthz`; parse `Authorization: Bearer <token>`; constant-time compare via `subtle`; on failure respond 401 with `WWW-Authenticate: Bearer`
- [x] 1.2 Wire the layer around the `/mcp` route only in `main.rs` (health route stays outside)
- [x] 1.3 Add dep `subtle = "2"`

## 2. Tests proving the unit of work

- [x] 2.1 Integration `tests/auth.rs` (ephemeral port):
  - token unset → POST `tools/list` without header → 200
  - token set → missing header → 401 + `WWW-Authenticate: Bearer`; wrong token → 401; prefix token → 401; `Basic` scheme → 401; correct token → 200
  - token set → `GET /healthz` without header → 200
- [x] 2.2 Unit tests (inline): header parsing edge cases (case-insensitive scheme, extra spaces, empty bearer, multiple header values) → reject; constant-time compare exercised for equal/mismatched/length-differing inputs
- [x] 2.3 `cargo clippy -- -D warnings` stays green
