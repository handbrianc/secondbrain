//! The `search` MCP tool over the full HTTP surface: `tools/list`
//! discovery, threshold filtering, error mapping, and inert argument
//! passing — against stub CLIs so no Python or Qdrant is needed.

mod common;

use common::{RunningServer, boot_with_cli, call_tool, json_body, tool_text};
use serde_json::{Value, json};

#[test]
fn tools_list_declares_search() {
    let server = boot_with_cli("stub_search_success.sh", &[]);
    let response = common::post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );

    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let tools = body["result"]["tools"].as_array().expect("a tools array");
    let search = tools
        .iter()
        .find(|tool| tool["name"] == "search")
        .expect("the registry must contain search")
        .clone();

    let schema = &search["inputSchema"];
    let properties = schema["properties"]
        .as_object()
        .expect("the input schema must declare properties");
    for field in ["query", "top_k", "source", "file_type", "min_score"] {
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
        ["query"],
        "only the query is required: {schema}"
    );
    assert_eq!(properties["query"]["type"], "string");
    let top_k = properties["top_k"].to_string();
    assert!(
        top_k.contains("integer"),
        "top_k must be an integer: {top_k}"
    );
    let min_score = properties["min_score"].to_string();
    assert!(
        min_score.contains("number"),
        "min_score must be a number: {min_score}"
    );
}

