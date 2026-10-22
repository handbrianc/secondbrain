//! Structured logging: `SECONDBRAIN_MCP_LOG_LEVEL` filters the stderr event
//! stream, lifecycle and request events included.

mod common;

use std::time::Duration;

use common::{RunningServer, ServerRun, http_get, http_request};

/// Boots the server on an ephemeral loopback port with the given log level.
fn boot_with_level(level: &str) -> RunningServer {
    RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_LOG_LEVEL", level),
    ])
}

/// Waits until the server's collected stderr stops growing, so assertions see
/// the full event stream produced by the requests made so far.
fn settled_stderr(server: &RunningServer) -> Vec<String> {
    let mut previous = server.stderr_lines();
    for _ in 0..40 {
        std::thread::sleep(Duration::from_millis(50));
        let current = server.stderr_lines();
        if current.len() == previous.len() {
            return current;
        }
        previous = current;
    }
    previous
}

#[test]
fn warn_level_hides_info_and_debug_but_shows_rejections() {
    let server = boot_with_level("warn");

    // A normal request is served; its debug event and the startup info events
    // must stay below the warn filter.
    let health = http_get(server.address, "/healthz");
    assert_eq!(health.status, 200, "{health:?}");

    // A rejected request: rmcp answers a wrong content type with 415, which
    // the request middleware logs at warn.
    let rejected = http_request(
        "POST",
        server.address,
        "/mcp",
        &[
            ("Content-Type", "text/plain"),
            ("Accept", "application/json, text/event-stream"),
        ],
        Some(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#),
    );
    assert_eq!(rejected.status, 415, "{rejected:?}");

    let stderr = settled_stderr(&server).join("\n");
    for hidden in [
        "secondbrain-mcp starting",
        "listening",
        "shutdown signal handler armed",
        "request received",
    ] {
        assert!(
            !stderr.contains(hidden),
            "info/debug event {hidden:?} must be suppressed at warn level: {stderr}"
        );
    }
    assert!(
        stderr.contains("request rejected"),
        "the warn event must pass the warn filter: {stderr}"
    );
}

#[test]
fn error_events_pass_the_filter() {
    // The first server holds its bound address; a second one pointed at the
    // same address must log the bind failure as an error event and exit 1.
    let first = boot_with_level("warn");
    let second = ServerRun::run(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", &first.address.to_string()),
        ("SECONDBRAIN_MCP_LOG_LEVEL", "warn"),
    ]);

    assert!(
        !second.status.success(),
        "the second server must refuse to start: {second:?}"
    );
    assert!(
        second.stderr.contains("cannot bind"),
        "the bind failure must be logged as an error event: {second:?}"
    );
}

#[test]
fn debug_level_shows_request_events() {
    let server = boot_with_level("debug");

    let health = http_get(server.address, "/healthz");
    assert_eq!(health.status, 200, "{health:?}");

    let stderr = settled_stderr(&server).join("\n");
    assert!(
        stderr.contains("request received"),
        "the debug request event must appear at debug level: {stderr}"
    );
    assert!(
        stderr.contains("secondbrain-mcp starting"),
        "the startup info event must appear at debug level: {stderr}"
    );
    assert!(
        stderr.contains("listening"),
        "the bind-address info event must appear at debug level: {stderr}"
    );
    assert!(
        stderr.contains("shutdown signal handler armed"),
        "the shutdown-path info event must appear at debug level: {stderr}"
    );
}
