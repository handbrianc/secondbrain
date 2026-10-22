//! Startup confinement for the `upload_document` tool's storage directory: a
//! `SECONDBRAIN_MCP_UPLOAD_DIR` that resolves outside the workspace root
//! refuses startup (exit 1, stderr naming the variable) before anything
//! binds, while a missing-inside or relative directory boots and is created
//! on demand at upload time — and an upload through it then reaches the CLI
//! as an inside-the-root path, which the stub's workspace-root check
//! verifies (it exits 9 on any path the root does not contain).

mod common;

use common::{
    ServerRun, WorkspaceCopy, boot_with_workspace, call_tool, fixture_workspace, json_body,
    sample_upload_base64, tool_text,
};
use serde_json::json;
use std::path::Path;

/// A spawn-log path for one test: the stub appends a line per CLI spawn, so
/// the recorded argv is the confined path the CLI received.
fn spawn_log(tag: &str) -> String {
    let path = std::env::temp_dir().join(format!(
        "mcp-stub-upload-spawns-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_file(&path);
    path.to_string_lossy().into_owned()
}

/// Runs the binary to exit with a workspace root and an upload directory to
/// validate.
///
/// TLS is enabled without certificate paths as a guard rail: the upload
/// directory is validated before the TLS material loads, so a correct
/// refusal must name the upload variable — while a wrongly-accepted one
/// would go on to exit with the TLS refusal (and never hang this
/// run-to-exit helper by serving).
fn run_with_upload_dir(workspace_root: &Path, upload_dir: &str) -> ServerRun {
    let root = workspace_root.to_string_lossy().into_owned();
    ServerRun::run(&[
        ("SECONDBRAIN_MCP_WORKSPACE_ROOT", root.as_str()),
        ("SECONDBRAIN_MCP_UPLOAD_DIR", upload_dir),
        ("SECONDBRAIN_MCP_HTTP_TLS_ENABLED", "true"),
    ])
}

/// The shared startup-refusal contract: exit 1, before anything binds, with
/// stderr naming the upload variable and the confinement rule.
fn assert_startup_refusal(run: &ServerRun) {
    assert!(
        !run.status.success(),
        "an escaping upload directory must refuse startup: {run:?}"
    );
    assert!(
        !run.stdout.contains("listening on"),
        "the refusal must happen before anything binds: {run:?}"
    );
    assert!(
        run.stderr.contains("SECONDBRAIN_MCP_UPLOAD_DIR")
            && run.stderr.contains("escapes the workspace"),
        "the refusal must name the variable and the confinement rule: {run:?}"
    );
    assert!(
        !run.stderr.contains("invalid TLS configuration"),
        "the guard-rail TLS refusal must not fire: the upload check refuses first: {run:?}"
    );
}

#[test]
fn an_absolute_upload_dir_outside_the_root_refuses_startup() {
    let outside =
        std::env::temp_dir().join(format!("mcp-upload-refuse-outside-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&outside);
    std::fs::create_dir_all(&outside).expect("the outside directory must create");

    let run = run_with_upload_dir(&fixture_workspace(), outside.to_string_lossy().as_ref());
    assert_startup_refusal(&run);

    let _ = std::fs::remove_dir_all(&outside);
}

#[test]
fn a_traversal_upload_dir_refuses_startup() {
    // The directory does not exist, so it is compared lexically:
    // `../outside-uploads` joins the root and normalizes to a sibling of the
    // workspace root — outside by construction.
    let run = run_with_upload_dir(&fixture_workspace(), "../outside-uploads");
    assert_startup_refusal(&run);
}

#[cfg(unix)]
#[test]
fn a_symlinked_outside_upload_dir_refuses_startup() {
    let copy = WorkspaceCopy::new("refuse-symlink");
    let target =
        std::env::temp_dir().join(format!("mcp-upload-refuse-target-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&target);
    std::fs::create_dir_all(&target).expect("the outside target must create");
    std::os::unix::fs::symlink(&target, copy.workspace.join("outside-link"))
        .expect("the symlink must create");

    // An existing path is canonicalized, so the link resolves to the outside
    // target and the startup check must see through it.
    let link = copy.workspace.join("outside-link");
    let run = run_with_upload_dir(&copy.workspace, link.to_string_lossy().as_ref());
    assert_startup_refusal(&run);

    let _ = std::fs::remove_dir_all(&target);
}

/// The default upload directory (`<workspace root>/uploads`) does not exist
/// at boot: the startup confinement must accept a not-yet-created directory
/// inside the root, and the directory is created on demand by the first
/// upload — never by the server's startup.
#[test]
fn the_default_upload_dir_boots_without_existing_and_is_created_on_demand() {
    let workspace = WorkspaceCopy::new("default-dir");
    let log = spawn_log("default-dir");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("STUB_INGEST_SPAWN_LOG", &log)],
    );
    assert!(
        !workspace.upload_dir().exists(),
        "booting must not create the upload directory"
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "report.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "an upload into the default directory must succeed: {body}"
    );

    // The first upload creates the default directory on demand; its staged
    // file is deleted again by the successful ingest.
    let stored = workspace.upload_dir().join("report.txt");
    assert!(
        workspace.upload_dir().is_dir(),
        "the first upload must create the default directory on demand"
    );
    assert!(
        !stored.exists(),
        "a successful ingest deletes the staged file"
    );

    // The stub's own workspace-root check (exit 9 on an outside path) passed,
    // and the recorded argv is the confined stored path the CLI received.
    let recorded = std::fs::read_to_string(&log).expect("the spawn log must exist");
    let spawns: Vec<&str> = recorded
        .lines()
        .filter(|l| l.starts_with("spawn: "))
        .collect();
    assert_eq!(
        spawns.len(),
        1,
        "exactly one CLI ingest must run: {recorded}"
    );
    assert!(
        spawns[0].contains(stored.to_string_lossy().as_ref()),
        "the CLI must receive the stored path inside the root: {recorded}"
    );
}

/// A relative `SECONDBRAIN_MCP_UPLOAD_DIR` anchors at the workspace root
/// (like a relative ingest path): a missing `staging` inside the root boots,
/// and an upload stores into it and hands the confined path to the CLI.
#[test]
fn a_relative_upload_dir_anchors_at_the_workspace_root_and_reaches_the_cli() {
    let workspace = WorkspaceCopy::new("relative");
    let log = spawn_log("relative");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[
            ("SECONDBRAIN_MCP_UPLOAD_DIR", "staging"),
            ("STUB_INGEST_SPAWN_LOG", &log),
        ],
    );
    let staging = workspace.workspace.join("staging");
    assert!(
        !staging.exists(),
        "booting must not create the upload directory"
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "notes.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "an upload into the anchored directory must succeed: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("stored at staging/notes.txt (relative to the workspace root)"),
        "the stored path must be reported relative to the workspace root: {text}"
    );

    // The upload stores inside the anchored directory; the successful
    // ingest then deletes the staged file.
    let stored = staging.join("notes.txt");
    assert!(
        staging.is_dir(),
        "the upload must create the anchored directory on demand"
    );
    assert!(
        !stored.exists(),
        "a successful ingest deletes the staged file"
    );

    // The stub's own workspace-root check (exit 9 on an outside path) passed,
    // and the recorded argv is the confined stored path the CLI received.
    let recorded = std::fs::read_to_string(&log).expect("the spawn log must exist");
    let spawns: Vec<&str> = recorded
        .lines()
        .filter(|l| l.starts_with("spawn: "))
        .collect();
    assert_eq!(
        spawns.len(),
        1,
        "exactly one CLI ingest must run: {recorded}"
    );
    assert!(
        spawns[0].contains(stored.to_string_lossy().as_ref()),
        "the CLI must receive the stored path inside the root: {recorded}"
    );
}
