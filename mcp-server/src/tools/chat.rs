//! The chat MCP tools (`add-mcp-chat-*`): each wraps one surface of the
//! secondbrain CLI's `chat` command through the adapter.
//!
//! `chat_send` submits one query into a session (generating a UUID v4
//! session id when the caller passes none) and extracts the answer from the
//! CLI's stdout, stripping the reasoning-indicator lines.
//! `chat_list_sessions` passes the CLI's session table through.
//!
//! The CLI's chat outputs are human-readable (no JSON mode); the tools pass
//! them through as text content — a documented limitation shared by the
//! send, history, and session-listing tools.

use std::ffi::OsString;

use rmcp::ErrorData;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::schemars::JsonSchema;
use rmcp::{tool, tool_router};
use serde::Deserialize;

use crate::cli::CliOutcome;
use crate::server::SecondBrainServer;

use super::{adapter_error, describe_exit, resolution_error};

/// Input of the `chat_send` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct ChatSendParams {
    /// The question to ask, appended to the session's context.
    pub query: String,
    /// The chat session to continue; a fresh UUID v4 session is generated
    /// (and returned) when omitted.
    #[serde(default)]
    pub session_id: Option<String>,
    /// Number of chunks to retrieve (the CLI default is 20).
    #[serde(default)]
    pub top_k: Option<u64>,
    /// LLM temperature (the CLI default is 0.1).
    #[serde(default)]
    pub temperature: Option<f64>,
    /// LLM model override.
    #[serde(default)]
    pub model: Option<String>,
}

/// Registers the `chat_send` tool on the shared server
/// (`add-mcp-chat-send-tool`).
#[tool_router(router = chat_send_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Send one query into a chat session.
    #[tool(
        description = "Send one query into a secondbrain chat session (retrieval-augmented \\\
                       answer over the ingested knowledge base). Generates and returns a fresh \\\
                       session id when none is given; pass the returned id to continue the \\\
                       conversation. Returns {\"session_id\", \"answer\"} as a JSON text block."
    )]
    async fn chat_send(
        &self,
        Parameters(params): Parameters<ChatSendParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run_send(self, params).await
    }
}

