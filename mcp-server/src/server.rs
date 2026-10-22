//! The MCP server handler: server metadata and the tool registry.
//!
//! Each tool module (`src/tools/`) registers its tools on this server via
//! its own `#[tool_router]` impl block; the handler below composes those
//! routers, so `tools/list` and `tools/call` serve every registered tool.

use rmcp::{ServerHandler, tool_handler};

use crate::cli::CliRunner;
use crate::tools::jobs::JobRegistry;

use std::path::PathBuf;
use std::sync::Arc;

/// The secondbrain MCP server.
///
/// The CLI runner is resolved once at startup (in `main`); a failed
/// resolution is carried here so every tool call can report it — naming
/// `SECONDBRAIN_MCP_CLI_BIN` — while the server itself stays up.
///
/// The server is `Clone` and one instance is built per stateless request;
/// process-wide state must therefore be shared explicitly (the job registry
/// below).
#[derive(Clone)]
pub struct SecondBrainServer {
    /// The CLI runner, or the rendered resolution failure (the variable is
    /// named) that tool calls report until the configuration is fixed.
    pub(crate) cli: Result<CliRunner, String>,
    /// The workspace root relative ingest paths resolve against
    /// (`SECONDBRAIN_MCP_WORKSPACE_ROOT`).
    pub(crate) workspace_root: PathBuf,
    /// The directory uploads are stored in (`SECONDBRAIN_MCP_UPLOAD_DIR`),
    /// validated at startup to resolve inside the workspace root.
    pub(crate) upload_dir: PathBuf,
    /// The decoded-size cap for submitted upload content
    /// (`SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`).
    pub(crate) upload_max_bytes: u64,
    /// The shared registry of asynchronous ingest/upload jobs
    /// (`add-mcp-async-ingestion`): job ids must mean the same job to every
    /// request, so one registry is created at startup and shared through
    /// this `Arc` — the stateless transport builds a fresh handler per
    /// request, and the detached job tasks outlive any single request.
    pub(crate) jobs: Arc<JobRegistry>,
}

impl SecondBrainServer {
    /// Builds the server around an already-resolved CLI runner (or the
    /// rendered resolution failure, naming `SECONDBRAIN_MCP_CLI_BIN`, that
    /// every tool call reports), the workspace root, the upload
    /// configuration, and the shared job registry.
    pub fn new(
        cli: Result<CliRunner, String>,
        workspace_root: PathBuf,
        upload_dir: PathBuf,
        upload_max_bytes: u64,
        jobs: Arc<JobRegistry>,
    ) -> Self {
        Self {
            cli,
            workspace_root,
            upload_dir,
            upload_max_bytes,
            jobs,
        }
    }
}

// `version` is deliberately omitted: the macro then emits
// `Implementation::new(name, env!("CARGO_PKG_VERSION"))`, keeping serverInfo
// structurally tied to the crate version. (The attribute value itself must be
// a string literal — `version = env!(...)` does not parse in rmcp 3.5.)
#[tool_handler(
    router = (
        Self::chat_history_router() + Self::chat_list_router() + Self::chat_send_router()
            + Self::ingest_router() + Self::job_status_router() + Self::search_router()
            + Self::upload_router()
    ),
    name = "secondbrain-mcp",
    instructions = "secondbrain exposes three capability groups over MCP: file \
                    ingestion (add documents to the knowledge base), semantic \
                    search (query ingested documents), and chat sessions \
                    (conversational retrieval over the knowledge base). Run \
                    tools/list to discover the registered tools."
)]
impl ServerHandler for SecondBrainServer {}
