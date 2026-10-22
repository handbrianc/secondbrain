# MCP Server Ingest Worker Cap (2) — Tasks

- [x] 1. Set `SECONDBRAIN_MAX_WORKERS=2` with the rationale comment in `.env.docker`
- [x] 2. Validate the compose config: `docker compose config`
- [x] 3. Document the worker-cap rationale in the production-stack section of
  `docs/developer-guide/docker.md` (and correct the two stale `cli` references there)
- [x] 4. Add the OOM/`BrokenProcessPool` troubleshooting entry to `docs/developer-guide/docker.md`
- [x] 5. Verify live: recreate the stack, confirm the server container receives the cap
  (`get_config().max_workers == 2` in-container) and `/healthz` stays healthy
- [x] 6. Verify end-to-end: re-ingest the file that OOM-crashed (`UserManual_x175.pdf`)
  with the cap in effect — the cap is active but the file still OOM-killed a single
  parse spike (cgroup peak 5.8G, `oom_kill` 0→1 in 43 s, `BrokenProcessPool`); the spike
  was isolated to the structure-probe → full-docling route: the same file, same
  `--cores 2`, with `SECONDBRAIN_PDF_STRUCTURE_PROBE_ENABLED=false` ingested in 48 s
  (601 points stored). Flipping the probe default is a separate trade-off decision
  (structural labels vs. heavy-parse survivability), not part of this change
