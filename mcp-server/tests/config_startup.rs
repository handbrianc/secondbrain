//! The entrypoint refuses to start on an invalid `SECONDBRAIN_MCP_*` value:
//! non-zero exit with the offending variable named on stderr, before any
//! runtime behavior begins. (Valid configurations are exercised by the
//! boot-based tests: `health.rs`, `bind.rs`.)

mod common;

use common::{RunningServer, ServerRun};

#[test]
fn invalid_timeout_exits_nonzero_naming_the_variable() {
    let run = ServerRun::run(&[("SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS", "zero")]);
    assert!(
        !run.status.success(),
        "an invalid timeout must exit non-zero: {run:?}"
    );
    assert!(
        run.stderr
            .contains("SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS"),
        "stderr must name the offending variable: {run:?}"
    );
}

#[test]
fn invalid_bind_addr_exits_nonzero_naming_the_variable() {
    let run = ServerRun::run(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "localhost:8080")]);
    assert!(
        !run.status.success(),
        "an invalid bind address must exit non-zero: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_HTTP_BIND_ADDR"),
        "stderr must name the offending variable: {run:?}"
    );
}

#[test]
fn invalid_boolean_exits_nonzero_naming_the_variable() {
    let run = ServerRun::run(&[("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "maybe")]);
    assert!(
        !run.status.success(),
        "an invalid boolean must exit non-zero: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_HTTP_TLS_ENABLED"),
        "stderr must name the offending variable: {run:?}"
    );
}

#[test]
fn empty_auth_token_boots_as_disabled() {
    let server = RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_AUTH_TOKEN", ""),
    ]);
    assert!(
        server.address.ip().is_loopback(),
        "an empty auth token is accepted configuration, not a refusal"
    );
}
