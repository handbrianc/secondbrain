//! The `upload_document` MCP tool over the full HTTP surface: discovery,
//! validate-before-store rules (base64, size cap, filename, collision),
//! storage plus the stored-path + CLI-summary result, CLI-failure retention,
//! and the `/mcp` body budget that admits upload-sized calls — against a
//! stub CLI and a per-test workspace copy, so no Python, Qdrant, or fixture
//! writes are involved.

mod common;

use common::{
    WorkspaceCopy, boot_with_cli, boot_with_workspace, call_tool, fixture_upload, http_request,
    json_body, post_mcp, sample_upload_base64, tool_text,
};
use serde_json::json;
use std::path::Path;

/// A spawn-log path for one test: the stub appends a line per spawn, so an
/// empty log proves no CLI subprocess started and a written line records the
/// argv (the confined path the CLI received).
fn spawn_log(tag: &str) -> String {
    let path = std::env::temp_dir().join(format!(
        "mcp-stub-upload-spawns-{tag}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_file(&path);
    path.to_string_lossy().into_owned()
}

/// Builds a base64 payload that decodes to exactly `decoded_bytes` bytes:
/// `"QUFB"` encodes `"AAA"` (three bytes), so a multiple of three yields a
/// canonical, padding-free payload of `4/3 × decoded_bytes` characters —
/// size boundaries without a base64 encoder in the test.
fn payload_base64(decoded_bytes: usize) -> String {
    assert_eq!(
        decoded_bytes % 3,
        0,
        "the payload trick needs a multiple of three"
    );
    "QUFB".repeat(decoded_bytes / 3)
}

#[test]
fn tools_list_declares_upload_document() {
    let workspace = WorkspaceCopy::new("discovery");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let upload = tools
        .iter()
        .find(|tool| tool["name"] == "upload_document")
        .expect("the registry must contain upload_document")
        .clone();

    let schema = &upload["inputSchema"];
    let properties = schema["properties"]
        .as_object()
        .expect("the input schema must declare properties");
    for field in [
        "filename",
        "content_base64",
        "skip_existing",
        "chunk_size",
        "chunk_overlap",
        "batch_size",
        "cores",
    ] {
        assert!(
            properties.contains_key(field),
            "the input schema must declare {field}: {schema}"
        );
    }
    let mut required: Vec<String> = schema["required"]
        .as_array()
        .expect("a required list")
        .iter()
        .filter_map(|name| name.as_str().map(str::to_string))
        .collect();
    required.sort();
    assert_eq!(
        required,
        ["content_base64", "filename"],
        "the filename and the payload are required: {schema}"
    );
    for field in ["filename", "content_base64"] {
        assert_eq!(
            properties[field]["type"], "string",
            "{field} must be a string: {schema}"
        );
    }
    assert!(
        properties["skip_existing"].to_string().contains("boolean"),
        "skip_existing must be a boolean: {schema}"
    );
    for field in ["chunk_size", "chunk_overlap", "batch_size", "cores"] {
        assert!(
            properties[field].to_string().contains("integer"),
            "{field} must be an integer: {schema}"
        );
    }

    let description = upload["description"].as_str().expect("a description");
    assert!(
        description.contains("Store a document in the workspace and ingest it"),
        "the description must state that the document is stored and ingested: {description}"
    );
}

#[test]
fn a_successful_upload_stores_and_ingests() {
    let workspace = WorkspaceCopy::new("success");
    let log = spawn_log("success");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("STUB_INGEST_SPAWN_LOG", &log)],
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "sample.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a valid upload must succeed: {body}"
    );

    let text = tool_text(&body);
    assert!(
        text.contains("stored at uploads/sample.txt (relative to the workspace root)"),
        "the result must carry the stored path relative to the workspace root: {text}"
    );
    assert!(
        text.contains("ingest summary (from the secondbrain CLI)"),
        "the result must carry the CLI summary with the usual prefix: {text}"
    );
    assert!(
        text.contains("1 documents, 3 chunks"),
        "the CLI's summary must be carried: {text}"
    );
    assert!(
        text.contains("the staged file was deleted after the successful ingest"),
        "the success must state that the staged file was deleted: {text}"
    );

    // A successful ingest deletes the staged file — the upload directory is
    // a transient inbox. The stub CLI received the stored bytes while the
    // file existed; the spawn log below proves the ingest ran against it.
    let stored = workspace.upload_dir().join("sample.txt");
    assert!(
        !stored.exists(),
        "a successful ingest must delete the staged file"
    );

    // The CLI ran exactly once, receiving the stored (inside-the-root) path.
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
        "the CLI must receive the stored path: {recorded}"
    );
}

