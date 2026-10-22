# MCP Tools

## ADDED Requirements

### Requirement: Search tool

The MCP server SHALL expose a `search` tool that performs semantic search by driving the secondbrain CLI
(`search <query> --format json` with mapped optional flags) through the CLI adapter, and SHALL return the results as
a JSON text block in the tool result.

#### Scenario: Tool is discoverable

- **WHEN** a client requests `tools/list`
- **THEN** the list contains a tool named `search`
- **AND** its input schema declares `query` (string, required), `top_k` (integer, optional), `source` (string,
  optional), `file_type` (string, optional), `min_score` (number, optional)

#### Scenario: Successful search returns filtered results

- **WHEN** the tool is called with a query and the CLI (stub or real) returns a JSON array of result objects
- **THEN** the tool result content is a JSON array containing exactly the returned results whose `score` is greater
  than or equal to the effective `min_score` (default 0.46)
- **AND** the results preserve the CLI's fields (e.g. `source_file`, `chunk_text`, `score`, `chunk_id`, `page_number`)

#### Scenario: Server-side threshold applied

- **WHEN** the tool is called with `min_score: 0.9` and the CLI returns results scored 0.95 and 0.5
- **THEN** only the 0.95 result is returned (the CLI JSON output is not threshold-filtered; the server applies it)

#### Scenario: Empty result set is success

- **WHEN** the search yields no results (CLI exits 0, JSON array is empty)
- **THEN** the tool result is success with an empty JSON array

#### Scenario: CLI failure maps to a tool error

- **WHEN** the CLI exits non-zero (e.g. Qdrant unreachable)
- **THEN** the tool result is an error carrying the CLI's captured output for diagnosis (truncated to a bounded size)

#### Scenario: Unparseable output maps to a tool error

- **WHEN** the CLI exits 0 but stdout is not valid JSON
- **THEN** the tool result is an error indicating malformed CLI output (not a server panic)

### Requirement: Safe argument passing for search

The search tool SHALL pass user input to the CLI as argv elements only, never through a shell, and SHALL prevent a
query from being parsed as CLI flags.

#### Scenario: Hostile query is inert

- **WHEN** the tool is called with a query containing `--top-k 1 && rm -rf /` or other metacharacters/flag-like text
- **THEN** the query reaches the CLI as a single literal positional argument (after a `--` separator) and is searched as-is
