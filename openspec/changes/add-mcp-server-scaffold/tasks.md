# MCP Server Scaffold — Tasks

## 1. Crate skeleton

- [x] 1.1 Create `mcp-server/Cargo.toml` for crate `secondbrain-mcp` (edition 2024, `rust-version = "1.88"`; deps at this stage: `serde`, `thiserror` — later proposals add `rmcp`/`axum`/`tokio`/`tracing` as their behavior lands)
- [x] 1.2 Create `mcp-server/src/main.rs`: entrypoint shell that resolves the configuration and exits 0 on success (binding/serving arrive in `add-mcp-server-runtime`)
- [x] 1.3 Add `mcp-server/target/` to the root `.gitignore`
- [x] 1.4 Create `mcp-server/tests/` tree with `tests/common/mod.rs` helper for spawning the binary as an integration subject

## 2. Configuration module

- [x] 2.1 Implement `mcp-server/src/config.rs` parsing the full `SECONDBRAIN_MCP_*` table (see spec) with defaults; validation errors name the offending variable
- [x] 2.2 Unit tests (inline in `config.rs`): defaults when unset, overrides applied, invalid bind address / timeout / boolean rejected with variable named in the error, empty auth token treated as unset

## 3. Tests proving the unit of work

- [x] 3.1 `tests/config_startup.rs` (integration, spawns the binary): valid configuration (defaults and a custom override) → exit 0; invalid `SECONDBRAIN_MCP_*` value → non-zero exit with the variable named on stderr

## 4. CI

- [x] 4.1 Add `.github/workflows/rust-checks.yml`: on push/PR touching `mcp-server/**` — `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` (pinned stable toolchain, working-directory `mcp-server`)
