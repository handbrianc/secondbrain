//! `secondbrain-mcp` entrypoint.
//!
//! Resolves and validates the `SECONDBRAIN_MCP_*` configuration, initializes
//! structured logging on stderr (`add-mcp-structured-logging`), binds
//! `SECONDBRAIN_MCP_HTTP_BIND_ADDR`, and serves plaintext HTTP until asked to
//! terminate: SIGINT or SIGTERM stops the accept loop, in-flight requests
//! drain, and the process exits 0 (`add-mcp-graceful-shutdown`). `/healthz`
//! reports health, `/mcp` is the MCP Streamable HTTP transport in stateless
//! mode with single-body JSON responses, and the tools drive the secondbrain
//! CLI as a subprocess (`add-mcp-cli-*`). TLS is the optional capability of
//! `add-mcp-tls-support`.

mod auth;
mod cli;
mod config;
mod server;
mod tls;
mod tools;

use axum::{Json, Router, extract::Request, middleware::Next, response::Response, routing::get};
use rmcp::transport::streamable_http_server::{
    StreamableHttpServerConfig, StreamableHttpService, session::local::LocalSessionManager,
};
use serde::Serialize;
use std::sync::Arc;
use tracing_subscriber::filter::LevelFilter;

#[tokio::main]
async fn main() {
    let config = match config::Config::from_env() {
        Ok(config) => config,
        Err(error) => {
            // Config refusal happens before logging is usable: the level
            // filter comes from the config itself, so the scaffold's
            // fail-fast stderr contract stays a plain write.
            eprintln!("secondbrain-mcp: invalid configuration: {error}");
            std::process::exit(1);
        }
    };

    // The upload directory must resolve inside the workspace root before
    // anything binds — the same confinement rule the ingest tool enforces
    // per call, applied to the directory uploads are written into (a
    // directory outside the root would let `upload_document` defeat the
    // ingest path confinement).
    if let Err(error) =
        tools::upload::validate_upload_dir(&config.workspace_root, &config.upload_dir)
    {
        eprintln!("secondbrain-mcp: invalid configuration: {error}");
        std::process::exit(1);
    }

    init_tracing(config.log_level);
    tracing::info!("secondbrain-mcp starting");

    // The signal handlers arm before anything binds: a SIGINT/SIGTERM that
    // arrives at any point of the startup window routes into the graceful
    // drain instead of the default terminate disposition.
    let shutdown = arm_shutdown_signals();

    // The CLI binary resolves once at startup, before any tool invocation can
    // run (the adapter contract). A failure is not fatal: the server still
    // boots so `/healthz` and `tools/list` work, and every tool call reports
    // the resolution failure — naming the variable — until the configuration
    // is fixed.
    let cli = match cli::CliRunner::new(&config.cli_bin, config.subprocess_timeout) {
        Ok(runner) => Ok(runner),
        Err(error) => {
            tracing::error!(error = %error, "the CLI binary could not be resolved");
            Err(error.to_string())
        }
    };

    // Stateless protocol mode (`legacy_session_mode == false`): each request
    // is served on its own, with no initialize handshake and no session id;
    // `json_response` makes every reply a single-body application/json
    // document. The `Host` header allow-list (rmcp's DNS-rebinding
    // protection) defaults to rmcp's localhost set and is replaced by the
    // configured list when `SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS` is set.
    //
    // The request-body limit is derived from the upload cap (base64
    // expansion + JSON framing slack): an `upload_document` call at
    // `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` must reach the tool handler, so the
    // transport's own default POST body limit (4 MiB) is raised to the
    // derived budget. The same budget replaces axum's framework default
    // body limit on the `/mcp` router, so every body-consuming layer in
    // front of the transport agrees on one number.
    let workspace_root = config.workspace_root.clone();
    let upload_dir = config.upload_dir.clone();
    let upload_max_bytes = config.upload_max_bytes;
    let body_budget = request_body_budget(upload_max_bytes);
    // One job registry for the whole process lifetime
    // (`add-mcp-async-ingestion`): the stateless mode below builds a fresh
    // server per request, so the registry must be constructed here and
    // shared through a clone into every instance — a job id means the same
    // job to every request, and a detached job outlives the request that
    // started it.
    let jobs = Arc::new(tools::jobs::JobRegistry::new());
    let mut http_config = StreamableHttpServerConfig::default()
        .with_legacy_session_mode(false)
        .with_json_response(true)
        .with_max_request_body_bytes(body_budget);
    if let Some(allowed_hosts) = &config.http_allowed_hosts {
        http_config = http_config.with_allowed_hosts(allowed_hosts.iter().cloned());
    }
    let mcp: StreamableHttpService<server::SecondBrainServer, LocalSessionManager> =
        StreamableHttpService::new(
            move || {
                Ok(server::SecondBrainServer::new(
                    cli.clone(),
                    workspace_root.clone(),
                    upload_dir.clone(),
                    upload_max_bytes,
                    Arc::clone(&jobs),
                ))
            },
            Default::default(),
            http_config,
        );

    // Bearer auth on the MCP surface, driven by the configured token: with
    // the variable unset the layer passes everything through (open mode).
    let auth_state = auth::AuthState::new(config.auth_token);

    let mcp_app = Router::new()
        .nest_service("/mcp", mcp)
        .layer(axum::extract::DefaultBodyLimit::max(body_budget))
        .layer(axum::middleware::from_fn_with_state(
            auth_state,
            auth::bearer_auth,
        ));

    let app = Router::new()
        .route("/healthz", get(health))
        .merge(mcp_app)
        .layer(axum::middleware::from_fn(log_request));

    // TLS material loads before any bind: an invalid TLS configuration
    // refuses startup without ever listening.
    let tls_config = if config.tls.enabled {
        Some(match tls::load(&config.tls).await {
            Ok(tls_config) => tls_config,
            Err(error) => {
                // Fail-fast contract: the refusal names the offending
                // `SECONDBRAIN_MCP_HTTP_TLS_*` variable on stderr.
                eprintln!("secondbrain-mcp: invalid TLS configuration: {error}");
                std::process::exit(1);
            }
        })
    } else {
        None
    };

    let listener = match tokio::net::TcpListener::bind(config.bind_addr).await {
        Ok(listener) => listener,
        Err(error) => {
            tracing::error!(
                bind_addr = %config.bind_addr,
                error = %error,
                "cannot bind the listen address"
            );
            std::process::exit(1);
        }
    };
    let bound = listener
        .local_addr()
        .expect("a bound listener has a local address");
    // Machine-readable listen announcement on stdout: the integration tests'
    // ephemeral-port boot helper parses this line. Structured events go to
    // stderr.
    println!("secondbrain-mcp listening on {bound}");
    tracing::info!(address = %bound, "listening");

    match tls_config {
        // TLS: axum-server terminates TLS in front of the same router, with
        // the same shutdown token — the signal future drives
        // `Handle::graceful_shutdown`, so in-flight requests drain exactly
        // like on the plaintext path.
        Some(tls_config) => {
            let std_listener = listener
                .into_std()
                .expect("a tokio listener converts to a std listener");
            let server = match axum_server::tls_rustls::from_tcp_rustls(std_listener, tls_config) {
                Ok(server) => server,
                Err(error) => {
                    tracing::error!(error = %error, "cannot start the TLS server");
                    std::process::exit(1);
                }
            };
            let shutdown_handle = axum_server::Handle::new();
            let signal_handle = shutdown_handle.clone();
            tokio::spawn(async move {
                shutdown.wait().await;
                signal_handle.graceful_shutdown(None);
            });
            let server = server.handle(shutdown_handle);
            if let Err(error) = server.serve(app.into_make_service()).await {
                tracing::error!(error = %error, "serving failed");
                std::process::exit(1);
            }
        }
        None => {
            if let Err(error) = axum::serve(listener, app)
                .with_graceful_shutdown(shutdown.wait())
                .await
            {
                tracing::error!(error = %error, "serving failed");
                std::process::exit(1);
            }
        }
    }
}

