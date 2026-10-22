//! The `ingest_documents` MCP tool over the full HTTP surface: `tools/list`
//! discovery, relative-path resolution against the workspace root, absolute
//! pass-through, and CLI failure mapping — against a stub CLI and a real
//! fixture workspace, so no Python or Qdrant is needed.

mod common;

use common::{boot_with_cli_workspace, call_tool, fixture_workspace, json_body, tool_text};
use serde_json::json;

#[test]
fn tools_list_declares_ingest_documents() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    let response = common::post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let ingest = tools
        .iter()
        .find(|tool| tool["name"] == "ingest_documents")
        .expect("the registry must contain ingest_documents")
        .clone();

    let schema = &ingest["inputSchema"];
    let properties = schema["properties"]
        .as_object()
        .expect("the input schema must declare properties");
    for field in [
        "path",
        "recursive",
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
    assert_eq!(
        schema["required"]
            .as_array()
            .expect("a required list")
            .iter()
            .filter_map(|name| name.as_str())
            .collect::<Vec<_>>(),
        ["path"],
        "only the path is required: {schema}"
    );
    assert_eq!(properties["path"]["type"], "string");
    for field in ["recursive", "skip_existing"] {
        let property = properties[field].to_string();
        assert!(
            property.contains("boolean"),
            "{field} must be a boolean: {property}"
        );
    }
    for field in ["chunk_size", "chunk_overlap", "batch_size", "cores"] {
        let property = properties[field].to_string();
        assert!(
            property.contains("integer"),
            "{field} must be an integer: {property}"
        );
    }
}

#[test]
fn a_relative_path_resolves_against_the_workspace_root() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

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
        "ingesting an existing relative path must succeed: {body}"
    );

    let text = tool_text(&body);
    let expected = fixture_workspace().join("report.txt");
    assert!(
        text.contains(expected.to_string_lossy().as_ref()),
        "the CLI must receive the resolved absolute path: {text}"
    );
    assert!(
        text.contains("ingest summary (from the secondbrain CLI)"),
        "the result must note the CLI summary origin: {text}"
    );
    assert!(
        text.contains("2 documents, 5 chunks"),
        "the CLI's summary must be carried: {text}"
    );
}

#[test]
fn an_absolute_path_passes_through() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    let absolute = fixture_workspace().join("report.txt");
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
        "ingesting an existing absolute path must succeed: {body}"
    );
    assert!(
        tool_text(&body).contains(absolute.to_string_lossy().as_ref()),
        "the CLI must receive the same absolute path: {body}"
    );
}

#[test]
fn optional_flags_map_to_the_cli_invocation() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    // The stub echoes its argv in the summary, so the mapped flags are
    // observable end-to-end.
    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({
            "path": "docs",
            "recursive": true,
            "skip_existing": false,
            "chunk_size": 1024,
            "chunk_overlap": 128,
            "batch_size": 30,
            "cores": 2
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let text = tool_text(&body);
    let expected_path = fixture_workspace().join("docs");
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "ingesting the existing fixture directory must succeed: {body}"
    );
    assert!(
        text.contains(expected_path.to_string_lossy().as_ref()),
        "the CLI must receive the resolved directory: {text}"
    );
    for mapped in [
        "-r",
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
}

#[test]
fn defaults_map_to_a_bare_invocation() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "report.txt"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let text = tool_text(&body);
    assert!(
        !text.contains("-r\n") && !text.contains("--no-skip-existing"),
        "default flags must map to no CLI flags: {text}"
    );
}

#[test]
fn a_missing_path_maps_to_a_tool_error() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    // The stub validates like the real CLI (click.Path(exists=True)): a
    // missing path exits 1 with a diagnostic.
    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "no-such-file.txt"}),
    );
    assert_eq!(
        response.status, 200,
        "tool errors are JSON-RPC results, not transport failures: {response:?}"
    );
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a failed CLI run must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("exit code 1") && text.contains("no such file or directory"),
        "the diagnostics must carry the CLI's failure: {text}"
    );
}

#[test]
fn a_cli_failure_maps_to_a_tool_error() {
    let server = boot_with_cli_workspace("stub_ingest.sh", &[]);

    // BOOM.txt exists in the fixture workspace, but the stub fails on it:
    // a tool error with diagnostics, even though the path is valid.
    let response = call_tool(&server, 1, "ingest_documents", json!({"path": "BOOM.txt"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a failed CLI run must be a tool error: {body}"
    );
    assert!(
        tool_text(&body).contains("exploded"),
        "the diagnostics must carry the CLI's stderr: {body}"
    );
}

/// Optional real-CLI round trip (excluded from the default suite: it needs
/// the actual `secondbrain` CLI entrypoint on the machine and the test
/// Qdrant stack from `revise-compose-test-stack`). Point
/// `SECONDBRAIN_MCP_CLI_BIN` at the CLI entrypoint and run
/// `cargo test -- --ignored` to exercise it.
#[ignore = "requires the real secondbrain CLI and the test Qdrant stack"]
#[test]
fn real_cli_ingest_round_trip() {
    let bin = std::env::var("SECONDBRAIN_MCP_CLI_BIN")
        .expect("set SECONDBRAIN_MCP_CLI_BIN to the real secondbrain CLI entrypoint");
    let workspace = fixture_workspace();
    let server = common::RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_CLI_BIN", &bin),
        (
            "SECONDBRAIN_MCP_WORKSPACE_ROOT",
            workspace.to_string_lossy().as_ref(),
        ),
    ]);

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
        "a real ingest of the fixture file must succeed (test Qdrant stack up): {body}"
    );
}
