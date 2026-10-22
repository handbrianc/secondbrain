//! Shared helpers for the `mcp-server` integration tests: the compiled
//! `secondbrain-mcp` binary is spawned as the integration subject, either
//! run-to-exit (configuration refusal) or booted for HTTP probing, with a
//! controlled `SECONDBRAIN_MCP_*` environment.

#![allow(dead_code)] // helpers are shared across the integration test binaries

use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

/// Every `SECONDBRAIN_MCP_*` variable the server resolves. Runs remove these
/// from the inherited environment first, so tests are hermetic regardless of
/// the host configuration.
pub const MCP_VARS: &[&str] = &[
    "SECONDBRAIN_MCP_HTTP_BIND_ADDR",
    "SECONDBRAIN_MCP_HTTP_TLS_ENABLED",
    "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH",
    "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH",
    "SECONDBRAIN_MCP_AUTH_TOKEN",
    "SECONDBRAIN_MCP_CLI_BIN",
    "SECONDBRAIN_MCP_WORKSPACE_ROOT",
    "SECONDBRAIN_MCP_UPLOAD_DIR",
    "SECONDBRAIN_MCP_UPLOAD_MAX_BYTES",
    "SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS",
    "SECONDBRAIN_MCP_LOG_LEVEL",
];

/// How long the boot helper waits for the server's listening announcement
/// before killing it and failing.
const BOOT_TIMEOUT: Duration = Duration::from_secs(10);

/// TCP connect timeout for the HTTP probe helper.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);

/// Socket read timeout for the HTTP probe helper.
const READ_TIMEOUT: Duration = Duration::from_secs(5);

/// How long the signal helper waits for the server to exit on its own before
/// failing the test.
#[cfg(unix)]
const SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(10);

/// Absolute path of the compiled `secondbrain-mcp` binary.
pub fn binary_path() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_secondbrain-mcp"))
}

/// A completed run of the server binary, for contracts where it must exit
/// (configuration refusal).
#[derive(Debug)]
pub struct ServerRun {
    /// Whether the process exited with status 0.
    pub status: ExitStatus,
    /// Standard output, decoded as UTF-8 (lossily).
    pub stdout: String,
    /// Standard error, decoded as UTF-8 (lossily).
    pub stderr: String,
}

impl ServerRun {
    /// Spawns the binary with the inherited environment minus every
    /// `SECONDBRAIN_MCP_*` variable, plus `extra_env`, and waits for it to
    /// exit.
    pub fn run(extra_env: &[(&str, &str)]) -> Self {
        let output = command(extra_env)
            .output()
            .expect("the secondbrain-mcp binary must be spawnable");
        Self {
            status: output.status,
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        }
    }
}

/// A booted server process and the address it listens on.
///
/// Dropping it kills and reaps the process, so tests never leak a server.
#[derive(Debug)]
pub struct RunningServer {
    child: Child,
    /// The address the server announced as listening on.
    pub address: SocketAddr,
    /// Collected stderr lines, for diagnostics on signal-driven runs.
    stderr_log: Arc<Mutex<Vec<String>>>,
}

impl RunningServer {
    /// Boots the server on an ephemeral loopback port (`127.0.0.1:0`, or
    /// whatever `extra_env` configures instead), waits for its listening
    /// announcement on stdout, and exposes the resolved address.
    pub fn boot(extra_env: &[(&str, &str)]) -> Self {
        let mut child = spawn(extra_env);

        // Drain the server's stderr in the background so a chatty server
        // cannot block on a full pipe: the structured-logging events land
        // there, tests can snapshot them via `stderr_lines`, and a tail is
        // reported when the boot handshake or a shutdown wait fails.
        let stderr_log = Arc::new(Mutex::new(Vec::new()));
        if let Some(stderr) = child.stderr.take() {
            spawn_line_collector(stderr, Arc::clone(&stderr_log));
        }

        let address = wait_for_listen(&mut child, &stderr_log);
        Self {
            child,
            address,
            stderr_log,
        }
    }

    /// The server's stderr collected so far, whole lines oldest last.
    pub fn stderr_lines(&self) -> Vec<String> {
        self.stderr_log
            .lock()
            .expect("the stderr line sink must not be poisoned")
            .clone()
    }

