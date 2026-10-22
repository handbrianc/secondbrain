# MCP Upload Tool — Tasks

## 1. Configuration

- [x] 1.1 `mcp-server/src/config.rs`: parse `SECONDBRAIN_MCP_UPLOAD_DIR` (default `<workspace_root>/uploads`) and
  `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (default 10485760 = 10 MB, configurable upward for larger workloads; reject 0
  and non-numeric) with fail-fast `ConfigError`s naming the variable; unit tests for defaults, overrides, invalid
  values (a value above the CLI's 100 MiB per-file cap is accepted at upload but the CLI's own gate still applies
  at ingest time)
- [x] 1.2 Startup validation: the upload dir must resolve inside the workspace root (lexical normalization when
  missing, canonicalization when present — same rules as ingest confinement); outside root → fail-fast config error
- [x] 1.3 `mcp-server/README.md`: config table rows for both variables (defaults: `<workspace_root>/uploads`,
  10485760 = 10 MB), an `upload_document` row in the tool reference table, a `### upload_document` section
  (parameter table with defaults, result shape, error behavior, and the base64 payload-overhead note — the wire
  payload is ~4/3 of the file size), and a JSON-RPC wire example of an upload call;
  `tests/test_docs/test_mcp_docs.py` enforces every registered tool name and every `SECONDBRAIN_MCP_*` literal
- [x] 1.4 Coordinate the MkDocs guide: when `docs/developer-guide/mcp.md` lands
  (`add-mcp-docs-site-integration`), add `upload_document` to its tool examples and troubleshooting table

## 2. Shared ingest invocation (behavior-preserving refactor)

- [x] 2.1 Extract the `ingest_documents` run flow into a shared helper in `mcp-server/src/tools/ingest.rs`
  (resolve → confine → build argv → `CliRunner.run`), parameterized by resolved ingest params; the tool calls the
  helper unchanged and existing tool tests stay green
- [x] 2.2 Unit-test the helper's parameter mapping (`skip_existing: false` → `--no-skip-existing`, chunk/batch/cores
  flags) against the argv builder

## 3. Upload tool

- [x] 3.1 Register `upload_document` in the `server.rs` tool router; `UploadParams` (`filename` required,
  `content_base64` required, `skip_existing` default true, `chunk_size`, `chunk_overlap`, `batch_size`, `cores`
  optional — `serde::Deserialize` + `schemars::JsonSchema`); tool description states it stores the document in the
  workspace and ingests it
- [x] 3.2 Content validation: decode `content_base64` (invalid encoding → tool error, nothing stored); decoded size
  over `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` → tool error, nothing stored; unit tests for decode failures, oversize,
  limit boundary
- [x] 3.3 Filename handling: reduce `filename` to its bare name (strip directory components); unusable filename
  (empty, `.`/`..` after reduction) → tool error; collision with an existing file → tool error naming the existing
  path, no overwrite; unit tests
- [x] 3.4 Store the decoded bytes in the upload dir (create the dir on demand), then invoke the shared ingest helper
  with the mapped ingest params
- [x] 3.5 Outcome mapping: success → tool result text carrying the stored path (relative to the workspace root) and
  the CLI summary; stored-but-ingest-failed → tool error carrying the stored path + captured CLI output, file
  retained; unit tests per outcome
- [x] 3.6 `mcp-server/Cargo.toml`: add the `base64` dependency; raise the `/mcp` request body limit in `main.rs`
  from the framework default to a value derived from `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (≥ 4/3 × limit + JSON
  framing slack); e2e check that a call at the configured limit is accepted

## 4. Security and confinement integration tests

- [x] 4.1 Confinement interplay: an uploaded file's ingest path passes `confine()`; an upload dir resolving outside
  the workspace root (including via symlink) is rejected at startup
- [x] 4.2 Auth inheritance: with `SECONDBRAIN_MCP_AUTH_TOKEN` set, an unauthenticated `tools/call` of
  `upload_document` is rejected at the HTTP layer by the existing `/mcp` middleware (no upload-specific auth code)

## 5. End-to-end integration tests

- [x] 5.1 `mcp-server/tests/tools_upload.rs` (full HTTP round trip through `/mcp`, `CLI_BIN` at the stub, workspace
  root at the fixture): successful upload → result text with stored relative path + summary; CLI failure sentinel →
  error with diagnostics and file retained; oversize content → error, nothing stored; invalid base64 → error;
  unusable filename → error; collision → error naming the existing path; a call at the configured size limit is
  accepted (body-limit check)
- [x] 5.2 Fixture additions: a `stub_ingest.sh`-style CLI stub that validates the path argument it receives (inside
  the workspace root) and prints a canned summary; an uploadable real text file encoded as base64
- [x] 5.3 Optional real-CLI integration (marked `#[ignore]`): upload a fixture via `upload_document` and ingest it
  through the real CLI against the test Qdrant stack (`docker-compose.test.yml`)

## 6. Delete-after-ingest amendment

- [x] 6.1 A successful ingest deletes the staged file (`StagedDisposition`: deleted / delete-failed / kept): the
  success result reports the deletion, a deletion that itself fails is reported inside the success, and failed
  ingests keep the file for re-ingest — unit tests in `src/tools/upload.rs`, integration updates in
  `tests/tools_upload.rs` and `tests/tools_upload_confinement.rs`, plus an end-to-end delete-failure case
  (`STUCK.txt` sentinel: the stub swaps the stored file for a same-named directory so the post-ingest cleanup
  fails deterministically)
- [x] 6.2 Spec delta, proposal, and the README/MCP docs updated for the deletion contract
