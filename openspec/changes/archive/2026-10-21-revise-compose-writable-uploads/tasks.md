# Writable Upload Staging Mounts — Tasks

- [x] 1. Layer `./workspace/uploads:/data/workspace/uploads:rw` into the `mcp-server` service of
  `docker-compose.yml` (the workspace stays `:ro`), with the host-directory prerequisite in the comment
- [x] 2. Layer the same mount over the fixture workspace in `docker-compose.test.yml`; commit
  `tests/fixtures/mcp_workspace/uploads/` (`.gitkeep`)
- [x] 3. Document the staging mount and the create-before-`up`/ownership prerequisite: `mcp-server/README.md`
  (compose section), `docs/developer-guide/docker.md` (mounts list, test stack), `docs/developer-guide/mcp.md`
  (quick start)
- [x] 4. Add commented `SECONDBRAIN_MCP_UPLOAD_DIR` / `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` entries to `.env.docker`
- [x] 5. Validate: `docker compose config` for both stacks; a container-level proof that the layered read-write
  mount is writable by a non-root user over a read-only parent (and that the read-only parent itself rejects
  writes, and that a compose-auto-created root-owned directory rejects the non-root user without the handover —
  the pre-entrypoint failure mode)
- [x] 6. Image entrypoint `scripts/docker_entrypoint.sh` (root-only staging-directory handover resolved like the
  server's config, then drop to the runtime user; non-root starts skip the handover) wired in the `Dockerfile`
  (gosu, `ENTRYPOINT`, pre-created default staging dir)
- [x] 7. Update the documentation from the create-before-`up` prerequisite to the automatic handover
  (`mcp-server/README.md`, `docs/developer-guide/docker.md`, `docs/developer-guide/mcp.md` quick start +
  troubleshooting row, `.env.docker`, compose comments)
- [x] 8. Validate the handover with a probe image built from the same base and the same Dockerfile lines
  (auto-created root-owned staging dir healed → write as the runtime user succeeds; corpus write still rejected;
  the process runs as the runtime user; a rootless start skips the handover); `docker compose config` both stacks
- [x] 9. Exclude the entrypoint from `.dockerignore`'s host-side-tooling sweep (`scripts/*` +
  `!scripts/docker_entrypoint.sh` — a wholesale `scripts` exclusion cannot be re-included per-file), so the
  image build's `COPY scripts/docker_entrypoint.sh` resolves; verified with a real `docker compose build`
