//! Graceful shutdown: SIGTERM and SIGINT stop the serving loop, an in-flight
//! request completes, and the process exits with status 0.

#![cfg(unix)] // the tests send POSIX signals to the server process

mod common;

use common::{RunningServer, parse_response};
use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::time::Duration;

/// Boots the server on an ephemeral loopback port.
fn boot() -> RunningServer {
    RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")])
}

#[test]
fn sigterm_exits_zero_when_idle() {
    let server = boot();
    let run = server.signal_and_wait(libc::SIGTERM);
    assert!(
        run.status.success(),
        "SIGTERM must exit 0 after draining: {run:?}"
    );
}

#[test]
fn in_flight_request_completes_on_sigterm() {
    let server = boot();

    // Half-send a POST body, so the connection is in-flight across the
    // signal: the server has accepted it and is still receiving it. The rest
    // of the body is sent only after SIGTERM, and the response must still be
    // delivered in full before the process exits.
    let body = json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).to_string();
    let (head, rest) = body.split_at(body.len() / 2);
    let mut stream =
        TcpStream::connect(server.address).expect("the server must accept connections");
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .expect("read timeouts must be configurable");
    let request = format!(
        "POST /mcp HTTP/1.1\r\n\
         Host: {}\r\n\
         Content-Type: application/json\r\n\
         Accept: application/json, text/event-stream\r\n\
         Content-Length: {}\r\n\
         Connection: close\r\n\
         \r\n\
         {head}",
        server.address,
        body.len()
    );
    stream
        .write_all(request.as_bytes())
        .expect("the server must accept the request bytes");

    // The signal must not outrun the server's acceptance of this connection:
    // a connection still sitting in the kernel accept queue when the drain
    // begins is never accepted by the serving loop (it breaks on the signal
    // without draining the queue), and its socket dies with a reset. The
    // short delay lets the accept loop and the connection task pick the
    // half-sent request up first, so the drain genuinely races a request
    // that is being read.
    std::thread::sleep(Duration::from_millis(200));

    server.send_signal(libc::SIGTERM);
    stream
        .write_all(rest.as_bytes())
        .expect("the server must still read the in-flight body");

    let mut raw = String::new();
    stream
        .read_to_string(&mut raw)
        .expect("the in-flight request must be answered before exit");
    let response = parse_response(&raw);
    assert_eq!(
        response.status, 200,
        "the in-flight request must complete: {response:?}"
    );
    let parsed: Value = serde_json::from_str(&response.body)
        .expect("the in-flight response body must be a JSON-RPC document");
    // The drain property is that the in-flight tools/list is answered; the
    // registry's contents are transport.rs's concern (this assertion once
    // pinned an empty registry and grew stale as tools landed).
    assert!(
        parsed["result"]["tools"].is_array(),
        "the in-flight tools/list must be answered with the registry: {parsed}"
    );

    let run = server.wait_for_exit();
    assert!(
        run.status.success(),
        "SIGTERM must exit 0 after the drain: {run:?}"
    );
}

#[test]
fn sigint_exits_zero() {
    let server = boot();
    let run = server.signal_and_wait(libc::SIGINT);
    assert!(
        run.status.success(),
        "SIGINT must exit 0 like SIGTERM: {run:?}"
    );
}