#[test]
fn ingest_parameters_map_to_the_cli_invocation() {
    let workspace = WorkspaceCopy::new("flags");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    // The stub echoes its argv in the summary, so the mapped flags are
    // observable end-to-end.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "sample.txt",
            "content_base64": sample_upload_base64(),
            "skip_existing": false,
            "chunk_size": 1024,
            "chunk_overlap": 128,
            "batch_size": 30,
            "cores": 2
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "the upload must succeed: {body}"
    );
    let text = tool_text(&body);
    for mapped in [
        "--no-skip-existing",
        "--chunk-size 1024",
        "--chunk-overlap 128",
        "-b 30",
        "-c 2",
    ] {
        assert!(
            text.contains(mapped),
            "the CLI argv must carry {mapped}: {text}"
        );
    }
    assert!(
        !text.contains("-r\n") && !text.contains(" -r "),
        "recursion never applies to a single uploaded file: {text}"
    );
}

#[test]
fn a_cli_failure_after_storage_retains_the_file() {
    let workspace = WorkspaceCopy::new("cli-failure");
    let log = spawn_log("cli-failure");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("STUB_INGEST_SPAWN_LOG", &log)],
    );

    // The stub fails on BOOM.txt by name (its sentinel), like the real CLI
    // failing on an unsupported extension or an unreachable Qdrant: the file
    // is already stored when the CLI runs.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "BOOM.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(
        response.status, 200,
        "tool errors are JSON-RPC results, not transport failures: {response:?}"
    );
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a failed ingest after storage must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("stored at uploads/BOOM.txt"),
        "the error must carry the stored path: {text}"
    );
    assert!(
        text.contains("exit code 1") && text.contains("exploded"),
        "the error must carry the CLI's captured output: {text}"
    );

    // The stored file remains in place for a later re-ingest.
    let stored = workspace.upload_dir().join("BOOM.txt");
    assert!(
        stored.is_file(),
        "a failed ingest must retain the stored file"
    );
    assert_eq!(
        std::fs::read(&stored).expect("the stored file must read"),
        std::fs::read(fixture_upload("sample-document.txt")).expect("the fixture must read"),
        "the retained file must hold the uploaded bytes"
    );
}

#[test]
fn a_failed_deletion_is_reported_in_an_otherwise_successful_result() {
    let workspace = WorkspaceCopy::new("delete-blocked");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    // The stub replaces STUCK.txt with a same-named directory before
    // exiting 0: the server's post-ingest cleanup then fails
    // deterministically (remove_file refuses directories), exercising the
    // delete-failure path end to end.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "STUCK.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a failed deletion must not fail an ingested upload: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("stored at uploads/STUCK.txt"),
        "the result must carry the stored path: {text}"
    );
    assert!(
        text.contains("deleting the staged file after the successful ingest failed"),
        "the result must report the failed deletion: {text}"
    );
    assert!(
        text.contains("the file remains in place"),
        "the result must say the staged file remains: {text}"
    );
    assert!(
        text.contains("ingest summary (from the secondbrain CLI)"),
        "the CLI summary must still be carried: {text}"
    );
    assert!(
        workspace.upload_dir().join("STUCK.txt").is_dir(),
        "the unremovable staged path must remain in place"
    );
}

#[test]
fn oversize_content_is_rejected_and_nothing_is_stored() {
    let workspace = WorkspaceCopy::new("oversize");
    let log = spawn_log("oversize");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[
            ("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES", "3072"),
            ("STUB_INGEST_SPAWN_LOG", &log),
        ],
    );

    // Decodes to 3075 bytes: 3 over the configured 3072-byte cap.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "too-big.txt",
            "content_base64": payload_base64(3075)
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "oversize content must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("too large") && text.contains("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES"),
        "the rejection must name the variable: {text}"
    );
    assert!(
        text.contains("nothing was stored"),
        "the rejection must state that nothing was stored: {text}"
    );

    // Nothing stored, and therefore nothing ingested.
    assert!(
        !workspace.upload_dir().exists()
            || workspace
                .upload_dir()
                .read_dir()
                .expect("readable")
                .next()
                .is_none(),
        "oversize content must not be stored"
    );
    assert!(
        !Path::new(&log).exists(),
        "no CLI subprocess may start when nothing was stored"
    );
}

