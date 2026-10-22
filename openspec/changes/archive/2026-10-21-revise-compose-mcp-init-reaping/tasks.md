# MCP Server PID 1 Reaping (docker-init) — Tasks

- [x] 1. Add `init: true` with the rationale comment to the `mcp-server` service of `docker-compose.yml`
- [x] 2. Add the same to the `mcp-server` service of `docker-compose.test.yml`
- [x] 3. Validate both stacks: `docker compose config`
- [x] 4. Document the reaping rationale and the symptom/fix pair in `docs/developer-guide/docker.md`
  (production-stack and test-stack sections, plus a troubleshooting entry)
- [x] 5. Verify live: recreate the stack, confirm docker-init holds the PID 1 seat
  (shim → docker-init → server), drive an ingest-family tool call, and confirm no defunct
  processes accumulate under the server or the init — and that the zombies accumulated by the
  previous server process are gone with the recreate
