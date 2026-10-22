//! The MCP tools: each module registers its tools on the shared
//! [`SecondBrainServer`] through its own `#[tool_router]` impl block, and
//! drives the secondbrain CLI through the adapter (`crate::cli`).

pub(crate) mod chat;
pub(crate) mod ingest;
pub(crate) mod jobs;
pub(crate) mod search;
pub(crate) mod upload;

use rmcp::model::{CallToolResult, ContentBlock};

use crate::cli::CliError;

/// Upper bound for one captured CLI stream echoed into a tool error result,
/// so a chatty CLI cannot flood the caller.
pub(crate) const MAX_STREAM_CHARS: usize = 1_000;

/// Renders an adapter failure (unresolved binary, spawn failure, deadline)
/// as caller-ready text: the message names the offending
/// `SECONDBRAIN_MCP_*` variable.
///
/// `pub(crate)` so the async ingest jobs (`add-mcp-async-ingestion`) record
/// the same text a synchronous call would carry.
pub(crate) fn render_adapter_error(error: &CliError) -> String {
    error.to_string()
}

/// Maps an adapter failure onto a tool-level error result: caller-visible,
/// and the message names the offending `SECONDBRAIN_MCP_*` variable.
pub(crate) fn adapter_error(error: &CliError) -> CallToolResult {
    CallToolResult::error(vec![ContentBlock::text(render_adapter_error(error))])
}

/// Wraps a rendered outcome — a success flag plus caller-ready text — into
/// the matching tool result shape.
///
/// The async jobs (`add-mcp-async-ingestion`) record outcomes in exactly
/// this (success, text) form, so a detached job's recorded text maps back
/// onto the same result shape the synchronous call returned.
pub(crate) fn tool_result(success: bool, text: String) -> CallToolResult {
    if success {
        CallToolResult::success(vec![ContentBlock::text(text)])
    } else {
        CallToolResult::error(vec![ContentBlock::text(text)])
    }
}

/// Maps the startup resolution failure carried by the server onto a
/// tool-level error result (the message already names the variable).
pub(crate) fn resolution_error(message: &str) -> CallToolResult {
    CallToolResult::error(vec![ContentBlock::text(message.to_string())])
}

/// Renders a failed CLI run's bounded diagnostics for a tool error result.
pub(crate) fn describe_exit(code: i32, stdout: &str, stderr: &str) -> String {
    format!(
        "the secondbrain CLI failed with exit code {code}\n\
         --- stdout ---\n{}\n\
         --- stderr ---\n{}",
        truncate(stdout, MAX_STREAM_CHARS),
        truncate(stderr, MAX_STREAM_CHARS),
    )
}

/// Truncates captured CLI output for diagnostics, keeping the head and
/// marking the cut.
pub(crate) fn truncate(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    let head: String = text.chars().take(max_chars).collect();
    format!("{head}\n… [truncated]")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_keeps_short_text_whole() {
        assert_eq!(truncate("short", 10), "short");
        assert_eq!(truncate("", 10), "");
        assert_eq!(truncate("exactlyten!", 11), "exactlyten!");
    }

    #[test]
    fn truncate_marks_the_cut_and_counts_characters() {
        let truncated = truncate("é".repeat(15).as_str(), 10);
        assert_eq!(truncated.chars().take(10).count(), 10);
        assert!(truncated.ends_with("… [truncated]"), "{truncated}");
    }

    #[test]
    fn describe_exit_carries_both_bounded_streams() {
        let described = describe_exit(3, "out", "err");
        assert!(described.contains("exit code 3"), "{described}");
        assert!(described.contains("--- stdout ---\nout"), "{described}");
        assert!(described.contains("--- stderr ---\nerr"), "{described}");
    }
}
