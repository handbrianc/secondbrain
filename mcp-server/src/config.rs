//! Server configuration resolved from the `SECONDBRAIN_MCP_*` environment
//! table.
//!
//! Every server setting is parsed and validated here, in one place, with
//! documented defaults. Individual values are wired into behavior by later
//! proposals (TLS paths are validated by the TLS proposal, the CLI binary by
//! the adapter proposals, the upload directory's startup confinement check by
//! the upload tool, and so on); this module only guarantees that the
//! configuration is well-formed. Any invalid value produces a
//! [`ConfigError`] naming the offending `SECONDBRAIN_MCP_*` variable — the
//! fail-fast contract the entrypoint builds on.
//!
//! An empty value is treated as unset, so the default applies; most notably
//! an empty `SECONDBRAIN_MCP_AUTH_TOKEN` leaves auth disabled.

use std::env;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::time::Duration;

use serde::Deserialize;
use serde::de::value::{Error as DeserializerError, StrDeserializer};
use thiserror::Error;

// Variable names live next to their parsing so an error is always attributed
// to the exact variable that failed.
const BIND_ADDR_VAR: &str = "SECONDBRAIN_MCP_HTTP_BIND_ADDR";
const TLS_ENABLED_VAR: &str = "SECONDBRAIN_MCP_HTTP_TLS_ENABLED";
const TLS_CERT_PATH_VAR: &str = "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH";
const TLS_KEY_PATH_VAR: &str = "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH";
const HTTP_ALLOWED_HOSTS_VAR: &str = "SECONDBRAIN_MCP_HTTP_ALLOWED_HOSTS";
const AUTH_TOKEN_VAR: &str = "SECONDBRAIN_MCP_AUTH_TOKEN";
const CLI_BIN_VAR: &str = "SECONDBRAIN_MCP_CLI_BIN";
const WORKSPACE_ROOT_VAR: &str = "SECONDBRAIN_MCP_WORKSPACE_ROOT";
// The upload tool's storage location and decoded-size cap. The directory's
// name is also `pub(crate)`: the startup confinement check lives in
// `tools/upload.rs` (it mirrors the ingest tool's per-call confinement) and
// must name the same variable in its refusal.
pub(crate) const UPLOAD_DIR_VAR: &str = "SECONDBRAIN_MCP_UPLOAD_DIR";
const UPLOAD_MAX_BYTES_VAR: &str = "SECONDBRAIN_MCP_UPLOAD_MAX_BYTES";
const SUBPROCESS_TIMEOUT_VAR: &str = "SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS";
const LOG_LEVEL_VAR: &str = "SECONDBRAIN_MCP_LOG_LEVEL";

/// Listen address when `SECONDBRAIN_MCP_HTTP_BIND_ADDR` is unset.
const DEFAULT_BIND_ADDR: SocketAddr = SocketAddr::new(IpAddr::V4(Ipv4Addr::UNSPECIFIED), 8080);

/// CLI binary when `SECONDBRAIN_MCP_CLI_BIN` is unset.
const DEFAULT_CLI_BIN: &str = "secondbrain";

/// Ingest path allow-list root when `SECONDBRAIN_MCP_WORKSPACE_ROOT` is
/// unset.
const DEFAULT_WORKSPACE_ROOT: &str = ".";

/// Upload storage directory, inside the workspace root, when
/// `SECONDBRAIN_MCP_UPLOAD_DIR` is unset.
const DEFAULT_UPLOAD_DIR: &str = "uploads";

/// Decoded upload size cap when `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` is unset
/// (10 MB — a conservative floor below the CLI's 100 MiB per-file processing
/// cap; the CLI's own gate still applies at ingest time).
const DEFAULT_UPLOAD_MAX_BYTES: u64 = 10 * 1024 * 1024;

/// Subprocess timeout when `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` is
/// unset.
const DEFAULT_SUBPROCESS_TIMEOUT_SECONDS: u64 = 900;