#[test]
fn successful_search_filters_by_the_default_threshold() {
    let server = boot_with_cli("stub_search_success.sh", &[]);

    let response = call_tool(&server, 1, "search", json!({"query": "qdrant url"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "a filtered search must succeed: {body}"
    );

    let results: Value =
        serde_json::from_str(tool_text(&body)).expect("the tool result must be a JSON array");
    let results = results.as_array().expect("an array");
    assert_eq!(
        results.len(),
        2,
        "only the 0.95 and 0.5 results clear the 0.46 default: {results:?}"
    );
    assert_eq!(results[0]["chunk_id"], "chunk-001");
    assert_eq!(results[0]["score"], 0.95);
    assert_eq!(results[1]["chunk_id"], "chunk-002");
    assert_eq!(results[1]["score"], 0.5);
    // The CLI's fields survive the round trip.
    assert_eq!(results[0]["source_file"], "docs/config.md");
    assert_eq!(results[0]["page_number"], 1);
    assert_eq!(results[0]["section_label"], "Configuration");
    assert_eq!(
        results[0]["future_field"]["nested"][1], 2,
        "unknown fields are preserved"
    );
}

#[test]
fn explicit_min_score_narrows_the_results() {
    let server = boot_with_cli("stub_search_success.sh", &[]);

    // The spec's scenario: scores 0.95 and 0.5, min_score 0.9 → only 0.95.
    let response = call_tool(
        &server,
        1,
        "search",
        json!({"query": "qdrant url", "min_score": 0.9}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let results: Value =
        serde_json::from_str(tool_text(&body)).expect("the tool result must be a JSON array");
    let results = results.as_array().expect("an array");
    assert_eq!(results.len(), 1, "only 0.95 clears 0.9: {results:?}");
    assert_eq!(results[0]["chunk_id"], "chunk-001");
}

#[test]
fn a_zero_threshold_keeps_every_result() {
    let server = boot_with_cli("stub_search_success.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "search",
        json!({"query": "anything", "min_score": 0.0}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let results: Value =
        serde_json::from_str(tool_text(&body)).expect("the tool result must be a JSON array");
    assert_eq!(
        results.as_array().expect("an array").len(),
        3,
        "all canned results clear a zero threshold: {results}"
    );
}

#[test]
fn empty_result_set_is_a_success_with_an_empty_array() {
    let server = boot_with_cli("stub_search_success.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "search",
        json!({"query": "give me __empty__ results"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        body["result"]["isError"].is_null() || body["result"]["isError"] == false,
        "an empty result set must be a success: {body}"
    );
    assert_eq!(
        tool_text(&body),
        "[]",
        "an empty result set must be an empty JSON array"
    );
}

#[test]
fn cli_failure_maps_to_a_tool_error() {
    let server = boot_with_cli("stub_search_failure.sh", &[]);

    let response = call_tool(&server, 1, "search", json!({"query": "anything"}));
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
        text.contains("exit code 1"),
        "the diagnostics must carry the exit code: {text}"
    );
    assert!(
        text.contains("stub-search-failure: partial stdout before the crash"),
        "the diagnostics must carry the captured stdout: {text}"
    );
    assert!(
        text.contains("SECONDBRAIN_QDRANT_URL unreachable"),
        "the diagnostics must carry the captured stderr: {text}"
    );
}

#[test]
fn garbage_stdout_maps_to_a_tool_error() {
    let server = boot_with_cli("stub_search_garbage.sh", &[]);

    let response = call_tool(&server, 1, "search", json!({"query": "anything"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "unparseable CLI output must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("malformed CLI output"),
        "the error must indicate malformed CLI output: {text}"
    );
}

#[test]
fn hostile_query_passes_through_verbatim() {
    // The argv-echo stub receives the tool's argv and prints each element on
    // its own line; the tool reports the non-JSON output as malformed, and
    // the echoed lines prove the query arrived as one literal element after
    // the `--` separator.
    let server = boot_with_cli("stub_argv.sh", &[]);

    let response = call_tool(
        &server,
        1,
        "search",
        json!({"query": "--top-k 1 && rm -rf /", "top_k": 9, "source": "docs/a.md"}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let text = tool_text(&body);
    assert!(
        text.contains("--\n--top-k 1 && rm -rf /"),
        "the query must reach the CLI as one literal element after `--`: {text}"
    );
    assert!(
        text.contains("\n--top-k\n9\n"),
        "the mapped flag must stay a separate element pair: {text}"
    );
    assert!(
        text.contains("\n--source\ndocs/a.md\n"),
        "optional flags must map to separate elements: {text}"
    );
}

#[test]
fn an_unresolvable_cli_binary_is_a_tool_error_naming_the_variable() {
    let server = RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_CLI_BIN", "/nonexistent/secondbrain-cli"),
    ]);

    // The server itself stays up (the boot handshake already proved the
    // listen announcement); the tool call carries the resolution failure.
    let response = call_tool(&server, 1, "search", json!({"query": "anything"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "a resolution failure must be a tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("SECONDBRAIN_MCP_CLI_BIN"),
        "the error must name the variable: {text}"
    );
    assert!(
        text.contains("/nonexistent/secondbrain-cli"),
        "the error must name the configured value: {text}"
    );
}

/// Optional real-CLI round trip (excluded from the default suite: it needs
/// the actual `secondbrain` CLI entrypoint on the machine and the test
/// Qdrant stack from `revise-compose-test-stack`). Point
/// `SECONDBRAIN_MCP_CLI_BIN` at the CLI entrypoint and run
/// `cargo test -- --ignored` to exercise it.
#[ignore = "requires the real secondbrain CLI and the test Qdrant stack"]
#[test]
fn real_cli_search_round_trip() {
    let bin = std::env::var("SECONDBRAIN_MCP_CLI_BIN")
        .expect("set SECONDBRAIN_MCP_CLI_BIN to the real secondbrain CLI entrypoint");
    let server = RunningServer::boot(&[
        ("SECONDBRAIN_MCP_HTTP_BIND_ADDR", "127.0.0.1:0"),
        ("SECONDBRAIN_MCP_CLI_BIN", &bin),
    ]);

    let response = call_tool(&server, 1, "search", json!({"query": "qdrant"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    let results: Value = serde_json::from_str(tool_text(&body))
        .expect("the tool result must be a JSON array of CLI results");
    assert!(results.is_array());
}
