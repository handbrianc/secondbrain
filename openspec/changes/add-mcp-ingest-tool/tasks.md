# MCP Ingest Tool — Tasks

## 1. Tool implementation

- [x] 1.1 Create `mcp-server/src/tools/ingest.rs`: `IngestParams` (path, recursive = false, skip_existing = true, chunk_size, chunk_overlap, batch_size, cores — `serde::Deserialize` + `schemars::JsonSchema`) registered via `#[tool]`
- [x] 1.2 Path resolution (no validation at this stage): relative paths joined against `SECONDBRAIN_MCP_WORKSPACE_ROOT` and made absolute; absolute paths passed through
- [x] 1.3 Build the CLI argv: `["ingest", <resolved-path>, (-r)?, (--no-skip-existing)?, (--chunk-size N)?, (--chunk-overlap N)?, (-b N)?, (-c N)?]`; unit-test the argv builder per flag combination (default `skip_existing: true` → no `--no-skip-existing`)
- [x] 1.4 Map outcomes: success → `CallToolResult::success(stdout text)` with a one-line prefix noting the output is the CLI summary; exit ≠ 0 → error result with truncated captured streams

## 2. Tests proving the unit of work

- [x] 2.1 Fixture workspace under `mcp-server/tests/fixtures/workspace/` (a real text file, a nested dir) and `stub_ingest.sh` (validates the path argument it receives and prints a canned summary; exits 1 on missing paths)
- [x] 2.2 Unit tests: relative resolution against the workspace root; absolute pass-through; argv mapping per flag combination including the `--no-skip-existing` inversion
- [x] 2.3 Integration `tests/tools_ingest.rs` (full HTTP round trip, CLI_BIN at the stub, workspace root at the fixture workspace):
  - relative and absolute ingest of the real file → success carrying the summary
  - missing path → error (CLI exit path)
  - CLI failure (stub exits 1 on a sentinel path) → error with diagnostics
- [x] 2.4 Optional real-CLI integration (marked `#[ignore]`): ingest a fixture via the real CLI against the test Qdrant stack
