//! TLS serving configuration: loading the PEM certificate/key pair when TLS
//! is enabled, with fail-fast errors naming the offending variable.
//!
//! Loading happens only on the TLS-enabled path — with TLS disabled the
//! certificate/key variables are ignored entirely and no validation runs
//! (`add-mcp-tls-support`).

use std::fs;

use axum_server::tls_rustls::RustlsConfig;
use thiserror::Error;

// Variable names, mirrored from the config so a TLS failure points at the
// exact knob to fix.
const TLS_CERT_PATH_VAR: &str = "SECONDBRAIN_MCP_HTTP_TLS_CERT_PATH";
const TLS_KEY_PATH_VAR: &str = "SECONDBRAIN_MCP_HTTP_TLS_KEY_PATH";

/// A failure to load the TLS material.
///
/// Mirrors [`crate::config::ConfigError`]: the message names the offending
/// `SECONDBRAIN_MCP_HTTP_TLS_*` variable so the entrypoint can point at
/// exactly what to fix.
#[derive(Debug, Error)]
#[error("{variable}: {reason}")]
pub struct TlsLoadError {
    /// The `SECONDBRAIN_MCP_HTTP_TLS_*` variable at fault.
    variable: &'static str,
    /// Why the material was rejected.
    reason: String,
}

impl TlsLoadError {
    fn new(variable: &'static str, reason: impl Into<String>) -> Self {
        Self {
            variable,
            reason: reason.into(),
        }
    }
}

/// Loads the TLS serving material from the configured paths.
///
/// Only called when TLS is enabled. Every failure names the offending
/// `SECONDBRAIN_MCP_HTTP_TLS_*` variable.
pub async fn load(tls: &crate::config::TlsConfig) -> Result<RustlsConfig, TlsLoadError> {
    let cert_path = tls
        .cert_path
        .as_deref()
        .ok_or_else(|| TlsLoadError::new(TLS_CERT_PATH_VAR, "must be set when TLS is enabled"))?;
    let key_path = tls
        .key_path
        .as_deref()
        .ok_or_else(|| TlsLoadError::new(TLS_KEY_PATH_VAR, "must be set when TLS is enabled"))?;

    let cert_pem = fs::read(cert_path).map_err(|error| {
        TlsLoadError::new(
            TLS_CERT_PATH_VAR,
            format!("cannot read {cert_path:?}: {error}"),
        )
    })?;
    require_pem_certificate(&cert_pem).map_err(|reason| {
        TlsLoadError::new(TLS_CERT_PATH_VAR, format!("{cert_path:?} {reason}"))
    })?;

    let key_pem = fs::read(key_path).map_err(|error| {
        TlsLoadError::new(
            TLS_KEY_PATH_VAR,
            format!("cannot read {key_path:?}: {error}"),
        )
    })?;
    require_pem_private_key(&key_pem)
        .map_err(|reason| TlsLoadError::new(TLS_KEY_PATH_VAR, format!("{key_path:?} {reason}")))?;

    // rustls parses the chain before the key, so a rejection here is
    // attributed to the certificate side; both paths are named so the
    // operator can tell which file is at fault.
    RustlsConfig::from_pem(cert_pem, key_pem)
        .await
        .map_err(|error| {
            TlsLoadError::new(
                TLS_CERT_PATH_VAR,
                format!("rustls rejected the material from {cert_path:?} / {key_path:?}: {error}"),
            )
        })
}

/// Checks that the bytes contain a PEM certificate block.
fn require_pem_certificate(pem: &[u8]) -> Result<(), String> {
    require_pem_block(pem, "CERTIFICATE")
}

/// Checks that the bytes contain a PEM private-key block, in any of the
/// encodings rustls accepts (`PRIVATE KEY` covers PKCS#8, and legacy
/// `RSA PRIVATE KEY` / `EC PRIVATE KEY` contain the same phrase).
fn require_pem_private_key(pem: &[u8]) -> Result<(), String> {
    let text = as_pem_text(pem)?;
    let markers = ["-----BEGIN ", "-----END ", "PRIVATE KEY"];
    if !markers.iter().all(|marker| text.contains(marker)) {
        return Err("is not a PEM private key".to_string());
    }
    Ok(())
}

/// Checks that the bytes contain a PEM block of the given kind.
fn require_pem_block(pem: &[u8], kind: &str) -> Result<(), String> {
    let text = as_pem_text(pem)?;
    for marker in ["-----BEGIN ", "-----END "] {
        if !text.contains(format!("{marker}{kind}-----").as_str()) {
            return Err(format!("is not PEM: no {kind} block"));
        }
    }
    Ok(())
}

/// Decodes PEM candidate bytes as UTF-8 text.
fn as_pem_text(pem: &[u8]) -> Result<&str, String> {
    std::str::from_utf8(pem).map_err(|_| "is not UTF-8 text".to_string())
}
