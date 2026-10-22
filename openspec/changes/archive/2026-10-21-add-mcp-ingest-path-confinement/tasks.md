# MCP Ingest Path Confinement — Tasks

## 1. Implementation

- [x] 1.1 In `ingest.rs`: after relative/absolute resolution, canonicalize target and workspace root (`fs::canonicalize`); require `target.starts_with(canonical_root)`; on failure return a tool error describing the rule and naming `SECONDBRAIN_MCP_WORKSPACE_ROOT` — before building argv or spawning

## 2. Fixtures

- [x] 2.1 Add to `mcp-server/tests/fixtures/workspace/`: an outbound symlink `escape -> ../../../etc` (target outside the root)

## 3. Tests proving the unit of work

- [x] 3.1 Unit tests: canonical root+target containment check; rejection cases (traversal, absolute-outside, symlink escape) each yield an error naming the variable
- [x] 3.2 Integration `tests/tools_ingest_confinement.rs` (full HTTP round trip, CLI_BIN at `stub_ingest.sh` — the stub records every spawn, so the test asserts **no spawn occurred** on rejection):
  - traversal escape → error, no spawn
  - absolute-outside → error, no spawn
  - symlink escape → error, no spawn
  - relative-inside and absolute-inside still succeed (spawn occurred, summary returned)
- [x] 3.3 Confirm the base ingest tool tests (`tests/tools_ingest.rs`) still pass unchanged
