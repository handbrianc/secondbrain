# MCP Asynchronous Ingestion with Job Polling — Tasks

- [x] 1. Job registry module (`src/tools/jobs.rs`): sequential ids, kind,
  running/completed/failed state, terminal result text, bounded finished-job
  retention, and unit tests
- [x] 2. Server wiring: `SecondBrainServer` carries a shared
  `Arc<JobRegistry>` (`new()` parameter, `main.rs` construction, test
  harness updates), and the handler's router sum includes the new tool
- [x] 3. `ingest_documents` async mode: validations stay synchronous
  (confinement, argv build), CLI run spawns into a job, immediate job-id
  result; the sync mapping is refactored into a shared pure render so the
  job records exactly what the sync call would return
- [x] 4. `upload_document` async mode: base64/size/filename/existing-target/
  staging stay synchronous, CLI run + delete-after-ingest disposition spawn
  into the job, immediate job-id result, disposition sentence recorded
- [x] 5. `job_status` tool: single-job status (running/completed/failed with
  the recorded text, elapsed time) and the no-argument list; always-success
  results; unknown-id diagnostic; `tools/list` descriptions updated for the
  two extended tools and the new tool
- [x] 6. E2E (`tests/tools_jobs.rs`): async start returns a job id and not
  the ingest summary; polling reaches terminal state with the sync-equivalent
  text; async upload delete-parity (success deletes the staged file, failed
  ingest keeps it, delete-failure is reported without failing the job);
  invalid async calls fail immediately and create no job; unknown id; the
  sync contract is unchanged when `async_mode` is absent
- [x] 7. Docs: README tool table + asynchronous-ingestion section (start →
  poll example, in-memory/restart caveat), MCP guide rows; docs tests pass
- [x] 8. Full suite green (`cargo fmt --check`, `cargo clippy --all-targets
  -- -D warnings`, `cargo test`), `openspec validate add-mcp-async-ingestion
  --type change --strict`
