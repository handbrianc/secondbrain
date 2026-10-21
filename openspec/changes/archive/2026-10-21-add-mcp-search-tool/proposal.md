# MCP Search Tool — Proposal

## Why

Semantic search is secondbrain's core retrieval capability, and the CLI already provides the machine-readable surface
the MCP server needs: `secondbrain search "query" --format json` emits a JSON array on stdout (the one fully
clean structured output in the CLI — logging goes to stderr and spinners suppress on non-TTY). This proposal exposes
it as the first MCP tool. One verified CLI quirk is handled here: `--min-score` filtering applies to table output
only (`src/secondbrain/cli/display.py`), so the threshold is applied by the server after parsing the JSON.

## What Changes

- **`search` MCP tool** (registered on the transport from `add-mcp-streamable-http-transport`):
  - Input: `query` (required), `top_k` (default 50), `source` (optional path filter), `file_type` (optional
    category/extension filter), `min_score` (default 0.46, applied server-side).
  - Execution: CLI `search <query> --format json [--top-k N] [--source S] [--file-type T]` via the CLI adapter,
    with `--` separating options from the positional query (no shell, no flag injection).
  - Output: tool result containing the parsed, threshold-filtered results as a JSON text block.
- Tool-level error mapping: CLI failure or malformed JSON → error result carrying diagnostics; empty result set →
  success with an empty array.

No Python changes.

## Capabilities

### New Capabilities

- *None.*

### Modified Capabilities

- **mcp-tools** — adds the search tool requirements.

## Dependencies

- Requires: `add-mcp-streamable-http-transport`, `add-mcp-cli-adapter`.

**Depended on by:** `add-mcp-readme-feature-docs`, `add-mcp-e2e-smoke`.

## Impact

**Code**: `mcp-server/src/tools/search.rs`, new tests.

**Dependencies**: none beyond existing.

## Non-goals

- Changing CLI search behavior (including making JSON mode honor `--min-score`; the server-side filter replicates the
  CLI default without touching Python).
- Ranking/reranking changes; result display formatting (table mode is CLI-only).