/// An invalid `SECONDBRAIN_MCP_*` value.
///
/// The message names the offending variable so the entrypoint can point at
/// exactly what to fix.
#[derive(Debug, Error)]
#[error("{variable}: {reason}")]
pub struct ConfigError {
    /// The `SECONDBRAIN_MCP_*` variable that failed.
    pub(crate) variable: &'static str,
    /// Why the value was rejected.
    reason: String,
}

impl ConfigError {
    pub(crate) fn invalid(variable: &'static str, reason: impl Into<String>) -> Self {
        Self {
            variable,
            reason: reason.into(),
        }
    }
}

/// The resolved server configuration.
///
/// Every field is consumed by the entrypoint now: the transport binds
/// `bind_addr`, bearer auth consumes `auth_token`, the CLI adapter consumes
/// `cli_bin`, `workspace_root`, and `subprocess_timeout`, structured logging
/// consumes `log_level`, the upload tool consumes `upload_dir` and
/// `upload_max_bytes` (and the `/mcp` request-body budget is derived from
/// `upload_max_bytes`), and the TLS block drives the TLS capability.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    /// Address the server listens on.
    pub bind_addr: SocketAddr,
    /// TLS serving settings.
    pub tls: TlsConfig,
    /// Explicit `Host` allow-list on the MCP surface; `None` keeps the
    /// transport's built-in default (`localhost`, `127.0.0.1`, `::1`).
    pub http_allowed_hosts: Option<Vec<String>>,
    /// Static bearer token; `None` leaves auth disabled.
    pub auth_token: Option<String>,
    /// CLI binary the adapter spawns.
    pub cli_bin: String,
    /// Root of the ingest path allow-list.
    pub workspace_root: PathBuf,
    /// Directory uploads are stored in, anchored at the workspace root
    /// (relative values join the root, like relative ingest paths).
    pub upload_dir: PathBuf,
    /// Decoded-size cap for submitted upload content.
    pub upload_max_bytes: u64,
    /// Per-call CLI subprocess timeout.
    pub subprocess_timeout: Duration,
    /// Log level filter.
    pub log_level: LogLevel,
}

/// TLS serving settings from `SECONDBRAIN_MCP_HTTP_TLS_*`.
///
/// The paths are parsed here but validated (existence, loadability) by the
/// TLS proposal.
#[derive(Debug, Clone, PartialEq, Eq)]
#[allow(dead_code)] // field reads arrive with the TLS proposal
pub struct TlsConfig {
    /// Serve HTTPS instead of HTTP.
    pub enabled: bool,
    /// PEM certificate chain.
    pub cert_path: Option<PathBuf>,
    /// PEM private key.
    pub key_path: Option<PathBuf>,
}

/// Log level filter from `SECONDBRAIN_MCP_LOG_LEVEL`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogLevel {
    Trace,
    Debug,
    Info,
    Warn,
    Error,
}

impl LogLevel {
    /// Parses a `SECONDBRAIN_MCP_LOG_LEVEL` value, case-insensitively.
    ///
    /// Serde's plain-value deserialization does the variant matching, so the
    /// accepted set lives only on the enum.
    fn parse(raw: &str) -> Result<Self, String> {
        let normalized = raw.to_ascii_lowercase();
        Self::deserialize(StrDeserializer::<DeserializerError>::new(&normalized))
            .map_err(|_| "not a known log level".to_string())
    }
}