    /// The server's process id, for sending it signals directly.
    #[cfg(unix)]
    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    /// Sends `signal` (e.g. `libc::SIGTERM`) to the running server without
    /// waiting for it.
    #[cfg(unix)]
    pub fn send_signal(&self, signal: i32) {
        let pid =
            libc::pid_t::try_from(self.child.id()).expect("a spawned process id must fit pid_t");
        // SAFETY: `kill` only sends a POSIX signal to the server's process id;
        // no memory is touched.
        let sent = unsafe { libc::kill(pid, signal) };
        assert_eq!(sent, 0, "the server process must accept the signal");
    }

    /// Waits for the server to exit on its own and collects the exit status
    /// and stderr tail.
    ///
    /// Consumes the server, bypassing the Drop kill: the process is expected
    /// to exit by itself (graceful shutdown) and is reaped here. (The later
    /// Drop kill on the already-reaped child is a harmless ignored error.) One
    /// that does not exit within `SHUTDOWN_TIMEOUT` is killed and fails the
    /// test with diagnostics.
    #[cfg(unix)]
    pub fn wait_for_exit(mut self) -> SignalRun {
        let deadline = Instant::now() + SHUTDOWN_TIMEOUT;
        loop {
            match self
                .child
                .try_wait()
                .expect("the child status must be pollable")
            {
                Some(status) => {
                    return SignalRun {
                        status,
                        stderr_tail: recent_lines(&self.stderr_log, 5),
                    };
                }
                None if Instant::now() >= deadline => {
                    let _ = self.child.kill();
                    let _ = self.child.wait();
                    panic!(
                        "the server did not exit within {SHUTDOWN_TIMEOUT:?} after the signal; \
                         stderr tail {:?}",
                        recent_lines(&self.stderr_log, 5)
                    );
                }
                None => thread::sleep(Duration::from_millis(10)),
            }
        }
    }

    /// Sends `signal` to the running server, waits for it to exit on its own,
    /// and collects the exit status and stderr tail.
    #[cfg(unix)]
    pub fn signal_and_wait(self, signal: i32) -> SignalRun {
        self.send_signal(signal);
        self.wait_for_exit()
    }
}

/// A server process that exited after being signaled (graceful-shutdown runs).
#[cfg(unix)]
#[derive(Debug)]
pub struct SignalRun {
    /// The exit status the process reported.
    pub status: ExitStatus,
    /// The last stderr lines, oldest last (diagnostics).
    pub stderr_tail: Vec<String>,
}

impl Drop for RunningServer {
    fn drop(&mut self) {
        // SIGKILL (graceful shutdown is a later proposal), then reap so no
        // zombie is left behind.
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// Builds a command for the binary with the inherited environment minus every
/// `SECONDBRAIN_MCP_*` variable, plus `extra_env`.
fn command(extra_env: &[(&str, &str)]) -> Command {
    let mut command = Command::new(binary_path());
    for &variable in MCP_VARS {
        command.env_remove(variable);
    }
    for &(variable, value) in extra_env {
        command.env(variable, value);
    }
    command
}

/// Spawns the binary with piped output for the boot handshake.
fn spawn(extra_env: &[(&str, &str)]) -> Child {
    command(extra_env)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("the secondbrain-mcp binary must be spawnable")
}

/// Reads the child's stdout until the server announces its listen address.
///
/// A reader thread feeds lines through a channel so the wait can time out and
/// kill a misbehaving child instead of hanging the test suite.
fn wait_for_listen(child: &mut Child, stderr_log: &Mutex<Vec<String>>) -> SocketAddr {
    let stdout = child
        .stdout
        .take()
        .expect("the boot helper must pipe the server's stdout");
    let (sender, lines) = mpsc::channel();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if sender.send(line).is_err() {
                return; // the waiter gave up; nothing left to report
            }
        }
    });

    let deadline = Instant::now() + BOOT_TIMEOUT;
    let mut last_line = String::new();
    loop {
        let remaining = deadline.saturating_duration_since(Instant::now());
        match lines.recv_timeout(remaining) {
            Ok(line) => {
                if let Some(address) = parse_listen(&line) {
                    return address;
                }
                last_line = line;
            }
            Err(_) => {
                let _ = child.kill();
                let status = child.wait();
                let stderr = recent_lines(stderr_log, 5).join(" | ");
                panic!(
                    "the server did not announce a listen address within {BOOT_TIMEOUT:?}; \
                     exit {status:?}, last stdout line {last_line:?}, stderr tail {stderr:?}"
                );
            }
        }
    }
}

