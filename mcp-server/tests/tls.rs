//! Optional TLS: when enabled the same router is served over HTTPS and the
//! port speaks TLS only; when disabled the certificate/key variables are
//! ignored entirely.

mod common;

use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

use common::{RunningServer, ServerRun, TempPem, http_get};
use serde_json::{Value, json};

/// Boots a TLS-enabled server on an ephemeral loopback port with `pem`.
fn boot_tls(pem: &TempPem) -> RunningServer {
    RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "true"),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
            pem.cert_path.to_str().expect("a UTF-8 path"),
        ),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH",
            pem.key_path.to_str().expect("a UTF-8 path"),
        ),
    ])
}

/// An HTTPS client that accepts the test suite's self-signed certificate.
fn https_client() -> reqwest::Client {
    reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .expect("the HTTPS client must build")
}

#[tokio::test]
async fn tls_enabled_serves_healthz_over_https() {
    let pem = TempPem::generate();
    let server = boot_tls(&pem);
    let client = https_client();

    let response = client
        .get(format!("https://{}/healthz", server.address))
        .send()
        .await
        .expect("the HTTPS health check must succeed");
    assert_eq!(response.status(), 200, "{response:?}");
    let body: Value = response.json().await.expect("the health body is JSON");
    assert_eq!(body, json!({"status": "ok"}));
}

#[tokio::test]
async fn tls_enabled_serves_mcp_over_https() {
    let pem = TempPem::generate();
    let server = boot_tls(&pem);
    let client = https_client();

    let response = client
        .post(format!("https://{}/mcp", server.address))
        .header("Content-Type", "application/json")
        .header("Accept", "application/json, text/event-stream")
        .body(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}"#)
        .send()
        .await
        .expect("the HTTPS MCP request must succeed");
    assert_eq!(response.status(), 200, "{response:?}");
    let body: Value = response.json().await.expect("a JSON-RPC document");
    // The TLS property is that the HTTPS tools/list is answered; the
    // registry's contents are transport.rs's concern (this assertion once
    // pinned an empty registry and grew stale as tools landed).
    assert!(
        body["result"]["tools"].is_array(),
        "the protected tools/list must be answered with the registry: {body}"
    );
}

#[test]
fn plaintext_request_to_the_tls_port_fails() {
    let pem = TempPem::generate();
    let server = boot_tls(&pem);

    // A plain HTTP exchange against a TLS listener cannot complete: the
    // server sees a TLS record header where it expects one, fails the
    // handshake, and closes the connection.
    let mut stream =
        TcpStream::connect(server.address).expect("the server must accept connections");
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .expect("read timeouts must be configurable");
    stream
        .write_all(b"GET /healthz HTTP/1.1\r\nHost: probe\r\nConnection: close\r\n\r\n")
        .expect("the server must accept the request bytes");

    let mut raw = String::new();
    match stream.read_to_string(&mut raw) {
        // The failed handshake resets or closes the connection: no exchange.
        Err(_) => {}
        Ok(_) => assert!(
            !raw.contains("HTTP/1.1 200"),
            "a plaintext exchange must not complete over TLS: {raw:?}"
        ),
    }
}

#[test]
fn enabled_without_paths_refuses_startup() {
    let run = ServerRun::run(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "true"),
    ]);

    assert!(
        !run.status.success(),
        "TLS without material must refuse to start: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH"),
        "the refusal must name the missing cert variable: {run:?}"
    );
    assert!(
        !run.stdout.contains("listening on"),
        "the refusal must happen before binding: {run:?}"
    );
}

#[test]
fn enabled_with_cert_but_no_key_names_the_key_variable() {
    let pem = TempPem::generate();
    let run = ServerRun::run(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "true"),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
            pem.cert_path.to_str().expect("a UTF-8 path"),
        ),
    ]);

    assert!(
        !run.status.success(),
        "TLS without a key must refuse to start: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH"),
        "the refusal must name the missing key variable: {run:?}"
    );
    assert!(
        !run.stdout.contains("listening on"),
        "the refusal must happen before binding: {run:?}"
    );
}

#[test]
fn enabled_with_garbage_cert_refuses_startup() {
    let pem = TempPem::generate();
    std::fs::write(&pem.cert_path, "definitely not a PEM certificate")
        .expect("the garbage certificate must write");

    let run = ServerRun::run(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "true"),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
            pem.cert_path.to_str().expect("a UTF-8 path"),
        ),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH",
            pem.key_path.to_str().expect("a UTF-8 path"),
        ),
    ]);

    assert!(
        !run.status.success(),
        "TLS with an unparseable certificate must refuse to start: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH"),
        "the refusal must name the cert variable: {run:?}"
    );
    assert!(
        !run.stdout.contains("listening on"),
        "the refusal must happen before binding: {run:?}"
    );
}

#[test]
fn disabled_starts_plaintext_and_ignores_garbage_paths() {
    // With TLS disabled the certificate/key variables are ignored entirely:
    // even nonexistent paths must not block a normal plaintext start.
    let pem = TempPem::generate();
    let bogus_cert = pem.cert_path.with_file_name("nonexistent-cert.pem");
    let bogus_key = pem.key_path.with_file_name("nonexistent-key.pem");
    let server = RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "false"),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
            bogus_cert.to_str().expect("a UTF-8 path"),
        ),
        (
            "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH",
            bogus_key.to_str().expect("a UTF-8 path"),
        ),
    ]);

    let health = http_get(server.address, "/healthz");
    assert_eq!(
        health.status, 200,
        "the server must serve plaintext as before: {health:?}"
    );
}
