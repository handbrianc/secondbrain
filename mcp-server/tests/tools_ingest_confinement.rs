//! Workspace confinement for the `ingest_documents` tool over the full HTTP
//! surface: traversal, absolute-outside, and symlink escapes are rejected as
//! tool errors **before any CLI subprocess starts** (asserted via the stub's
//! spawn log), while valid inside paths still ingest.

mod common;

use common::{boot_with_cli_workspace, call_tool, fixture_workspace, json_body, tool_text};
use serde_json::json;

/// A fresh spawn-log path for one test: the stub appends a line per spawn,
/// so a missing log after a rejected call proves no subprocess started.
fn spawn_log(tag: &str) -> String {
    let path = std::env::temp_dir().join(format!(
        "mcp-stub-ingest-spawns-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_file(&path);
    path.to_string_lossy().into_owned()
}

#[test]
fn a_traversal_escape_is_rejected_before_any_spawn() {
    let log = spawn_log("traversal");
    let server = boot_with_cli_workspace("stub_ingest.sh", &[("STUB_INGEST_SPAWN_LOG", &log)]);

    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "../etc/passwd"}),
    );
    assert_eq!(
        response.status, 200,
        "the rejection is a JSON-RPC result, not a transport failure: {response:?}"
    );
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "an escaping path must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("escapes the workspace"),
        "the rejection must describe the confinement rule: {text}"
    );
    assert!(
        text.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
        "the rejection must name the variable: {text}"
    );
    assert!(
        !std::path::Path::new(&log).exists(),
        "no CLI subprocess may start for a rejected path"
    );
}

#[test]
fn an_absolute_path_outside_the_root_is_rejected_before_any_spawn() {
    let log = spawn_log("absolute");
    let server = boot_with_cli_workspace("stub_ingest.sh", &[("STUB_INGEST_SPAWN_LOG", &log)]);

    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "/etc/hosts"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "an escaping path must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("escapes the workspace") && text.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
        "the rejection must describe the rule and name the variable: {text}"
    );
    assert!(
        !std::path::Path::new(&log).exists(),
        "no CLI subprocess may start for a rejected path"
    );
}

#[test]
fn a_symlink_escape_is_rejected_before_any_spawn() {
    let log = spawn_log("symlink");
    let server = boot_with_cli_workspace("stub_ingest.sh", &[("STUB_INGEST_SPAWN_LOG", &log)]);

    // The fixture workspace carries `escape -> ../../../..` (the repo root,
    // outside the workspace): canonicalization resolves the symlink there.
    let response = call_tool(&server, 1, "ingest_documents", json!({"path": "escape"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a symlink escape must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("escapes the workspace") && text.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
        "the rejection must describe the rule and name the variable: {text}"
    );
    assert!(
        !std::path::Path::new(&log).exists(),
        "no CLI subprocess may start for a rejected path"
    );
}

#[test]
fn valid_relative_and_absolute_inside_paths_still_ingest() {
    let log = spawn_log("inside");
    let server = boot_with_cli_workspace("stub_ingest.sh", &[("STUB_INGEST_SPAWN_LOG", &log)]);

    // Relative inside: full success, and the spawn is recorded.
    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "report.txt"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a valid relative path must ingest as before: {body}"
    );
    assert!(
        tool_text(&body).contains("ingest summary"),
        "the CLI summary must be returned: {body}"
    );

    // Absolute inside: same.
    let absolute = fixture_workspace().join("docs");
    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": absolute.to_string_lossy()}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a valid absolute-inside path must ingest as before: {body}"
    );

    let recorded = std::fs::read_to_string(&log).expect("the spawn log must exist");
    assert_eq!(
        recorded
            .lines()
            .filter(|line| line.starts_with("spawn: "))
            .count(),
        2,
        "both valid ingests must have reached the CLI: {recorded}"
    );
}
