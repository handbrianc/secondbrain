//! The server binds the address configured via `SECONDBRAIN_MCP_HTTP_BIND_ADDR`.
//! (The default `0.0.0.0:8080` itself is covered by the config unit tests in
//! `src/config.rs`; binding that default here would depend on port 8080 being
//! free.)

mod common;

use std::net::{SocketAddr, TcpListener};

use common::RunningServer;

#[test]
fn configured_address_is_bound() {
    let port = free_loopback_port();
    let configured = SocketAddr::from(([127, 0, 0, 1], port));
    let address = configured.to_string();
    let server = RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", address.as_str())]);
    assert_eq!(
        server.address, configured,
        "the server must bind exactly the configured address"
    );
}

#[test]
fn ephemeral_bind_is_honored() {
    let server = RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")]);
    assert!(
        server.address.ip().is_loopback(),
        "the configured host must be honored: {server:?}"
    );
    assert_ne!(
        server.address.port(),
        8080,
        "the OS must resolve :0 to an ephemeral port, not the default"
    );
}

/// Reserves an ephemeral loopback port, then releases it for the server to
/// bind. There is a tiny window in which another process could claim it; if
/// that ever flakes, the boot failure names the bind error on stderr.
fn free_loopback_port() -> u16 {
    let probe = TcpListener::bind("127.0.0.1:0").expect("an ephemeral loopback port must exist");
    probe
        .local_addr()
        .expect("a bound probe has a local address")
        .port()
}