/// Initializes structured logging on stderr, filtered to `level`.
///
/// Events land on stderr (stdout stays reserved for the machine-readable
/// listen announcement), without ANSI colors so the stream stays easy to
/// scan for tests and log shippers.
fn init_tracing(level: config::LogLevel) {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .with_ansi(false)
        .with_max_level(level_filter(level))
        .init();
}

/// The `/mcp` request-body budget derived from the upload cap: base64
/// inflates a file to ~4/3 of its size on the wire and the JSON-RPC framing
/// adds a little more on top, so a call at
/// `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` (decoded) must still fit the
/// transport's body limit. One MiB of slack covers the framing at any
/// realistic size.
fn request_body_budget(upload_max_bytes: u64) -> usize {
    /// JSON-RPC framing slack on top of the base64-expanded payload.
    const FRAMING_SLACK_BYTES: u64 = 1024 * 1024;

    let budget = upload_max_bytes
        .saturating_mul(4)
        .div_ceil(3)
        .saturating_add(FRAMING_SLACK_BYTES);
    usize::try_from(budget).unwrap_or(usize::MAX)
}

/// Maps a configured log level onto the subscriber's level filter.
fn level_filter(level: config::LogLevel) -> LevelFilter {
    match level {
        config::LogLevel::Trace => LevelFilter::TRACE,
        config::LogLevel::Debug => LevelFilter::DEBUG,
        config::LogLevel::Info => LevelFilter::INFO,
        config::LogLevel::Warn => LevelFilter::WARN,
        config::LogLevel::Error => LevelFilter::ERROR,
    }
}