/// Extracts the listen address from the server's announcement
/// (`secondbrain-mcp listening on <address>`): the first whitespace-delimited
/// token that parses as a socket address.
fn parse_listen(line: &str) -> Option<SocketAddr> {
    line.split_whitespace().find_map(|token| token.parse().ok())
}

/// Collects lines from a piped stream into `sink` until the stream ends.
fn spawn_line_collector<R>(stream: R, sink: Arc<Mutex<Vec<String>>>)
where
    R: Read + Send + 'static,
{
    thread::spawn(move || {
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            sink.lock()
                .expect("the line sink must not be poisoned")
                .push(line);
        }
    });
}

/// The last `count` lines collected in `sink`, oldest last.
fn recent_lines(sink: &Mutex<Vec<String>>, count: usize) -> Vec<String> {
    let lines = sink.lock().expect("the line sink must not be poisoned");
    let start = lines.len().saturating_sub(count);
    lines[start..].to_vec()
}

/// A parsed HTTP/1.1 response from the server under test.
#[derive(Debug)]
pub struct HttpResponse {
    /// Numeric status code (e.g. 200).
    pub status: u16,
    /// All headers in response order, exactly as the server sent them.
    pub headers: Vec<(String, String)>,
    /// `Content-Type` header value, if present.
    pub content_type: Option<String>,
    /// Body decoded as UTF-8.
    pub body: String,
}

impl HttpResponse {
    /// Case-insensitive lookup of the first header with this name.
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(key, _)| key.eq_ignore_ascii_case(name))
            .map(|(_, value)| value.as_str())
    }
}

/// Sends an HTTP request with optional extra headers and body, and reads the
/// full response.
///
/// The request asks the server to close the connection, so reading to EOF
/// ends the response cleanly. A body is sent with an accurate
/// `Content-Length`; without one, no `Content-Length` header is emitted.
pub fn http_request(
    method: &str,
    address: SocketAddr,
    path: &str,
    headers: &[(&str, &str)],
    body: Option<&str>,
) -> HttpResponse {
    // An explicit `Host` entry replaces the built-in address form, so tests
    // can exercise the server's Host-based protections (rmcp's DNS-rebinding
    // allow-list) with exactly one Host header on the wire.
    let host_line = match headers
        .iter()
        .find(|(name, _)| name.eq_ignore_ascii_case("host"))
    {
        Some((_, host)) => format!("Host: {host}\r\n"),
        None => format!("Host: {address}\r\n"),
    };
    let mut request = format!("{method} {path} HTTP/1.1\r\n{host_line}Connection: close\r\n");
    for (name, value) in headers {
        if name.eq_ignore_ascii_case("host") {
            continue;
        }
        request.push_str(name);
        request.push_str(": ");
        request.push_str(value);
        request.push_str("\r\n");
    }
    if let Some(body) = body {
        request.push_str("Content-Length: ");
        request.push_str(&body.len().to_string());
        request.push_str("\r\n");
    }
    request.push_str("\r\n");

    let mut stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT)
        .expect("the server must accept connections");
    stream
        .set_read_timeout(Some(READ_TIMEOUT))
        .expect("read timeouts must be configurable");
    stream
        .write_all(request.as_bytes())
        .expect("the server must accept the request bytes");
    if let Some(body) = body {
        stream
            .write_all(body.as_bytes())
            .expect("the server must accept the body bytes");
    }
    let mut raw = String::new();
    BufReader::new(stream)
        .read_to_string(&mut raw)
        .expect("the server must close the connection after the response");
    parse_response(&raw)
}

/// Sends `GET path` to the server and reads the full response.
pub fn http_get(address: SocketAddr, path: &str) -> HttpResponse {
    http_request("GET", address, path, &[], None)
}

/// A generated self-signed certificate and key as PEM files in a temporary
/// directory, for the TLS integration tests.
///
/// The directory is removed on drop; declare the server under test after
/// this helper so the server is torn down first.
pub struct TempPem {
    /// Directory holding the PEM files; removed on drop.
    directory: PathBuf,
    /// The certificate chain PEM file.
    pub cert_path: PathBuf,
    /// The private key PEM file.
    pub key_path: PathBuf,
}