#[test]
fn content_at_the_configured_limit_is_accepted() {
    let workspace = WorkspaceCopy::new("at-limit");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES", "3072")],
    );

    // Decodes to exactly 3072 bytes: at the limit, not over it.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "exact.txt",
            "content_base64": payload_base64(3072)
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "content at the limit must be accepted: {body}"
    );
    let stored = workspace.upload_dir().join("exact.txt");
    assert!(
        tool_text(&body).contains("the staged file was deleted after the successful ingest"),
        "content at the limit must be accepted and ingested, not size-rejected: {}",
        tool_text(&body)
    );
    assert!(
        !stored.exists(),
        "a successful ingest deletes the staged file, even at the size limit"
    );
}

#[test]
fn invalid_base64_is_rejected_and_nothing_is_stored() {
    let workspace = WorkspaceCopy::new("bad-b64");
    let log = spawn_log("bad-b64");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("STUB_INGEST_SPAWN_LOG", &log)],
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "mangled.txt",
            "content_base64": "definitely not base64!!"
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "invalid base64 must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("not valid base64"),
        "the rejection must describe the decode failure: {text}"
    );
    assert!(
        !workspace.upload_dir().exists(),
        "nothing may be stored for undecodable content"
    );
    assert!(
        !Path::new(&log).exists(),
        "no CLI subprocess may start when nothing was stored"
    );
}

#[test]
fn an_unusable_filename_is_rejected() {
    let workspace = WorkspaceCopy::new("bad-name");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    for filename in ["", ".", "..", "nested/.."] {
        let response = call_tool(
            &server,
            1,
            "upload_document",
            json!({
                "filename": filename,
                "content_base64": sample_upload_base64()
            }),
        );
        assert_eq!(response.status, 200, "{response:?}");
        let body = json_body(&response);
        assert_eq!(
            body["result"]["isError"], true,
            "the filename {filename:?} must be rejected: {body}"
        );
        assert!(
            tool_text(&body).contains("not usable"),
            "the rejection must describe the bare-name rule: {body}"
        );
    }
    assert!(
        !workspace.upload_dir().exists(),
        "a rejected filename must store nothing"
    );
}

#[test]
fn directory_components_are_stripped() {
    let workspace = WorkspaceCopy::new("strip");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "nested/deeper/report.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a path-carrying filename must be reduced, not rejected: {body}"
    );
    assert!(
        tool_text(&body).contains("stored at uploads/report.txt"),
        "the file must be stored under its bare name: {body}"
    );
    assert!(
        !workspace.upload_dir().join("report.txt").exists(),
        "the staged file is deleted after its successful ingest"
    );
    assert!(
        !workspace.upload_dir().join("nested").exists(),
        "no directory structure may be created from the filename"
    );
}

#[test]
fn a_collision_is_rejected_naming_the_existing_path() {
    let workspace = WorkspaceCopy::new("collision");
    let log = spawn_log("collision");
    std::fs::create_dir_all(workspace.upload_dir()).expect("the upload dir must create");
    std::fs::write(workspace.upload_dir().join("taken.txt"), "keep me").expect("the existing file");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("STUB_INGEST_SPAWN_LOG", &log)],
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "taken.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a collision must be a tool error: {body}"
    );
    let text = tool_text(&body);
    let existing = workspace.upload_dir().join("taken.txt");
    assert!(
        text.contains(existing.to_string_lossy().as_ref()),
        "the rejection must name the existing path: {text}"
    );
    assert!(
        text.contains("never overwrite"),
        "the rejection must state the no-overwrite policy: {text}"
    );
    assert_eq!(
        std::fs::read_to_string(&existing).expect("the existing file must read"),
        "keep me",
        "the existing file must be unchanged"
    );
    assert!(
        !Path::new(&log).exists(),
        "no CLI subprocess may start for a rejected upload"
    );
}

/// The derived body budget must be *operative*: a body far above it is
/// rejected by the transport with 413 (rmcp's default would be 4 MiB, which
/// would accept this request).
#[test]
fn a_body_over_the_derived_budget_is_rejected_413() {
    let workspace = WorkspaceCopy::new("budget-over");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES", "1024")],
    );

    // ~2.8 MB body against a derived budget of ceil(1024 × 4/3) + 1 MiB ≈
    // 1.05 MB: rejected before the tool handler runs.
    let oversized = json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "upload_document",
            "arguments": {
                "filename": "big.txt",
                "content_base64": payload_base64(2_100_000)
            }
        }
    });
    let response = post_mcp(&server, oversized);
    assert_eq!(
        response.status, 413,
        "a body over the derived budget must be rejected by the transport: {response:?}"
    );
    assert!(
        response.body.contains("Payload Too Large"),
        "the 413 must say why: {response:?}"
    );
    assert!(
        !workspace.upload_dir().exists(),
        "a transport-rejected upload must store nothing"
    );
}

