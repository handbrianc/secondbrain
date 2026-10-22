//! The `chat_get_history` MCP tool over the full HTTP surface: discovery
//! with the required `session_id`, the CLI's history rendering passthrough,
//! and the unknown-session / CLI-failure error mapping — against a stub CLI,
//! so no Python, SQLite, or Qdrant is needed.

mod common;

use common::{boot_with_cli, call_tool, json_body, tool_text};
use serde_json::json;

#[test]
fn tools_list_declares_chat_get_history_with_a_required_session_id() {
    let server = boot_with_cli("stub_chat_history.sh", &[]);
    let response = common::post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );

    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let history = tools
        .iter()
        .find(|tool| tool["name"] == "chat_get_history")
        .expect("the registry must contain chat_get_history")
        .clone();

    let schema = &history["inputSchema"];
    let properties = schema["properties"]
        .as_object()
        .expect("the input schema must declare properties");
    assert!(
        properties.contains_key("session_id"),
        "the input schema must declare session_id: {schema}"
    );
    assert_eq!(
        schema["required"]
            .as_array()
            .expect("a required list")
            .iter()
            .filter_map(|name| name.as_str())
            .collect::<Vec<_>>(),
        ["session_id"],
        "the session id is required: {schema}"
    );
    assert_eq!(properties["session_id"]["type"], "string");
}

#[test]
fn the_history_of_a_known_session_is_passed_through() {
    let server = boot_with_cli("stub_chat_history.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "chat_get_history",
        json!({"session_id": "existing-session-42"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "an existing session's history must be a success: {body}"
    );

    let text = tool_text(&body);
    assert!(
        text.contains("[user] What is secondbrain?")
            && text.contains("[assistant] Qdrant for vectors, SQLite for conversations."),
        "the CLI's history rendering must be carried: {text}"
    );
}

#[test]
fn an_unknown_session_maps_to_a_tool_error() {
    let server = boot_with_cli("stub_chat_history.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "chat_get_history",
        json!({"session_id": "unknown-session"}),
    );
    assert_eq!(
        response.status, 200,
        "tool errors are JSON-RPC results, not transport failures: {response:?}"
    );
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "an unknown session must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("exit code 1"),
        "the error must surface the CLI's non-zero exit: {text}"
    );
    assert!(
        text.contains("session not found: unknown-session"),
        "the error must report the session was not found: {text}"
    );
}

#[test]
fn a_missing_session_id_is_a_tool_error_naming_the_field() {
    let server = boot_with_cli("stub_chat_history.sh", &[]);

    // The required parameter is absent: rmcp's argument deserialization
    // rejects the call as a tool-level error result (HTTP 200, isError)
    // whose message names the missing field — the CLI subprocess never runs.
    let response = call_tool(&server, 1, "chat_get_history", json!({}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "missing required arguments must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("session_id"),
        "the error must name the missing field: {text}"
    );
}
