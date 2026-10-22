//! The MCP transport at `/mcp`: JSON-RPC 2.0 over HTTP in stateless mode with
//! single-body `application/json` responses, probed with raw HTTP on an
//! ephemeral port (rmcp's `test_streamable_http_json_response.rs` pattern).
//!
//! Server metadata (`serverInfo`, `instructions`) is asserted on the
//! `initialize` response: rmcp 3.5 surfaces the handler's `get_info()` there,
//! while `tools/list` results carry only the tool list (verified against the
//! shipped rmcp 3.5.1 source) — and rmcp's own stateless test initializes
//! first as well.

mod common;

use common::{HttpResponse, RunningServer, http_get, http_request};
use serde_json::{Value, json};

/// Boots the server on an ephemeral loopback port.
fn boot() -> RunningServer {
    RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")])
}

/// POSTs a JSON-RPC request to `/mcp` with the media types a standard MCP
/// client offers (the server's content-negotiation gate requires both).
fn post_mcp(server: &RunningServer, request: Value) -> HttpResponse {
    http_request(
        "POST",
        server.address,
        "/mcp",
        &[
            ("Content-Type", "application/json"),
            ("Accept", "application/json, text/event-stream"),
        ],
        Some(&request.to_string()),
    )
}

/// A `tools/list` request for the tool registry.
fn tools_list(id: i64) -> Value {
    json!({"jsonrpc": "2.0", "id": id, "method": "tools/list", "params": {}})
}

/// A stateless `initialize` request, as rmcp's own test sends one.
fn initialize(id: i64) -> Value {
    json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "secondbrain-mcp-tests", "version": "0.0.0"}
        }
    })
}

#[test]
fn initialize_reports_server_metadata() {
    let server = boot();
    let response = post_mcp(&server, initialize(1));

    assert_eq!(
        response.status, 200,
        "initialize must succeed: {response:?}"
    );
    let content_type = response
        .header("content-type")
        .expect("the response must declare a content type");
    assert!(
        content_type.starts_with("application/json"),
        "single-body JSON responses must be application/json: {content_type}"
    );

    let body: Value = serde_json::from_str(&response.body)
        .expect("the response body must be a JSON-RPC document");
    assert_eq!(body["jsonrpc"], "2.0");
    assert_eq!(body["id"], 1);
    assert_eq!(body["result"]["serverInfo"]["name"], "secondbrain-mcp");
    assert_eq!(
        body["result"]["serverInfo"]["version"],
        env!("CARGO_PKG_VERSION")
    );
    let instructions = body["result"]["instructions"]
        .as_str()
        .expect("the server must provide instructions");
    for capability in ["ingestion", "search", "chat"] {
        assert!(
            instructions.contains(capability),
            "instructions must mention {capability}: {instructions}"
        );
    }
    // Stateless mode issues no session id even for the initialize handshake.
    assert!(
        response.header("mcp-session-id").is_none(),
        "stateless mode must not issue session ids: {response:?}"
    );
}

#[test]
fn tools_list_serves_the_registry() {
    let server = boot();
    let response = post_mcp(&server, tools_list(1));

    assert_eq!(
        response.status, 200,
        "tools/list must succeed: {response:?}"
    );
    let content_type = response
        .header("content-type")
        .expect("the response must declare a content type");
    assert!(
        content_type.starts_with("application/json"),
        "single-body JSON responses must be application/json: {content_type}"
    );

    let body: Value = serde_json::from_str(&response.body)
        .expect("the response body must be a JSON-RPC document");
    assert_eq!(body["jsonrpc"], "2.0");
    assert_eq!(body["id"], 1);
    let tools = body["result"]["tools"]
        .as_array()
        .expect("the result must carry a tools array");
    let names: Vec<&str> = tools
        .iter()
        .filter_map(|tool| tool["name"].as_str())
        .collect();
    assert!(
        names.contains(&"search"),
        "the search tool must be discoverable: {names:?}"
    );
}

#[test]
fn unknown_tool_call_is_a_json_rpc_error() {
    let server = boot();
    let response = post_mcp(
        &server,
        json!({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "definitely-not-a-tool", "arguments": {}}
        }),
    );

    // A JSON-RPC error result is still an HTTP 200 application/json reply;
    // the server must not crash.
    assert_eq!(
        response.status, 200,
        "errors are JSON-RPC results, not transport failures: {response:?}"
    );
    let body: Value = serde_json::from_str(&response.body)
        .expect("the response body must be a JSON-RPC document");
    assert_eq!(body["jsonrpc"], "2.0");
    assert_eq!(body["id"], 2);
    let error = &body["error"];
    assert!(
        error.is_object(),
        "an error result must be returned: {body}"
    );
    // rmcp's tool router maps unknown tools to invalid params (-32602).
    assert_eq!(error["code"], -32602);
    let message = error["message"]
        .as_str()
        .expect("the error must carry a message");
    assert!(
        message.contains("not found"),
        "the error must say the tool was not found: {message}"
    );

    // The server survives the error: a follow-up request must still succeed.
    let follow_up = post_mcp(&server, tools_list(3));
    assert_eq!(
        follow_up.status, 200,
        "the server must survive an unknown tool call: {follow_up:?}"
    );
}

#[test]
fn unacceptable_accept_header_is_rejected() {
    let server = boot();
    let response = http_request(
        "POST",
        server.address,
        "/mcp",
        &[
            ("Content-Type", "application/json"),
            ("Accept", "text/plain"),
        ],
        Some(&tools_list(1).to_string()),
    );

    assert_eq!(
        response.status, 406,
        "a POST offering neither application/json nor text/event-stream must be rejected: {response:?}"
    );
}

#[test]
fn get_and_delete_mcp_are_not_allowed() {
    let server = boot();
    let get = http_get(server.address, "/mcp");
    assert_eq!(
        get.status, 405,
        "GET serves server-initiated streams; stateless mode rejects it: {get:?}"
    );
    let delete = http_request("DELETE", server.address, "/mcp", &[], None);
    assert_eq!(
        delete.status, 405,
        "DELETE terminates stateful sessions; stateless mode rejects it: {delete:?}"
    );
}

#[test]
fn stateless_request_needs_no_session() {
    let server = boot();
    // No initialize request was sent first and no session id header is
    // offered: stateless mode serves the request on its own.
    let response = post_mcp(&server, tools_list(1));

    assert_eq!(
        response.status, 200,
        "a stateless-capable client may skip initialize entirely: {response:?}"
    );
    assert!(
        response.header("mcp-session-id").is_none(),
        "stateless mode must not issue session ids: {response:?}"
    );
}