impl Config {
    /// Resolves the configuration from the process environment.
    ///
    /// This is the entrypoint's validation step: it either yields a complete
    /// configuration or a [`ConfigError`] naming the offending variable.
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_lookup(|variable| env::var(variable).ok())
    }

    /// Resolves the configuration from an arbitrary variable lookup, so tests
    /// can drive parsing without touching process-global environment state.
    fn from_lookup<F>(lookup: F) -> Result<Self, ConfigError>
    where
        F: Fn(&str) -> Option<String>,
    {
        let get = |variable: &'static str| lookup(variable).filter(|value| !value.is_empty());

        let bind_addr = parse_optional(
            BIND_ADDR_VAR,
            get(BIND_ADDR_VAR),
            DEFAULT_BIND_ADDR,
            "a listen address such as `0.0.0.0:8080`",
            |raw: &str| raw.parse::<SocketAddr>(),
        )?;

        let tls_enabled = parse_optional(
            TLS_ENABLED_VAR,
            get(TLS_ENABLED_VAR),
            false,
            "`true` or `false`",
            |raw: &str| raw.to_ascii_lowercase().parse::<bool>(),
        )?;
        let tls = TlsConfig {
            enabled: tls_enabled,
            cert_path: get(TLS_CERT_PATH_VAR).map(PathBuf::from),
            key_path: get(TLS_KEY_PATH_VAR).map(PathBuf::from),
        };

        let http_allowed_hosts =
            parse_allowed_hosts(HTTP_ALLOWED_HOSTS_VAR, get(HTTP_ALLOWED_HOSTS_VAR))?;

        let cli_bin = get(CLI_BIN_VAR).unwrap_or_else(|| DEFAULT_CLI_BIN.to_string());
        let workspace_root = get(WORKSPACE_ROOT_VAR)
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(DEFAULT_WORKSPACE_ROOT));

        // The upload directory is anchored at the workspace root: a relative
        // value joins the root, like a relative ingest path (the directory
        // must live inside the workspace — the confinement check that
        // enforces this is the upload tool's startup validation). The
        // default is `uploads` inside the root.
        let upload_dir = get(UPLOAD_DIR_VAR)
            .map(|raw| match PathBuf::from(&raw) {
                configured if configured.is_absolute() => configured,
                configured => workspace_root.join(configured),
            })
            .unwrap_or_else(|| workspace_root.join(DEFAULT_UPLOAD_DIR));

        let upload_max_bytes = {
            let bytes = parse_optional(
                UPLOAD_MAX_BYTES_VAR,
                get(UPLOAD_MAX_BYTES_VAR),
                DEFAULT_UPLOAD_MAX_BYTES,
                "a positive whole number of bytes",
                |raw: &str| raw.parse::<u64>(),
            )?;
            // A zero cap could never admit a document, not even an empty one.
            if bytes == 0 {
                return Err(ConfigError::invalid(
                    UPLOAD_MAX_BYTES_VAR,
                    "must be greater than 0",
                ));
            }
            bytes
        };

        let subprocess_timeout = {
            let seconds = parse_optional(
                SUBPROCESS_TIMEOUT_VAR,
                get(SUBPROCESS_TIMEOUT_VAR),
                DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
                "a positive whole number of seconds",
                |raw: &str| raw.parse::<u64>(),
            )?;
            // A zero timeout could never bound a subprocess call.
            if seconds == 0 {
                return Err(ConfigError::invalid(
                    SUBPROCESS_TIMEOUT_VAR,
                    "must be greater than 0",
                ));
            }
            Duration::from_secs(seconds)
        };

        let log_level = parse_optional(
            LOG_LEVEL_VAR,
            get(LOG_LEVEL_VAR),
            LogLevel::Info,
            "one of `trace`, `debug`, `info`, `warn`, `error`",
            LogLevel::parse,
        )?;

        Ok(Self {
            bind_addr,
            tls,
            http_allowed_hosts,
            auth_token: get(AUTH_TOKEN_VAR),
            cli_bin,
            workspace_root,
            upload_dir,
            upload_max_bytes,
            subprocess_timeout,
            log_level,
        })
    }
}