/// Runs one chat send: resolve or generate the session id, build the argv,
/// drive the CLI with the thinking-suppression override, and map every
/// outcome onto a tool result.
async fn run_send(
    server: &SecondBrainServer,
    params: ChatSendParams,
) -> Result<CallToolResult, ErrorData> {
    let runner = match &server.cli {
        Ok(runner) => runner,
        Err(message) => return Ok(resolution_error(message)),
    };

    let session_id = params
        .session_id
        .clone()
        .unwrap_or_else(generate_session_id);
    let argv = send_argv(&session_id, &params);
    match runner.run(&argv, &[thinking_off()]).await {
        Ok(CliOutcome::Success { stdout, .. }) => {
            let payload = serde_json::json!({
                "session_id": session_id,
                "answer": extract_answer(&stdout),
            });
            Ok(CallToolResult::success(vec![ContentBlock::text(
                payload.to_string(),
            )]))
        }
        Ok(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => Ok(CallToolResult::error(vec![ContentBlock::text(
            describe_exit(code, &stdout, &stderr),
        )])),
        Err(error) => Ok(adapter_error(&error)),
    }
}

/// Generates a fresh chat session id (UUID v4).
fn generate_session_id() -> String {
    uuid::Uuid::new_v4().to_string()
}

/// The per-call environment override that reduces the CLI's stdout to one
/// strippable reasoning-indicator line plus the streamed answer.
fn thinking_off() -> (String, String) {
    ("SECONDBRAIN_SHOW_THINKING".to_string(), "0".to_string())
}

/// Builds the CLI argv: `chat --session <id> [--top-k N] [--temperature T]
/// [--model M] -- <query>`.
///
/// The `--` separator puts the query after the options, so flag-like query
/// text can never be parsed as a CLI flag; the adapter passes every element
/// verbatim (no shell).
fn send_argv(session_id: &str, params: &ChatSendParams) -> Vec<OsString> {
    let mut argv = vec![
        OsString::from("chat"),
        OsString::from("--session"),
        OsString::from(session_id),
    ];
    if let Some(top_k) = params.top_k {
        argv.push(OsString::from("--top-k"));
        argv.push(OsString::from(top_k.to_string()));
    }
    if let Some(temperature) = params.temperature {
        argv.push(OsString::from("--temperature"));
        argv.push(OsString::from(temperature.to_string()));
    }
    if let Some(model) = &params.model {
        argv.push(OsString::from("--model"));
        argv.push(OsString::from(model));
    }
    argv.push(OsString::from("--"));
    argv.push(OsString::from(&params.query));
    argv
}

/// The reasoning-indicator prefix: any line starting with it is stripped
/// from the CLI's stdout (the `▸` opens a single grapheme cluster, so the
/// match is anchored at the line's first cluster).
const THINKING_PREFIX: &str = "▸ Thinking:";

/// Extracts the answer from the CLI's stdout: every `▸ Thinking:`-prefixed
/// line is stripped, and the remainder is trimmed of a single trailing
/// newline.
fn extract_answer(stdout: &str) -> String {
    let mut answer = String::new();
    for line in stdout.split_inclusive('\n') {
        if !line.starts_with(THINKING_PREFIX) {
            answer.push_str(line);
        }
    }
    if let Some(without_last_newline) = answer.strip_suffix('\n') {
        answer = without_last_newline.to_string();
    }
    answer
}

/// Registers the `chat_list_sessions` tool on the shared server
/// (`add-mcp-chat-sessions-list-tool`).
#[tool_router(router = chat_list_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// List the stored chat sessions.
    #[tool(
        description = "List the stored secondbrain chat sessions: one line per session in \\\
                       the CLI's human-readable format `session_id: N messages (created: ...)`. \\\
                       Takes no parameters."
    )]
    async fn chat_list_sessions(&self) -> Result<CallToolResult, ErrorData> {
        run_list_sessions(self).await
    }
}

/// Runs `chat --list-sessions` and passes the CLI's session listing through
/// as text content.
async fn run_list_sessions(server: &SecondBrainServer) -> Result<CallToolResult, ErrorData> {
    let runner = match &server.cli {
        Ok(runner) => runner,
        Err(message) => return Ok(resolution_error(message)),
    };

    let argv = list_sessions_argv();
    match runner.run(&argv, &[]).await {
        Ok(CliOutcome::Success { stdout, .. }) => {
            // The CLI's session listing is a stable human-readable table;
            // there is no JSON mode to parse (documented CLI constraint).
            Ok(CallToolResult::success(vec![ContentBlock::text(stdout)]))
        }
        Ok(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => Ok(CallToolResult::error(vec![ContentBlock::text(
            describe_exit(code, &stdout, &stderr),
        )])),
        Err(error) => Ok(adapter_error(&error)),
    }
}

/// Builds the CLI argv: `chat --list-sessions` (no other flags).
fn list_sessions_argv() -> Vec<OsString> {
    vec![OsString::from("chat"), OsString::from("--list-sessions")]
}

/// Input of the `chat_get_history` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct ChatHistoryParams {
    /// The chat session whose history to fetch.
    pub session_id: String,
}

/// Registers the `chat_get_history` tool on the shared server
/// (`add-mcp-chat-history-tool`).
#[tool_router(router = chat_history_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Fetch a chat session's conversation history.
    #[tool(
        description = "Fetch the full conversation history of a secondbrain chat session, \\\
                       in the CLI's human-readable rendering (one message per line). Fails \\\
                       for sessions that do not exist."
    )]
    async fn chat_get_history(
        &self,
        Parameters(params): Parameters<ChatHistoryParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run_history(self, params).await
    }
}