impl TempPem {
    /// Generates a self-signed pair for `localhost`/`127.0.0.1` and writes
    /// the PEM files into a fresh temporary directory.
    pub fn generate() -> Self {
        static COUNTER: AtomicUsize = AtomicUsize::new(0);
        let directory = std::env::temp_dir().join(format!(
            "secondbrain-mcp-tls-{}-{}",
            std::process::id(),
            COUNTER.fetch_add(1, Ordering::Relaxed),
        ));
        std::fs::create_dir_all(&directory).expect("the temp directory must be creatable");

        let certified = rcgen::generate_simple_self_signed(vec![
            "localhost".to_string(),
            "127.0.0.1".to_string(),
        ])
        .expect("a self-signed certificate must generate");
        let cert_path = directory.join("cert.pem");
        let key_path = directory.join("key.pem");
        std::fs::write(&cert_path, certified.cert.pem()).expect("the certificate must write");
        std::fs::write(&key_path, certified.signing_key.serialize_pem())
            .expect("the key must write");

        Self {
            directory,
            cert_path,
            key_path,
        }
    }
}

impl Drop for TempPem {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.directory);
    }
}

/// Resolves a CLI fixture stub to an executable absolute path, making sure
/// the execute bit is set regardless of how the checkout was materialized.
#[cfg(unix)]
pub fn fixture_stub(name: &str) -> PathBuf {
    use std::os::unix::fs::PermissionsExt;

    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))
        .expect("the stub fixture must be chmod-able");
    path.canonicalize().expect("the stub fixture must exist")
}

/// The fixture workspace directory (a real text file, a nested directory),
/// for ingest tool tests.
pub fn fixture_workspace() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/workspace")
        .canonicalize()
        .expect("the fixture workspace must exist")
}

/// A file under `tests/fixtures/upload/` (the upload tool's fixtures).
pub fn fixture_upload(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/upload")
        .join(name)
}

/// The base64-encoded upload fixture document
/// (`sample-document.txt.b64` — the exact encoding of `sample-document.txt`,
/// byte-comparable against what lands in the upload directory).
pub fn sample_upload_base64() -> String {
    std::fs::read_to_string(fixture_upload("sample-document.txt.b64"))
        .expect("the upload fixture must exist")
        .trim()
        .to_string()
}

/// A per-test copy of the fixture workspace: uploads must write somewhere,
/// and the shared fixture must stay pristine for the other suites (tests run
/// in parallel). The copy is removed on drop; declare servers under test
/// after it so teardown order is copy-last.
pub struct WorkspaceCopy {
    /// The copy's root directory (removed on drop).
    base: PathBuf,
    /// The copied workspace, canonicalized — what boots as the workspace
    /// root.
    pub workspace: PathBuf,
}

impl WorkspaceCopy {
    /// Copies the fixture workspace (BOOM.txt sentinel, report.txt, the
    /// nested docs directory) into a fresh per-test directory.
    pub fn new(tag: &str) -> Self {
        let base = std::env::temp_dir().join(format!("mcp-upload-ws-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let workspace = base.join("workspace");
        std::fs::create_dir_all(workspace.join("docs")).expect("the workspace copy must create");
        for relative in ["BOOM.txt", "report.txt", "docs/deep.txt"] {
            std::fs::copy(fixture_workspace().join(relative), workspace.join(relative))
                .expect("the fixture file must copy");
        }
        Self {
            base,
            workspace: workspace.canonicalize().expect("the copy must exist"),
        }
    }

    /// The default upload directory inside the copy (not created yet).
    pub fn upload_dir(&self) -> PathBuf {
        self.workspace.join("uploads")
    }
}

impl Drop for WorkspaceCopy {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.base);
    }
}

/// Boots the server like [`boot_with_cli`], with
/// `SECONDBRAIN_MCP_WORKSPACE_ROOT` pointed at `workspace` (the caller's
/// per-test [`WorkspaceCopy`]) and any extra environment on top.
#[cfg(unix)]
pub fn boot_with_workspace(
    stub: &str,
    workspace: &std::path::Path,
    extra_env: &[(&str, &str)],
) -> RunningServer {
    let mut env: Vec<(&str, String)> = vec![(
        "SECONDBRAIN_MCP_WORKSPACE_ROOT",
        workspace.to_string_lossy().into_owned(),
    )];
    env.extend(
        extra_env
            .iter()
            .map(|(variable, value)| (*variable, (*value).to_string())),
    );
    let env: Vec<(&str, &str)> = env
        .iter()
        .map(|(variable, value)| (*variable, value.as_str()))
        .collect();
    boot_with_cli(stub, &env)
}

