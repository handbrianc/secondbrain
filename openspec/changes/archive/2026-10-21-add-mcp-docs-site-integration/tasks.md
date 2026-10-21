# MCP Docs Site Integration — Tasks

## 1. Site integration

- [x] 1.1 Write `docs/developer-guide/mcp.md` (client onboarding: pointing an MCP client at the server over HTTPS; compose quick start; tool examples; troubleshooting table mapping common failures: 401 → token, TLS errors → cert paths, tool errors → CLI diagnostics); link to `mcp-server/README.md` as the reference
- [x] 1.2 Add the nav entry in `mkdocs.yml`; update `docs/developer-guide/docker.md` (MCP-primary container, env-file wiring; remove the stale "application runs natively" framing)

## 2. Tests proving the unit of work

- [x] 2.1 `mkdocs build --strict` passes with the new page included (add to the docs gate / lint workflow)
- [x] 2.2 Manual check: nav renders the MCP page; the Docker guide contains no stale native-app framing (grep assertion added to `tests/test_docs/`)
