# MCP TLS Support — Proposal

## Why

HTTPS encryption to the calling client is desired, but TLS must not be a mandatory property of the server: local and
single-user deployments should stay zero-config plaintext. This proposal therefore delivers TLS as an **optional
capability** (MAY-level requirements, off by default): a server built and deployed without TLS is fully functional
over plaintext HTTP, and enabling TLS is purely a deployment choice via configuration. rmcp provides no server-side
TLS — its HTTP server transport binds plain TCP — so the standard Rust pattern applies: serve the existing axum
router (health + `/mcp`) with `axum-server` 0.8 `tls-rustls` (rustls 0.23), configured from PEM cert/key files and
strictly validated **only when TLS is actually enabled**.

## What Changes

- **Optional TLS serving mode** driven by `SECONDBRAIN_MCP_HTTP_TLS_ENABLED` (already parsed by the scaffold config):
  - The capability requirement is MAY — approving this proposal does not mandate TLS in any deployment.
  - When disabled (default): current plaintext behavior, unchanged; the cert/key variables are ignored entirely.
  - When enabled: the same router is served over TLS using `SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH` /
    `SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH` (PEM). Missing/invalid files refuse startup with errors naming the variable.
- **Tests**: self-signed certificates generated in-test via `rcgen` (dev-dependency); HTTPS health check and MCP
  request round trips; plaintext-to-TLS-port failure; startup validation on the enabled path; disabled-with-garbage-
  cert-paths starts normally (variables ignored).
- TLS env wiring into compose/certs volumes happens in the Docker proposals; usage documentation in the docs
  proposals, documented as an optional capability.

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-server-runtime** — adds the optional TLS requirements.

## Dependencies

- Requires: `add-mcp-server-scaffold` (config fields), `add-mcp-server-runtime` (serving loop; the health-only TLS
  test), `add-mcp-streamable-http-transport` (for the HTTPS MCP test).

**Depended on by:** `revise-compose-production-stack` (cert volume), `add-mcp-readme-feature-docs`.

## Impact

**Code**: `mcp-server/src/main.rs` (TLS branch), new `mcp-server/src/tls.rs` (config loading), new tests.

**Dependencies**: `axum-server = { version = "0.8", features = ["tls-rustls"] }` (rustls 0.23),
`rcgen` (dev-dependencies only — test certificate generation).

**Out of scope**: auth (separate proposal), compose/docs wiring.

## Non-goals

- Making TLS mandatory or default-on in any deployment (capability stays opt-in by design).
- Automatic certificate provisioning (ACME/Let's Encrypt) — operators mount certs (compose proposal provides the
  volume); rotation is a restart.
- mTLS client certificates (possible follow-up).
- TLS for the Python CLI subprocess connections (the CLI talks to its own endpoints with its own settings).
