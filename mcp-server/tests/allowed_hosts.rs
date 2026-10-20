//! The `Host` header allow-list on the MCP surface (rmcp's DNS-rebinding
//! protection).
//!
//! By default rmcp admits only `localhost`, `127.0.0.1`, and `::1` and
//! refuses any other `Host` header with `403 Forbidden`. The configured
//! `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` list replaces that default, with
//! rmcp's matching rules: an entry without a port matches any port, and an
//! entry with a port must match exactly.

mod common;

use common::{HttpResponse, RunningServer, http_request};
use serde_json::Value;

const ALLOWED_HOSTS_VAR: &str = "SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS";

/// Boots the server on an ephemeral loopback port with extra configuration.
///
/// The CLI binary stays unresolvable on purpose: only `tools/list` is
/// exercised here, and an unresolvable CLI is non-fatal by contract.
fn boot(extra_env: &[(&str, &str)]) -> RunningServer {
    let mut env: Vec<(&str, &str)> = vec![("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")];
    env.extend_from_slice(extra_env);
    RunningServer::boot(&env)
}

/// POSTs a `tools/list` request with an explicit `Host` header.
fn post_with_host(server: &RunningServer, host: &str) -> HttpResponse {
    http_request(
        "POST",
        server.address,
        "/mcp",
        &[
            ("Host", host),
            ("Content-Type", "application/json"),
            ("Accept", "application/json, text/event-stream"),
        ],
        Some(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#),
    )
}

#[test]
fn a_foreign_host_header_is_rejected_by_default() {
    let server = boot(&[]);

    let response = post_with_host(&server, "opencode.internal.earthenwire.com");
    assert_eq!(response.status, 403, "{response:?}");
    assert!(
        response
            .body
            .contains("Forbidden: Host header is not allowed"),
        "the refusal must name the rule: {}",
        response.body
    );
}

#[test]
fn a_configured_host_is_admitted() {
    let server = boot(&[(ALLOWED_HOSTS_VAR, "opencode.internal.earthenwire.com")]);

    let response = post_with_host(&server, "opencode.internal.earthenwire.com");
    assert_eq!(response.status, 200, "{response:?}");
    let parsed: Value = serde_json::from_str(&response.body)
        .expect("the admitted request must be answered with JSON-RPC");
    assert!(
        parsed["result"]["tools"].is_array(),
        "the admitted tools/list must be answered with the registry: {parsed}"
    );
}

#[test]
fn an_entry_without_a_port_matches_any_port() {
    let server = boot(&[(ALLOWED_HOSTS_VAR, "opencode.internal.earthenwire.com")]);

    let response = post_with_host(&server, "opencode.internal.earthenwire.com:9");
    assert_eq!(response.status, 200, "{response:?}");
}

#[test]
fn an_entry_with_a_port_must_match_exactly() {
    let server = boot(&[(ALLOWED_HOSTS_VAR, "opencode.internal.earthenwire.com:8443")]);

    let matching = post_with_host(&server, "opencode.internal.earthenwire.com:8443");
    assert_eq!(matching.status, 200, "{matching:?}");
    let mismatching = post_with_host(&server, "opencode.internal.earthenwire.com:9999");
    assert_eq!(mismatching.status, 403, "{mismatching:?}");
}

#[test]
fn the_configured_list_replaces_the_default_localhost_set() {
    let server = boot(&[(ALLOWED_HOSTS_VAR, "opencode.internal.earthenwire.com")]);

    // The loopback address the tests actually talk over is no longer
    // admitted once the list is set: the configured list replaces rmcp's
    // default, it does not extend it.
    let response = post_with_host(&server, &format!("127.0.0.1:{}", server.address.port()));
    assert_eq!(response.status, 403, "{response:?}");
}
