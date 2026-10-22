# MCP Search Tool — Tasks

## 1. Tool implementation

- [x] 1.1 Create `mcp-server/src/tools/search.rs`: `SearchParams` (`serde::Deserialize` + `schemars::JsonSchema`; query, top_k = 50, source, file_type, min_score = 0.46) registered via `#[tool]`
- [x] 1.2 Build the CLI argv: `["search", "--format", "json", (--top-k N)?, (--source S)?, (--file-type T)?, "--", query]`; unit-test the argv builder against every flag combination
- [x] 1.3 Parse CLI stdout JSON into typed structs mirroring the CLI's fields; apply the `min_score` filter; serialize the filtered results back to a compact JSON text block for the tool result
- [x] 1.4 Map outcomes: success → `CallToolResult::success(json text)`; CLI exit ≠ 0 → error result with truncated captured streams; invalid JSON → error result

## 2. Tests proving the unit of work

- [x] 2.1 Fixtures `mcp-server/tests/fixtures/stub_search_success.sh` (emits canned CLI JSON: mixed scores, full field set) and `stub_search_failure.sh` (exit 1 + stderr diagnostics) and `stub_search_garbage.sh` (exit 0, non-JSON stdout)
- [x] 2.2 Unit tests: argv construction per flag combination; `--` separator placement; threshold filtering (>= boundary inclusive; empty array passthrough); field preservation through parse/re-serialize
- [x] 2.3 Integration `tests/tools_search.rs` (full HTTP round trip, CLI_BIN pointed at fixtures): tools/call `search` → success JSON with only the high-scoring result; empty array success; failure → error result carrying diagnostics; garbage stdout → error result; hostile query with metacharacters/flag text → literal pass-through (stub echoes argv, tool treats it as the query)
- [x] 2.4 Optional real-CLI integration (marked `#[ignore]`, documented): run against the actual `secondbrain` CLI with the test Qdrant stack from `revise-compose-test-stack`
