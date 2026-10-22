//! The health endpoint: `GET /healthz` returns 200 with `application/json`
//! and a body that parses to `{"status":"ok"}`, independent of MCP protocol
//! handling (none exists yet; it arrives with the transport proposal).

mod common;

use common::{RunningServer, http_get};

#[test]
fn healthz_reports_ok() {
    let server = RunningServer::boot(&[("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0")]);
    let response = http_get(server.address, "/healthz");
    assert_eq!(response.status, 200, "health must report 200: {response:?}");
    assert_eq!(
        response.content_type.as_deref(),
        Some("application/json"),
        "health must be served as JSON: {response:?}"
    );
    let body: serde_json::Value =
        serde_json::from_str(&response.body).expect("the health body must parse as JSON");
    assert_eq!(body["status"], "ok", "health must report status ok");
}
