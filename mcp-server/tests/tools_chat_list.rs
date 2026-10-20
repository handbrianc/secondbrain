//! The `chat_list_sessions` MCP tool over the full HTTP surface: discovery
//! with an empty input schema, the CLI's session-table passthrough, and CLI
//! failure mapping — against stub CLIs, so no Python or Qdrant is needed.

mod common;

use common::{boot_with_cli, call_tool, json_body, tool_text};
use serde_json::json;

#[test]
fn tools_list_declares_chat_list_sessions_with_an_empty_schema() {
    let server = boot_with_cli("stub_chat_sessions.sh", &[]);
    let response = common::post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );

    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let listing = tools
        .iter()
        .find(|tool| tool["name"] == "chat_list_sessions")
        .expect("the registry must contain chat_list_sessions")
        .clone();

    let schema = &listing["inputSchema"];
    let properties = schema["properties"].as_array();
    let empty_properties = properties.is_none_or(|properties| properties.is_empty())
        || schema["properties"]
            .as_object()
            .is_none_or(|properties| properties.is_empty());
    assert!(
        empty_properties,
        "the input schema must declare no parameters: {schema}"
    );
    let required = schema["required"].as_array();
    assert!(
        required.is_none_or(|required| required.is_empty()),
        "no parameter can be required: {schema}"
    );
}

#[test]
fn calling_the_tool_returns_the_session_table() {
    let server = boot_with_cli("stub_chat_sessions.sh", &[]);

    let response = call_tool(&server, 1, "chat_list_sessions", json!({}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a successful listing must be a success: {body}"
    );

    let text = tool_text(&body);
    assert!(
        text.contains("ab12cd34: 3 messages (created: 2026-10-14T10:00:00)")
            && text.contains("ef56ab78: 1 message (created: 2026-10-15T08:30:00)"),
        "the CLI's session table must be passed through: {text}"
    );
}

#[test]
fn arguments_are_not_required() {
    let server = boot_with_cli("stub_chat_sessions.sh", &[]);

    // The tool takes no parameters: calling it with no arguments at all must
    // work just as well as with an empty object.
    let response = common::post_mcp(
        &server,
        json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "chat_list_sessions"}
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a parameterless call must be a success: {body}"
    );
}

#[test]
fn cli_failure_maps_to_a_tool_error() {
    let server = boot_with_cli("stub_chat_sessions_failure.sh", &[]);

    let response = call_tool(&server, 1, "chat_list_sessions", json!({}));
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
        text.contains("the session store is unreadable"),
        "the diagnostics must carry the captured stderr: {text}"
    );
}
