# MCP Upload Cap 100 MB — Tasks

- [x] 1. Set `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES=104857600` (active, with the
  derivation and CLI-cap comment) in `.env.docker`
- [x] 2. Validate the compose config: `docker compose config`
- [x] 3. Note the stack's 100 MB cap in `docs/developer-guide/docker.md`
  (production-stack section)
- [x] 4. Verify live: after the image rebuild + stack restart, upload a file
  larger than the old 10 MB default through `upload_document` and confirm it
  is accepted (the derived body budget ≈ 141 MB is in effect) — verified with
  a 12,000,000-byte decoded submission: accepted, staged, job started; the
  CLI skipped the unknown extension (nothing stored) and the staged file was
  deleted per the success contract