/// Parses an optional raw value into `T`, falling back to `default` when the
/// variable is unset.
///
/// `expected` describes a valid value in operator-facing terms; the underlying
/// parse error is surfaced after it verbatim.
fn parse_optional<T, E>(
    variable: &'static str,
    raw: Option<String>,
    default: T,
    expected: &str,
    parse: impl Fn(&str) -> Result<T, E>,
) -> Result<T, ConfigError>
where
    E: std::fmt::Display,
{
    match raw {
        None => Ok(default),
        Some(raw) => parse(&raw).map_err(|error| {
            ConfigError::invalid(
                variable,
                format!("expected {expected}, got `{raw}`: {error}"),
            )
        }),
    }
}

/// Parses an optional comma-separated `Host` allow-list for the MCP surface.
///
/// Entries are trimmed and entries that trim to nothing are skipped; a value
/// that yields no entry at all is rejected, naming the variable. `None`
/// (unset or empty) keeps the transport's built-in default allow-list —
/// disabling the protection entirely stays a code-level decision.
fn parse_allowed_hosts(
    variable: &'static str,
    raw: Option<String>,
) -> Result<Option<Vec<String>>, ConfigError> {
    let Some(raw) = raw else {
        return Ok(None);
    };
    let entries: Vec<String> = raw
        .split(',')
        .map(|entry| entry.trim().to_string())
        .filter(|entry| !entry.is_empty())
        .collect();
    if entries.is_empty() {
        return Err(ConfigError::invalid(
            variable,
            format!(
                "expected comma-separated hosts such as `example.com` or `example.com:8443`, \
                 got `{raw}`: no non-empty entry"
            ),
        ));
    }
    Ok(Some(entries))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::*;

    /// Resolves a configuration from a literal variable table; entries absent
    /// from the table are unset.
    fn from_table(variables: &[(&str, &str)]) -> Result<Config, ConfigError> {
        let table: HashMap<&str, &str> = variables.iter().copied().collect();
        Config::from_lookup(|variable| table.get(variable).map(|value| (*value).to_string()))
    }

    #[test]
    fn defaults_when_unset() {
        let config = from_table(&[]).expect("defaults must resolve");
        assert_eq!(config.bind_addr, DEFAULT_BIND_ADDR);
        assert!(!config.tls.enabled);
        assert_eq!(config.tls.cert_path, None);
        assert_eq!(config.tls.key_path, None);
        assert_eq!(config.auth_token, None);
        assert_eq!(config.cli_bin, DEFAULT_CLI_BIN);
        assert_eq!(config.workspace_root, PathBuf::from(DEFAULT_WORKSPACE_ROOT));
        assert_eq!(
            config.upload_dir,
            PathBuf::from(DEFAULT_WORKSPACE_ROOT).join(DEFAULT_UPLOAD_DIR),
            "the upload dir defaults to `uploads` inside the workspace root"
        );
        assert_eq!(config.upload_max_bytes, 10_485_760);
        assert_eq!(
            config.subprocess_timeout,
            Duration::from_secs(DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)
        );
        assert_eq!(config.log_level, LogLevel::Info);
        assert_eq!(config.http_allowed_hosts, None);
    }

    #[test]
    fn overrides_are_applied() {
        let config = from_table(&[
            (BIND_ADDR_VAR, "127.0.0.1:9200"),
            (TLS_ENABLED_VAR, "true"),
            (TLS_CERT_PATH_VAR, "/etc/secondbrain/tls/cert.pem"),
            (TLS_KEY_PATH_VAR, "/etc/secondbrain/tls/key.pem"),
            (
                HTTP_ALLOWED_HOSTS_VAR,
                "ops.example.com, ops.example.com:8443",
            ),
            (AUTH_TOKEN_VAR, "secret-token"),
            (CLI_BIN_VAR, "/usr/local/bin/secondbrain"),
            (WORKSPACE_ROOT_VAR, "/data/workspace"),
            (UPLOAD_DIR_VAR, "/data/workspace/incoming"),
            (UPLOAD_MAX_BYTES_VAR, "52428800"),
            (SUBPROCESS_TIMEOUT_VAR, "30"),
            (LOG_LEVEL_VAR, "DEBUG"),
        ])
        .expect("overrides must resolve");
        assert_eq!(config.bind_addr, SocketAddr::from(([127, 0, 0, 1], 9200)));
        assert!(config.tls.enabled);
        assert_eq!(
            config.tls.cert_path,
            Some(PathBuf::from("/etc/secondbrain/tls/cert.pem"))
        );
        assert_eq!(
            config.tls.key_path,
            Some(PathBuf::from("/etc/secondbrain/tls/key.pem"))
        );
        assert_eq!(
            config.http_allowed_hosts,
            Some(vec![
                "ops.example.com".to_string(),
                "ops.example.com:8443".to_string()
            ])
        );
        assert_eq!(config.auth_token, Some("secret-token".to_string()));
        assert_eq!(config.cli_bin, "/usr/local/bin/secondbrain");
        assert_eq!(config.workspace_root, PathBuf::from("/data/workspace"));
        assert_eq!(
            config.upload_dir,
            PathBuf::from("/data/workspace/incoming"),
            "an absolute upload dir passes through"
        );
        assert_eq!(config.upload_max_bytes, 52_428_800);
        assert_eq!(config.subprocess_timeout, Duration::from_secs(30));
        assert_eq!(config.log_level, LogLevel::Debug);
    }

    #[test]
    fn a_relative_upload_dir_is_anchored_at_the_workspace_root() {
        let config = from_table(&[
            (WORKSPACE_ROOT_VAR, "/data/workspace"),
            (UPLOAD_DIR_VAR, "incoming"),
        ])
        .expect("a relative upload dir must resolve");
        assert_eq!(
            config.upload_dir,
            PathBuf::from("/data/workspace/incoming"),
            "a relative upload dir joins the workspace root, like an ingest path"
        );
    }

    #[test]
    fn a_value_above_the_cli_per_file_cap_is_accepted_at_upload() {
        // 200 MiB is above the CLI's own 100 MiB per-file processing cap: the
        // upload cap is parsed as configured (the CLI's gate still applies at
        // ingest time, on top of this one).
        let config =
            from_table(&[(UPLOAD_MAX_BYTES_VAR, "209715200")]).expect("a large cap must resolve");
        assert_eq!(config.upload_max_bytes, 209_715_200);
    }

    #[test]
    fn invalid_upload_max_bytes_names_the_variable() {
        let error = from_table(&[(UPLOAD_MAX_BYTES_VAR, "ten megabytes")])
            .expect_err("a non-numeric cap must be rejected");
        assert_eq!(error.variable, UPLOAD_MAX_BYTES_VAR);
        assert!(error.to_string().contains(UPLOAD_MAX_BYTES_VAR));
    }

    #[test]
    fn zero_upload_max_bytes_is_rejected() {
        let error = from_table(&[(UPLOAD_MAX_BYTES_VAR, "0")])
            .expect_err("a zero cap could never admit a document");
        assert_eq!(error.variable, UPLOAD_MAX_BYTES_VAR);
        assert!(error.to_string().contains(UPLOAD_MAX_BYTES_VAR));
    }

    #[test]
    fn empty_upload_values_are_treated_as_unset() {
        let config = from_table(&[(UPLOAD_DIR_VAR, ""), (UPLOAD_MAX_BYTES_VAR, "")])
            .expect("empty values must resolve to the defaults");
        assert_eq!(
            config.upload_dir,
            PathBuf::from(DEFAULT_WORKSPACE_ROOT).join(DEFAULT_UPLOAD_DIR)
        );
        assert_eq!(config.upload_max_bytes, 10_485_760);
    }

    #[test]
    fn invalid_bind_addr_names_the_variable() {
        // `localhost` must be rejected: the value is parsed as a socket
        // address, no hostname resolution, e.g. `0.0.0.0:8080`.
        let error = from_table(&[(BIND_ADDR_VAR, "localhost:8080")])
            .expect_err("an invalid bind address must be rejected");
        assert_eq!(error.variable, BIND_ADDR_VAR);
        assert!(error.to_string().contains(BIND_ADDR_VAR));
    }

    #[test]
    fn invalid_timeout_names_the_variable() {
        let error = from_table(&[(SUBPROCESS_TIMEOUT_VAR, "zero")])
            .expect_err("a non-numeric timeout must be rejected");
        assert_eq!(error.variable, SUBPROCESS_TIMEOUT_VAR);
        assert!(error.to_string().contains(SUBPROCESS_TIMEOUT_VAR));
    }

    #[test]
    fn zero_timeout_is_rejected() {
        let error = from_table(&[(SUBPROCESS_TIMEOUT_VAR, "0")])
            .expect_err("a zero timeout could never bound a subprocess");
        assert_eq!(error.variable, SUBPROCESS_TIMEOUT_VAR);
    }

    #[test]
    fn invalid_boolean_names_the_variable() {
        let error = from_table(&[(TLS_ENABLED_VAR, "yes")])
            .expect_err("a non-boolean TLS flag must be rejected");
        assert_eq!(error.variable, TLS_ENABLED_VAR);
        assert!(error.to_string().contains(TLS_ENABLED_VAR));
    }

    #[test]
    fn invalid_log_level_names_the_variable() {
        let error = from_table(&[(LOG_LEVEL_VAR, "verbose")])
            .expect_err("an unknown log level must be rejected");
        assert_eq!(error.variable, LOG_LEVEL_VAR);
        assert!(error.to_string().contains(LOG_LEVEL_VAR));
    }

    #[test]
    fn empty_auth_token_is_treated_as_unset() {
        let config = from_table(&[(AUTH_TOKEN_VAR, "")]).expect("an empty token must resolve");
        assert_eq!(config.auth_token, None);
    }

    #[test]
    fn allowed_hosts_single_host_is_kept_verbatim() {
        let config = from_table(&[(HTTP_ALLOWED_HOSTS_VAR, "ops.example.com")])
            .expect("a single host must resolve");
        assert_eq!(
            config.http_allowed_hosts,
            Some(vec!["ops.example.com".to_string()])
        );
    }

    #[test]
    fn allowed_hosts_entries_are_trimmed_and_ports_kept_verbatim() {
        let config = from_table(&[(
            HTTP_ALLOWED_HOSTS_VAR,
            "  ops.example.com  , gateway.example.com:8443 ",
        )])
        .expect("trimmed entries must resolve");
        assert_eq!(
            config.http_allowed_hosts,
            Some(vec![
                "ops.example.com".to_string(),
                "gateway.example.com:8443".to_string()
            ])
        );
    }

    #[test]
    fn allowed_hosts_whitespace_only_entries_are_skipped() {
        let config = from_table(&[(
            HTTP_ALLOWED_HOSTS_VAR,
            " , ops.example.com ,, gateway.example.com:8443 , ",
        )])
        .expect("whitespace-only entries must be skipped");
        assert_eq!(
            config.http_allowed_hosts,
            Some(vec![
                "ops.example.com".to_string(),
                "gateway.example.com:8443".to_string()
            ])
        );
    }

    #[test]
    fn allowed_hosts_with_no_valid_entry_names_the_variable() {
        let error = from_table(&[(HTTP_ALLOWED_HOSTS_VAR, " , ,, ")])
            .expect_err("a value with only whitespace entries must be rejected");
        assert_eq!(error.variable, HTTP_ALLOWED_HOSTS_VAR);
        assert!(error.to_string().contains(HTTP_ALLOWED_HOSTS_VAR));
    }

    #[test]
    fn empty_allowed_hosts_is_treated_as_unset() {
        let config =
            from_table(&[(HTTP_ALLOWED_HOSTS_VAR, "")]).expect("an empty value must resolve");
        assert_eq!(config.http_allowed_hosts, None);
    }
}