/// Runs `chat --history --session <id>` and passes the CLI's history
/// rendering through as text content.
async fn run_history(
    server: &SecondBrainServer,
    params: ChatHistoryParams,
) -> Result<CallToolResult, ErrorData> {
    let runner = match &server.cli {
        Ok(runner) => runner,
        Err(message) => return Ok(resolution_error(message)),
    };

    let argv = history_argv(&params.session_id);
    match runner.run(&argv, &[]).await {
        Ok(CliOutcome::Success { stdout, .. }) => {
            // The CLI's history is a human-readable rendering; there is no
            // JSON mode to parse (documented CLI constraint).
            Ok(CallToolResult::success(vec![ContentBlock::text(stdout)]))
        }
        Ok(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => Ok(CallToolResult::error(vec![ContentBlock::text(
            describe_exit(code, &stdout, &stderr),
        )])),
        Err(error) => Ok(adapter_error(&error)),
    }
}

/// Builds the CLI argv: `chat --history --session <id>`.
fn history_argv(session_id: &str) -> Vec<OsString> {
    vec![
        OsString::from("chat"),
        OsString::from("--history"),
        OsString::from("--session"),
        OsString::from(session_id),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn list_sessions_argv_is_exactly_the_single_flag() {
        let strings: Vec<String> = list_sessions_argv()
            .iter()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            strings,
            ["chat", "--list-sessions"],
            "the listing tool must invoke exactly `chat --list-sessions` with no extra flags"
        );
    }

    /// Builds send params with every knob settable.
    fn send_params(
        query: &str,
        session_id: Option<&str>,
        top_k: Option<u64>,
        temperature: Option<f64>,
        model: Option<&str>,
    ) -> ChatSendParams {
        ChatSendParams {
            query: query.to_string(),
            session_id: session_id.map(str::to_string),
            top_k,
            temperature,
            model: model.map(str::to_string),
        }
    }

    #[test]
    fn history_argv_is_exactly_the_flag_pair_with_the_id() {
        let strings: Vec<String> = history_argv("existing-session-42")
            .iter()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            strings,
            ["chat", "--history", "--session", "existing-session-42"],
            "the history tool must invoke exactly `chat --history --session <id>`"
        );
    }

    #[test]
    fn send_argv_covers_every_flag_combination() {
        for with_top_k in [false, true] {
            for with_temperature in [false, true] {
                for with_model in [false, true] {
                    let argv = send_argv(
                        "session-42",
                        &send_params(
                            "the query",
                            Some("session-42"),
                            with_top_k.then_some(5),
                            with_temperature.then_some(0.2),
                            with_model.then_some("gpt-x"),
                        ),
                    );
                    let strings: Vec<String> = argv
                        .iter()
                        .map(|argument| argument.to_string_lossy().into_owned())
                        .collect();

                    assert_eq!(strings[0], "chat");
                    assert_eq!(strings[1], "--session");
                    assert_eq!(
                        strings[2], "session-42",
                        "the session id precedes the flags"
                    );

                    let mut rest = strings[3..].to_vec();
                    let query = rest.pop().expect("the query is the last element");
                    let separator = rest.pop().expect("the separator precedes the query");
                    assert_eq!(separator, "--", "the query must follow a -- separator");
                    assert_eq!(query, "the query");

                    let mut flags = rest.into_iter();
                    if with_top_k {
                        assert_eq!(flags.next().as_deref(), Some("--top-k"));
                        assert_eq!(flags.next().as_deref(), Some("5"));
                    }
                    if with_temperature {
                        assert_eq!(flags.next().as_deref(), Some("--temperature"));
                        assert_eq!(flags.next().as_deref(), Some("0.2"));
                    }
                    if with_model {
                        assert_eq!(flags.next().as_deref(), Some("--model"));
                        assert_eq!(flags.next().as_deref(), Some("gpt-x"));
                    }
                    let leftover: Vec<String> = flags.collect();
                    assert!(
                        leftover.is_empty(),
                        "no unexpected flags may remain: {leftover:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn send_argv_keeps_the_hostile_query_literal() {
        let argv = send_argv(
            "session-42",
            &send_params(
                "--session evil && rm -rf /",
                Some("session-42"),
                None,
                None,
                None,
            ),
        );
        let last = argv.last().expect("the query is the last element");
        assert_eq!(
            last, "--session evil && rm -rf /",
            "the query must stay one verbatim element"
        );
        assert_eq!(argv[argv.len() - 2], "--");
    }

    #[test]
    fn generated_session_ids_are_unique_v4s() {
        let first = generate_session_id();
        let second = generate_session_id();
        assert_ne!(first, second, "two generated ids must differ");
        for id in [first, second] {
            assert_eq!(id.len(), 36, "a UUID is 8-4-4-4-12: {id}");
            let chars: Vec<char> = id.chars().collect();
            assert_eq!(chars[8], '-', "{id}");
            assert_eq!(chars[13], '-', "{id}");
            assert_eq!(chars[18], '-', "{id}");
            assert_eq!(chars[23], '-', "{id}");
            assert_eq!(chars[14], '4', "the version nibble must be 4 (v4): {id}");
            assert!(
                matches!(chars[19], '8' | '9' | 'a' | 'b'),
                "the variant nibble must be 8/9/a/b: {id}"
            );
        }
    }

    #[test]
    fn a_leading_thinking_line_is_stripped() {
        let stdout = "▸ Thinking: 123 chars (collapsed)\nThe capital of France is Paris.\n";
        assert_eq!(extract_answer(stdout), "The capital of France is Paris.");
    }

    #[test]
    fn a_trailing_thinking_line_is_stripped() {
        let stdout = "The capital of France is Paris.\n▸ Thinking: 123 chars (collapsed)\n";
        assert_eq!(extract_answer(stdout), "The capital of France is Paris.");
    }

    #[test]
    fn multiple_thinking_lines_are_stripped() {
        let stdout = concat!(
            "▸ Thinking: 123 chars (collapsed)\n",
            "The capital of France is Paris.\n",
            "▸ Thinking: 456 chars (collapsed)\n"
        );
        assert_eq!(extract_answer(stdout), "The capital of France is Paris.");
    }

    #[test]
    fn the_answer_is_preserved_verbatim_otherwise() {
        let stdout = "▸ Thinking: 123 chars (collapsed)\nLine one.\nLine two.\n\nLine three.\n";
        assert_eq!(
            extract_answer(stdout),
            "Line one.\nLine two.\n\nLine three."
        );
    }

    #[test]
    fn a_thinking_mention_inside_a_line_is_kept() {
        // The prefix is line-anchored: an interior mention is answer text.
        let stdout = "See the ▸ Thinking: documentation.\n";
        assert_eq!(extract_answer(stdout), "See the ▸ Thinking: documentation.");
    }

    #[test]
    fn output_without_a_trailing_newline_is_kept_whole() {
        let stdout = "▸ Thinking: 1 char (collapsed)\nBare answer";
        assert_eq!(extract_answer(stdout), "Bare answer");
    }

    #[test]
    fn empty_and_thinking_only_output_extracts_to_nothing() {
        assert_eq!(extract_answer(""), "");
        assert_eq!(extract_answer("▸ Thinking: 123 chars (collapsed)\n"), "");
    }

    #[test]
    fn only_a_single_trailing_newline_is_trimmed() {
        let stdout = "▸ Thinking: 1 char (collapsed)\nAnswer.\n\n";
        // One blank line is preserved (only ONE trailing newline is trimmed).
        assert_eq!(extract_answer(stdout), "Answer.\n");
    }

    #[test]
    fn the_thinking_override_is_exact() {
        let (variable, value) = thinking_off();
        assert_eq!(variable, "SECONDBRAIN_SHOW_THINKING");
        assert_eq!(value, "0");
    }
}
