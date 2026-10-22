//! Bearer auth: `SECONDBRAIN_MCP_AUTH_TOKEN` optionally locks `/mcp` behind
//! `Authorization: Bearer`, while `/healthz` stays open for probes.

mod common;

use common::{HttpResponse, RunningServer, http_get, http_request};
use serde_json::Value;

/// The configured token for the locked mode.
const TOKEN: &str = "s3cret-token";

/// Boots the server with the token configured on an ephemeral loopback port.
fn boot_locked() -> RunningServer {
    RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_AUTH_TOKEN", TOKEN),
    ])
}

/// POSTs `tools/list` with the given `Authorization` header value (absent
/// when `None`).
fn tools_list(address: std::net::SocketAddr, authorization: Option<&str>) -> HttpResponse {
    let mut headers: Vec<(&str, &str)> = vec![
        ("Content-Type", "application/json"),
        ("Accept", "application/json, text/event-stream"),
    ];
    if let Some(value) = authorization {
        headers.push(("Authorization", value));
    }
    http_request(
        "POST",
        address,
        "/mcp",
        &headers,
        Some(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#),
    )
}

#[test]
fn open_mode_accepts_requests_without_a_header() {
    let server = RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")]);
    let response = tools_list(server.address, None);
    assert_eq!(
        response.status, 200,
        "without a token the MCP surface stays open: {response:?}"
    );
}

#[test]
fn missing_header_is_unauthorized() {
    let server = boot_locked();
    let response = tools_list(server.address, None);
    assert_eq!(response.status, 401, "{response:?}");
    assert_eq!(
        response.header("WWW-Authenticate"),
        Some("Bearer"),
        "401 must signal the bearer challenge: {response:?}"
    );
}

#[test]
fn wrong_token_is_unauthorized() {
    let server = boot_locked();
    let response = tools_list(server.address, Some("Bearer nope"));
    assert_eq!(response.status, 401, "{response:?}");
    assert_eq!(response.header("WWW-Authenticate"), Some("Bearer"));
}

#[test]
fn prefix_token_is_unauthorized() {
    let server = boot_locked();
    // A strict prefix of the configured token…
    let response = tools_list(server.address, Some("Bearer s3cret"));
    assert_eq!(response.status, 401, "{response:?}");
    // …and the presented token strictly longer than the configured one.
    let response = tools_list(server.address, Some("Bearer s3cret-token-extended"));
    assert_eq!(
        response.status, 401,
        "the longer-than-configured variant must also reject: {response:?}"
    );
}

#[test]
fn wrong_scheme_is_unauthorized() {
    let server = boot_locked();
    let response = tools_list(server.address, Some("Basic dXNlcjpwYXNz"));
    assert_eq!(response.status, 401, "{response:?}");
    assert_eq!(response.header("WWW-Authenticate"), Some("Bearer"));
}

#[test]
fn correct_token_is_accepted() {
    let server = boot_locked();
    let response = tools_list(server.address, Some("Bearer s3cret-token"));
    assert_eq!(response.status, 200, "{response:?}");
    let parsed: Value = serde_json::from_str(&response.body)
        .expect("the protected request must be answered with JSON-RPC");
    // The auth property is that the protected tools/list is answered; the
    // registry's contents are transport.rs's concern (they evolve as tools
    // land — this test once pinned an empty registry and grew stale).
    assert!(
        parsed["result"]["tools"].is_array(),
        "the protected tools/list must be answered with the registry: {parsed}"
    );
}

#[test]
fn healthz_stays_open_without_a_token() {
    let server = boot_locked();
    let health = http_get(server.address, "/healthz");
    assert_eq!(
        health.status, 200,
        "healthchecks must work without credentials: {health:?}"
    );
}