/// An upload at the configured limit reaches the tool handler: the derived
/// body budget grows with `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`, so a body that
/// exceeds the framework's 2 MB default is accepted end to end.
#[test]
fn an_upload_at_the_configured_limit_is_accepted_end_to_end() {
    let workspace = WorkspaceCopy::new("budget-at");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES", "1572864")],
    );

    // Decoded 1.5 MiB == the configured limit → base64 payload of 2 MiB →
    // JSON body ≈ 2.1 MB, above axum's 2 MB default and well under the
    // derived budget of 2 MiB + 1 MiB slack.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "at-limit.bin",
            "content_base64": payload_base64(1_572_864)
        }),
    );
    assert_eq!(
        response.status, 200,
        "a call at the configured limit must reach the tool handler: {response:?}"
    );
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "the at-limit upload must succeed end to end: {}",
        serde_json::to_string(&body).unwrap_or_default()
    );
    let stored = workspace.upload_dir().join("at-limit.bin");
    assert!(
        tool_text(&body).contains("the staged file was deleted after the successful ingest"),
        "the at-limit upload must be accepted and ingested end to end: {}",
        tool_text(&body)
    );
    assert!(
        !stored.exists(),
        "a successful ingest deletes the staged file"
    );
}

/// With auth enabled, the unauthenticated call is rejected at the HTTP layer
/// by the existing `/mcp` middleware — there is no upload-specific auth code,
/// so nothing is stored and the CLI never runs.
#[test]
fn unauthenticated_upload_document_is_rejected_by_the_http_layer() {
    let workspace = WorkspaceCopy::new("auth");
    let server = boot_with_workspace(
        "stub_ingest_upload.sh",
        &workspace.workspace,
        &[("SECONDBRAIN_MCP_AUTH_TOKEN", "tok")],
    );

    let response = http_request(
        "POST",
        server.address,
        "/mcp",
        &[
            ("Content-Type", "application/json"),
            ("Accept", "application/json, text/event-stream"),
        ],
        Some(
            &json!({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "upload_document",
                    "arguments": {
                        "filename": "sample.txt",
                        "content_base64": sample_upload_base64()
                    }
                }
            })
            .to_string(),
        ),
    );
    assert_eq!(
        response.status, 401,
        "an unauthenticated tools/call must be rejected by the middleware: {response:?}"
    );
    assert!(
        response
            .header("www-authenticate")
            .map(|v| v.contains("Bearer"))
            == Some(true),
        "the 401 must carry the bearer challenge: {response:?}"
    );
    assert!(
        !workspace.upload_dir().exists(),
        "a rejected request must store nothing"
    );
}

/// Optional real-CLI round trip (excluded from the default suite: it needs
/// the actual `secondbrain` CLI entrypoint on the machine and the test
/// Qdrant stack from `docker-compose.test.yml`). Point
/// `SECONDBRAIN_MCP_CLI_BIN` at the CLI entrypoint and run
/// `cargo test -- --ignored` to exercise it.
#[ignore = "requires the real secondbrain CLI and the test Qdrant stack"]
#[test]
fn real_cli_upload_round_trip() {
    let bin = std::env::var("SECONDBRAIN_MCP_CLI_BIN")
        .expect("set SECONDBRAIN_MCP_CLI_BIN to the real secondbrain CLI entrypoint");
    let workspace = WorkspaceCopy::new("real-cli");
    let server = boot_with_cli(
        "stub_ingest_upload.sh",
        &[
            ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
            ("SECONDBRAIN_MCP_CLI_BIN", &bin),
            (
                "SECONDBRAIN_MCP_WORKSPACE_ROOT",
                workspace.workspace.to_string_lossy().as_ref(),
            ),
        ],
    );

    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "sample-document.txt",
            "content_base64": sample_upload_base64()
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a real upload-and-ingest must succeed (test Qdrant stack up): {body}"
    );
    assert!(
        tool_text(&body).contains("stored at uploads/sample-document.txt"),
        "the result must carry the stored path: {body}"
    );
}
