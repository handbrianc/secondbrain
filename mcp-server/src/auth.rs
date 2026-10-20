//! Optional static bearer authentication for the MCP surface.
//!
//! Enforced when and only when `SECONDBRAIN_MCP_AUTH_TOKEN` is configured:
//! requests must carry `Authorization: Bearer <token>` matching the token,
//! compared in constant time, and anything else is answered 401 with
//! `WWW-Authenticate: Bearer`. With the variable unset (or empty) the surface
//! stays open — the v1 private-stack posture; the full OAuth 2.1
//! resource-server flow is the recorded follow-up.

use std::sync::Arc;

use axum::{
    extract::{Request, State},
    http::{HeaderMap, StatusCode, header},
    middleware::Next,
    response::{IntoResponse, Response},
};
use subtle::ConstantTimeEq;

/// Middleware state: the configured bearer token, when auth is enabled.
#[derive(Clone, Debug)]
pub struct AuthState {
    /// The static bearer token; `None` leaves the surface open.
    token: Option<Arc<str>>,
}

impl AuthState {
    /// Builds the middleware state from the configured token; `None` (unset
    /// or empty in the config) means open mode.
    pub fn new(token: Option<String>) -> Self {
        Self {
            token: token.map(Arc::from),
        }
    }
}

/// Enforces the optional bearer token: in open mode everything passes
/// through; otherwise the request must present the exact token, or it is
/// answered 401 with `WWW-Authenticate: Bearer`.
pub async fn bearer_auth(State(auth): State<AuthState>, request: Request, next: Next) -> Response {
    let Some(token) = auth.token.as_ref() else {
        return next.run(request).await;
    };
    let authorized =
        extract_token(request.headers()).is_some_and(|presented| tokens_match(presented, token));
    if !authorized {
        return (
            StatusCode::UNAUTHORIZED,
            [(header::WWW_AUTHENTICATE, "Bearer")],
        )
            .into_response();
    }
    next.run(request).await
}

/// Extracts the presented bearer token from the request headers.
///
/// `None` for every reject shape: no header, more than one `Authorization`
/// header, a non-UTF-8 value, a wrong scheme, or a missing/empty token after
/// the scheme. The scheme match is case-insensitive; the separator must be
/// exactly one space (extra or embedded spaces reject).
fn extract_token(headers: &HeaderMap) -> Option<&str> {
    let mut values = headers.get_all(header::AUTHORIZATION).iter();
    let value = values.next()?;
    if values.next().is_some() {
        return None;
    }
    parse_bearer(value.to_str().ok())
}

/// Splits an `Authorization` header value into its presented bearer token.
fn parse_bearer(value: Option<&str>) -> Option<&str> {
    let value = value?;
    let (scheme, presented) = value.split_once(' ')?;
    if !scheme.eq_ignore_ascii_case("bearer") {
        return None;
    }
    if presented.is_empty() || presented.contains(' ') {
        return None;
    }
    Some(presented)
}

/// Constant-time token comparison.
///
/// Both sides are padded to the same length first, so the comparison cannot
/// shortcut on length, and every byte goes through `subtle`'s
/// `ConstantTimeEq`. Padding uses NUL bytes, which cannot appear in header
/// values, so a presented token can never collide with another token's
/// padding.
fn tokens_match(presented: &str, configured: &str) -> bool {
    let width = presented.len().max(configured.len());
    let mut left = vec![0u8; width];
    let mut right = vec![0u8; width];
    left[..presented.len()].copy_from_slice(presented.as_bytes());
    right[..configured.len()].copy_from_slice(configured.as_bytes());
    left.ct_eq(&right).into()
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::HeaderValue;

    #[test]
    fn missing_header_is_rejected() {
        let headers = HeaderMap::new();
        assert_eq!(extract_token(&headers), None);
    }

    #[test]
    fn wrong_scheme_is_rejected() {
        assert_eq!(parse_bearer(Some("Basic dXNlcjpwYXNz")), None);
        assert_eq!(parse_bearer(Some("Digest realm=...")), None);
    }

    #[test]
    fn scheme_is_case_insensitive() {
        assert_eq!(parse_bearer(Some("bearer tok")), Some("tok"));
        assert_eq!(parse_bearer(Some("BEARER tok")), Some("tok"));
        assert_eq!(parse_bearer(Some("BeArEr tok")), Some("tok"));
    }

    #[test]
    fn scheme_without_separator_is_rejected() {
        assert_eq!(parse_bearer(Some("Bearer")), None);
    }

    #[test]
    fn empty_bearer_is_rejected() {
        assert_eq!(parse_bearer(Some("Bearer ")), None);
        assert_eq!(parse_bearer(Some("Bearer")), None);
    }

    #[test]
    fn extra_spaces_are_rejected() {
        assert_eq!(parse_bearer(Some("Bearer  tok")), None);
        assert_eq!(parse_bearer(Some("Bearer tok extra")), None);
    }

    #[test]
    fn multiple_header_values_are_rejected() {
        let mut headers = HeaderMap::new();
        headers.append(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer one"),
        );
        headers.append(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer two"),
        );
        assert_eq!(extract_token(&headers), None);
    }

    #[test]
    fn non_utf8_header_value_is_rejected() {
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_bytes(&[0xff]).expect("a raw header value"),
        );
        assert_eq!(extract_token(&headers), None);
    }

    #[test]
    fn matching_tokens_compare_equal() {
        assert!(tokens_match("tok", "tok"));
        assert!(tokens_match("", ""));
    }

    #[test]
    fn mismatched_tokens_differ() {
        assert!(!tokens_match("tok", "tot"));
        assert!(!tokens_match("same-length-a", "same-length-b"));
    }

    #[test]
    fn length_differing_tokens_differ() {
        assert!(!tokens_match("tok", "token"));
        assert!(!tokens_match("token", "tok"));
        assert!(!tokens_match("", "tok"));
        assert!(!tokens_match("tok", ""));
    }
}