/// Boots the server with `SECONDBRAIN_MCP_HTTP_BIND_ADDR` on an ephemeral
/// loopback port, `SECONDBRAIN_MCP_CLI_BIN` pointed at a fixture stub, and
/// any extra environment on top.
#[cfg(unix)]
pub fn boot_with_cli(stub: &str, extra_env: &[(&str, &str)]) -> RunningServer {
    let path = fixture_stub(stub);
    let mut env: Vec<(&str, String)> = vec![
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0".to_string()),
        (
            "SECONDBRAIN_MCP_CLI_BIN",
            path.to_str().expect("a UTF-8 stub path").to_string(),
        ),
    ];
    env.extend(
        extra_env
            .iter()
            .map(|(variable, value)| (*variable, (*value).to_string())),
    );
    let env: Vec<(&str, &str)> = env
        .iter()
        .map(|(variable, value)| (*variable, value.as_str()))
        .collect();
    RunningServer::boot(&env)
}

/// Boots the server like [`boot_with_cli`], plus `SECONDBRAIN_MCP_WORKSPACE_ROOT`
/// pointed at the fixture workspace.
#[cfg(unix)]
pub fn boot_with_cli_workspace(stub: &str, extra_env: &[(&str, &str)]) -> RunningServer {
    let root = fixture_workspace();
    let mut extra: Vec<(&str, String)> = vec![(
        "SECONDBRAIN_MCP_WORKSPACE_ROOT",
        root.to_string_lossy().into_owned(),
    )];
    extra.extend(
        extra_env
            .iter()
            .map(|(variable, value)| (*variable, (*value).to_string())),
    );
    let extra: Vec<(&str, &str)> = extra
        .iter()
        .map(|(variable, value)| (*variable, value.as_str()))
        .collect();
    boot_with_cli(stub, &extra)
}

/// POSTs a JSON-RPC request to `/mcp` with the media types a standard MCP
/// client offers (the server's content-negotiation gate requires both).
pub fn post_mcp(server: &RunningServer, request: serde_json::Value) -> HttpResponse {
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

/// POSTs a `tools/call` request for `name` with `arguments`.
pub fn call_tool(
    server: &RunningServer,
    id: i64,
    name: &str,
    arguments: serde_json::Value,
) -> HttpResponse {
    post_mcp(
        server,
        serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments}
        }),
    )
}

/// Parses a JSON-RPC response body.
pub fn json_body(response: &HttpResponse) -> serde_json::Value {
    serde_json::from_str(&response.body).expect("the response body must be a JSON-RPC document")
}

/// The first text block of a tool result's content.
pub fn tool_text(body: &serde_json::Value) -> &str {
    body["result"]["content"][0]["text"]
        .as_str()
        .expect("the tool result must carry a text block")
}

/// Lists the registered tool names via `tools/list`.
pub fn tool_names(server: &RunningServer) -> Vec<String> {
    let response = post_mcp(
        server,
        serde_json::json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );
    assert_eq!(
        response.status, 200,
        "tools/list must succeed: {response:?}"
    );
    json_body(&response)["result"]["tools"]
        .as_array()
        .expect("the result must carry a tools array")
        .iter()
        .filter_map(|tool| tool["name"].as_str().map(str::to_string))
        .collect()
}

/// Splits status line, headers, and body out of a raw HTTP/1.1 response.
pub fn parse_response(raw: &str) -> HttpResponse {
    let (head, body) = raw
        .split_once("\r\n\r\n")
        .expect("the response must have a header/body separator");
    let mut head_lines = head.lines();
    let status_line = head_lines
        .next()
        .expect("the response must have a status line");
    let status = status_line
        .split_whitespace()
        .nth(1)
        .expect("the status line must carry a code")
        .parse()
        .expect("the status code must be numeric");
    let mut headers = Vec::new();
    for line in head_lines {
        if let Some((name, value)) = line.split_once(':') {
            headers.push((name.trim().to_string(), value.trim().to_string()));
        }
    }
    let content_type = headers
        .iter()
        .find(|(name, _)| name.eq_ignore_ascii_case("content-type"))
        .map(|(_, value)| value.clone());
    HttpResponse {
        status,
        headers,
        content_type,
        body: body.to_string(),
    }
}