/// Logs each request: receipt at `debug`, client-error rejections at `warn`,
/// server-side failures at `error`.
async fn log_request(request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let path = request.uri().path().to_owned();
    tracing::debug!(method = %method, path = %path, "request received");
    let response = next.run(request).await;
    let status = response.status();
    if status.is_server_error() {
        tracing::error!(method = %method, path = %path, status = %status, "request failed");
    } else if status.is_client_error() {
        tracing::warn!(method = %method, path = %path, status = %status, "request rejected");
    }
    response
}

/// The SIGINT/SIGTERM handlers, armed as early as possible in the process
/// lifetime.
///
/// Arming happens in [`arm_shutdown_signals`], **before** the listener
/// binds: from that moment a signal resolves the shutdown future instead of
/// hitting the default terminate disposition, so the graceful-shutdown
/// contract ("SIGTERM while idle exits 0") covers the whole serving
/// lifetime — the startup window included.
#[derive(Debug)]
struct ArmedShutdownSignals {
    /// Interactive stop (Ctrl-C).
    #[cfg(unix)]
    interrupt: tokio::signal::unix::Signal,
    /// Container-style stop.
    #[cfg(unix)]
    terminate: tokio::signal::unix::Signal,
}

/// Installs the SIGINT/SIGTERM handlers eagerly, rather than when the
/// serving loop first polls the shutdown future.
fn arm_shutdown_signals() -> ArmedShutdownSignals {
    #[cfg(unix)]
    {
        ArmedShutdownSignals {
            interrupt: tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())
                .expect("installing the SIGINT handler must succeed"),
            terminate: tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("installing the SIGTERM handler must succeed"),
        }
    }
    #[cfg(not(unix))]
    {
        ArmedShutdownSignals {}
    }
}

impl ArmedShutdownSignals {
    /// Resolves when the process is asked to terminate: SIGINT (interactive
    /// stop) or SIGTERM (container-style stop). Completing this future
    /// starts the graceful shutdown; the serving loop then drains in-flight
    /// requests.
    async fn wait(mut self) {
        tracing::info!("shutdown signal handler armed");
        #[cfg(unix)]
        let interrupt = self.interrupt.recv();
        #[cfg(not(unix))]
        let interrupt = tokio::signal::ctrl_c();

        #[cfg(unix)]
        let terminate = self.terminate.recv();
        #[cfg(not(unix))]
        let terminate = std::future::pending::<()>();

        tokio::select! {
            _ = interrupt => tracing::info!(signal = "SIGINT", "shutdown signal received; draining"),
            _ = terminate => tracing::info!(signal = "SIGTERM", "shutdown signal received; draining"),
        }
    }
}

/// Body of the health endpoint.
#[derive(Serialize)]
struct Health {
    status: &'static str,
}

async fn health() -> Json<Health> {
    Json(Health { status: "ok" })
}

#[cfg(test)]
mod tests {
    use super::request_body_budget;

    /// One MiB, the JSON framing slack the budget adds.
    const SLACK: usize = 1024 * 1024;

    #[test]
    fn the_budget_covers_the_base64_expansion_plus_slack() {
        // 10 MB (the default cap): 4/3 of it, rounded up, plus one MiB of
        // framing slack.
        assert_eq!(request_body_budget(10_485_760), 13_981_014 + SLACK);
        // A tiny configured cap: the slack keeps the budget above the
        // expansion at every size.
        assert_eq!(request_body_budget(1024), 1366 + SLACK);
        // The boundary invariant: at least ceil(4/3 × limit) + slack.
        for limit in [1u64, 2, 3, 10, 1000, 1_048_576, 104_857_600] {
            let budget = request_body_budget(limit);
            assert!(
                budget >= (limit * 4).div_ceil(3) as usize + SLACK,
                "the budget must cover base64 expansion plus slack at {limit}"
            );
        }
    }

    #[test]
    fn an_absurd_cap_saturates_instead_of_overflowing() {
        // No overflow panic: the arithmetic saturates and stays astronomi-
        // cally large (≈ 2^63), far above any plausible body. (Where usize
        // is narrower than u64, the conversion lands on usize::MAX — the
        // transport's "no limit" value.)
        assert!(request_body_budget(u64::MAX) >= u64::MAX as usize / 3);
    }
}
