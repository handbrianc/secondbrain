//! The `chat_send` MCP tool over the full HTTP surface: discovery, generated
//! and client-provided session ids, the `SECONDBRAIN_SHOW_THINKING=0` env
//! override (asserted via the stub's recorded observation), clean answer
//! extraction, and CLI failure mapping — against stub CLIs, so no Python,
//! LLM, or Qdrant is needed.

mod common;

use common::{boot_with_cli, call_tool, json_body, tool_text};
use serde_json::{Value, json};

/// A fresh observation-log path for one test: the stub records the
/// `SECONDBRAIN_SHOW_THINKING` value it saw (first line) and its argv
/// (second line).
fn observation_log(tag: &str) -> String {
    let path =
        std::env::temp_dir().join(format!("mcp-stub-chat-send-{tag}-{}", std::process::id()));
    let _ = std::fs::remove_file(&path);
    path.to_string_lossy().into_owned()
}

/// Asserts a v4 UUID shape: 8-4-4-4-12 with version nibble 4 and an
/// 8/9/a/b variant nibble.
fn assert_uuid_v4(id: &str) {
    assert_eq!(id.len(), 36, "a UUID is 8-4-4-4-12: {id}");
    let chars: Vec<char> = id.chars().collect();
    for separator in [8usize, 13, 18, 23] {
        assert_eq!(chars[separator], '-', "{id}");
    }
    assert_eq!(chars[14], '4', "the version nibble must be 4 (v4): {id}");
    assert!(
        matches!(chars[19], '8' | '9' | 'a' | 'b'),
        "the variant nibble must be 8/9/a/b: {id}"
    );
}

#[test]
fn tools_list_declares_chat_send() {
    let server = boot_with_cli("stub_chat_send.sh", &[]);
    let response = common::post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );

    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let send = tools
        .iter()
        .find(|tool| tool["name"] == "chat_send")
        .expect("the registry must contain chat_send")
        .clone();

    let schema = &send["inputSchema"];
    let properties = schema["properties"]
        .as_object()
        .expect("the input schema must declare properties");
    for field in ["query", "session_id", "top_k", "temperature", "model"] {
        assert!(
            properties.contains_key(field),
            "the input schema must declare {field}: {schema}"
        );
    }
    assert_eq!(
        schema["required"]
            .as_array()
            .expect("a required list")
            .iter()
            .filter_map(|name| name.as_str())
            .collect::<Vec<_>>(),
        ["query"],
        "only the query is required: {schema}"
    );
    assert_eq!(properties["query"]["type"], "string");
    let top_k = properties["top_k"].to_string();
    assert!(
        top_k.contains("integer"),
        "top_k must be an integer: {top_k}"
    );
    let temperature = properties["temperature"].to_string();
    assert!(
        temperature.contains("number"),
        "temperature must be a number: {temperature}"
    );
}

#[test]
fn a_call_without_session_id_generates_a_fresh_uuid_and_returns_the_clean_answer() {
    let log = observation_log("generated");
    let server = boot_with_cli("stub_chat_send.sh", &[("STUB_CHAT_SEND_ENV_LOG", &log)]);

    let response = call_tool(
        &server,
        1,
        "chat_send",
        json!({"query": "What is the capital of France?"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a successful send must be a success: {body}"
    );

    let payload: Value =
        serde_json::from_str(tool_text(&body)).expect("the result must be the send JSON");
    let session_id = payload["session_id"].as_str().expect("a session id");
    assert_uuid_v4(session_id);
    assert_eq!(
        payload["answer"], "The capital of France is Paris.",
        "the answer must be the stdout with the thinking line stripped: {payload}"
    );

    // The env contract: the stub observed exactly `0` for this call.
    let observed = std::fs::read_to_string(&log).expect("the stub must have recorded its env");
    let mut lines = observed.lines();
    assert_eq!(
        lines.next(),
        Some("0"),
        "SECONDBRAIN_SHOW_THINKING must be 0 in the subprocess env: {observed}"
    );
    let argv_line = lines.next().expect("the stub must have recorded its argv");
    assert!(
        argv_line.contains(&format!("--session {session_id}")),
        "the generated id must reach the CLI as --session <id>: {argv_line}"
    );
    assert!(
        argv_line.contains("-- What is the capital of France?"),
        "the query must follow the -- separator: {argv_line}"
    );
}

#[test]
fn every_call_gets_its_own_fresh_session_id() {
    let log = observation_log("unique");
    let server = boot_with_cli("stub_chat_send.sh", &[("STUB_CHAT_SEND_ENV_LOG", &log)]);

    let ids: Vec<String> = (1..=2)
        .map(|id| {
            let response = call_tool(&server, id, "chat_send", json!({"query": "again"}));
            assert_eq!(response.status, 200, "{response:?}");
            let payload: Value = serde_json::from_str(tool_text(&json_body(&response)))
                .expect("the result must be the send JSON");
            payload["session_id"]
                .as_str()
                .expect("a session id")
                .to_string()
        })
        .collect();
    assert_ne!(ids[0], ids[1], "each call must generate its own session id");
    for id in &ids {
        assert_uuid_v4(id);
    }
}

#[test]
fn a_client_provided_session_id_is_used_and_echoed() {
    let log = observation_log("explicit");
    let server = boot_with_cli("stub_chat_send.sh", &[("STUB_CHAT_SEND_ENV_LOG", &log)]);

    let response = call_tool(
        &server,
        1,
        "chat_send",
        json!({"query": "Follow-up question", "session_id": "existing-session-42"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let payload: Value =
        serde_json::from_str(tool_text(&body)).expect("the result must be the send JSON");
    assert_eq!(
        payload["session_id"], "existing-session-42",
        "the provided id must be echoed back: {payload}"
    );
    assert_eq!(payload["answer"], "The capital of France is Paris.");

    let observed = std::fs::read_to_string(&log).expect("the stub must have recorded its argv");
    assert!(
        observed.contains("--session existing-session-42"),
        "the CLI must receive the provided id: {observed}"
    );
    assert_eq!(
        observed.lines().next(),
        Some("0"),
        "the env override applies to provided-id calls too: {observed}"
    );
}

#[test]
fn cli_failure_maps_to_a_tool_error() {
    let server = boot_with_cli("stub_chat_send_fail.sh", &[]);

    let response = call_tool(&server, 1, "chat_send", json!({"query": "anything"}));
    assert_eq!(
        response.status, 200,
        "tool errors are JSON-RPC results, not transport failures: {response:?}"
    );
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a failed CLI run must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("exit code 1"),
        "the diagnostics must carry the exit code: {text}"
    );
    assert!(
        text.contains("the LLM endpoint is unreachable"),
        "the diagnostics must carry the captured stderr: {text}"
    );
}
