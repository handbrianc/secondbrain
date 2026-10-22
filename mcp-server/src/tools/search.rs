//! The `search` MCP tool: semantic search by driving the secondbrain CLI's
//! `search --format json` surface through the adapter (`add-mcp-search-tool`).
//!
//! One verified CLI quirk is handled here: the CLI's `--min-score` filtering
//! applies to table output only (`src/secondbrain/cli/display.py`), so the
//! similarity threshold is applied by the server after parsing the JSON.

use std::ffi::OsString;

use rmcp::ErrorData;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::schemars::JsonSchema;
use rmcp::{tool, tool_router};
use serde::{Deserialize, Serialize};

use crate::cli::CliOutcome;
use crate::server::SecondBrainServer;

use super::{MAX_STREAM_CHARS, adapter_error, describe_exit, resolution_error, truncate};

/// The similarity threshold applied server-side when the caller passes none:
/// the CLI's own default (`DEFAULT_MIN_SIMILARITY_THRESHOLD`), mirrored here
/// without touching Python.
const DEFAULT_MIN_SCORE: f64 = 0.46;

/// Input of the `search` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct SearchParams {
    /// The semantic search query text.
    pub query: String,
    /// Maximum number of results to return (the CLI default is 50).
    #[serde(default)]
    pub top_k: Option<u64>,
    /// Only results from this source file path.
    #[serde(default)]
    pub source: Option<String>,
    /// Only results of this file type/category.
    #[serde(default)]
    pub file_type: Option<String>,
    /// Minimum similarity score, applied by the server (default 0.46; the
    /// CLI's JSON output is not threshold-filtered).
    #[serde(default)]
    pub min_score: Option<f64>,
}

/// One CLI search result, as emitted by `search --format json`.
///
/// Only `score` is read by the server (for the threshold); every other field
/// the CLI includes is preserved verbatim through the parse/re-serialize
/// round trip.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct SearchResult {
    /// The similarity score the threshold filters on (0 when the CLI omits
    /// it, mirroring the CLI's own display filter).
    #[serde(default)]
    pub score: f64,
    /// Every remaining CLI field, preserved as-is.
    #[serde(flatten)]
    pub rest: serde_json::Map<String, serde_json::Value>,
}

/// Registers the `search` tool on the shared server.
#[tool_router(router = search_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Semantic search over the ingested knowledge base.
    #[tool(
        description = "Semantic search over the secondbrain knowledge base. Returns \
                       the matching chunks as a JSON array (fields include chunk_id, \
                       source_file, page_number, chunk_text, score), filtered by the \
                       server to a minimum similarity score (default 0.46)."
    )]
    async fn search(
        &self,
        Parameters(params): Parameters<SearchParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run(&self.cli, params).await
    }
}

/// Runs one search: build the argv, drive the CLI, filter by the threshold,
/// and map every outcome onto a tool result.
pub(crate) async fn run(
    cli: &Result<crate::cli::CliRunner, String>,
    params: SearchParams,
) -> Result<CallToolResult, ErrorData> {
    let runner = match cli {
        Ok(runner) => runner,
        Err(message) => return Ok(resolution_error(message)),
    };

    match runner.run(&search_argv(&params), &[]).await {
        Ok(CliOutcome::Success { stdout, .. }) => match threshold_filter(&stdout, params.min_score)
        {
            Ok(json) => Ok(CallToolResult::success(vec![ContentBlock::text(json)])),
            Err(message) => Ok(CallToolResult::error(vec![ContentBlock::text(message)])),
        },
        Ok(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => Ok(CallToolResult::error(vec![ContentBlock::text(
            describe_exit(code, &stdout, &stderr),
        )])),
        Err(error) => Ok(adapter_error(&error)),
    }
}

/// Builds the CLI argv: `search --format json [--top-k N] [--source S]
/// [--file-type T] -- <query>`.
///
/// The `--` separator puts the query after the options, so flag-like query
/// text can never be parsed as a CLI flag; the adapter passes every element
/// verbatim (no shell).
fn search_argv(params: &SearchParams) -> Vec<OsString> {
    let mut argv = vec![
        OsString::from("search"),
        OsString::from("--format"),
        OsString::from("json"),
    ];
    if let Some(top_k) = params.top_k {
        argv.push(OsString::from("--top-k"));
        argv.push(OsString::from(top_k.to_string()));
    }
    if let Some(source) = &params.source {
        argv.push(OsString::from("--source"));
        argv.push(OsString::from(source));
    }
    if let Some(file_type) = &params.file_type {
        argv.push(OsString::from("--file-type"));
        argv.push(OsString::from(file_type));
    }
    argv.push(OsString::from("--"));
    argv.push(OsString::from(&params.query));
    argv
}

/// Parses the CLI's JSON array, keeps the results scoring at or above the
/// threshold (inclusive), and re-serializes compactly.
fn threshold_filter(stdout: &str, min_score: Option<f64>) -> Result<String, String> {
    let min_score = min_score.unwrap_or(DEFAULT_MIN_SCORE);
    let results: Vec<SearchResult> = serde_json::from_str(stdout).map_err(|error| {
        // The bounded stdout preview is part of the contract: it lets a
        // caller (and the tests) see what the CLI actually emitted.
        format!(
            "malformed CLI output: {error}\n--- stdout ---\n{}",
            truncate(stdout, MAX_STREAM_CHARS)
        )
    })?;
    let kept: Vec<&SearchResult> = results
        .iter()
        .filter(|result| result.score >= min_score)
        .collect();
    Ok(serde_json::to_string(&kept).expect("re-serializing parsed results must succeed"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    /// Builds params with every knob settable.
    fn params(
        query: &str,
        top_k: Option<u64>,
        source: Option<&str>,
        file_type: Option<&str>,
        min_score: Option<f64>,
    ) -> SearchParams {
        SearchParams {
            query: query.to_string(),
            top_k,
            source: source.map(str::to_string),
            file_type: file_type.map(str::to_string),
            min_score,
        }
    }

    #[test]
    fn argv_covers_every_flag_combination() {
        for with_top_k in [false, true] {
            for with_source in [false, true] {
                for with_file_type in [false, true] {
                    let argv = search_argv(&params(
                        "the query",
                        with_top_k.then_some(7),
                        with_source.then_some("docs/a.md"),
                        with_file_type.then_some("markdown"),
                        None,
                    ));
                    let strings: Vec<String> = argv
                        .iter()
                        .map(|argument| argument.to_string_lossy().into_owned())
                        .collect();

                    assert_eq!(strings[0], "search");
                    assert_eq!(strings[1], "--format");
                    assert_eq!(strings[2], "json");

                    let mut rest = strings[3..].to_vec();
                    let query = rest.pop().expect("the query is the last element");
                    let separator = rest.pop().expect("the separator precedes the query");
                    assert_eq!(separator, "--", "the query must follow a -- separator");
                    assert_eq!(query, "the query");

                    let mut flags = rest.into_iter();
                    if with_top_k {
                        assert_eq!(flags.next().as_deref(), Some("--top-k"));
                        assert_eq!(flags.next().as_deref(), Some("7"));
                    }
                    if with_source {
                        assert_eq!(flags.next().as_deref(), Some("--source"));
                        assert_eq!(flags.next().as_deref(), Some("docs/a.md"));
                    }
                    if with_file_type {
                        assert_eq!(flags.next().as_deref(), Some("--file-type"));
                        assert_eq!(flags.next().as_deref(), Some("markdown"));
                    }
                    let leftover: Vec<String> = flags.collect();
                    assert!(
                        leftover.is_empty(),
                        "no unexpected flags may remain: {leftover:?}"
                    );
                }
            }
        }
    }

    #[test]
    fn hostile_query_is_one_literal_argv_element() {
        let argv = search_argv(&params("--top-k 1 && rm -rf /", None, None, None, None));
        let last = argv.last().expect("the query is the last element");
        assert_eq!(
            last, "--top-k 1 && rm -rf /",
            "the query must stay a single verbatim element"
        );
        assert_eq!(
            argv[argv.len() - 2],
            "--",
            "the query must follow the -- separator"
        );
    }

    #[test]
    fn threshold_is_inclusive_and_filters_below() {
        let stdout = r#"[{"chunk_id":"a","score":0.46},{"chunk_id":"b","score":0.4599}]"#;
        let filtered: Value =
            serde_json::from_str(&threshold_filter(stdout, Some(0.46)).expect("must filter"))
                .expect("the filtered text must be JSON");
        let kept = filtered.as_array().expect("an array");
        assert_eq!(kept.len(), 1, "the boundary score is kept: {filtered}");
        assert_eq!(kept[0]["chunk_id"], "a");
        assert_eq!(kept[0]["score"], 0.46);
    }

    #[test]
    fn default_threshold_applies_when_none() {
        let stdout = r#"[{"chunk_id":"a","score":0.95},{"chunk_id":"b","score":0.5},{"chunk_id":"c","score":0.3}]"#;
        let filtered: Value =
            serde_json::from_str(&threshold_filter(stdout, None).expect("must filter"))
                .expect("the filtered text must be JSON");
        let ids: Vec<&str> = filtered
            .as_array()
            .expect("an array")
            .iter()
            .map(|result| result["chunk_id"].as_str().expect("an id"))
            .collect();
        assert_eq!(ids, ["a", "b"], "0.3 must fall under the 0.46 default");
    }

    #[test]
    fn empty_array_passes_through() {
        assert_eq!(threshold_filter("[]", None).expect("must filter"), "[]");
    }

    #[test]
    fn missing_score_is_treated_as_zero() {
        // Mirrors the CLI's own display filter (`r.get("score", 0)`): an
        // item without a score cannot pass a positive threshold.
        let stdout = r#"[{"chunk_id":"x"},{"chunk_id":"y","score":0.0}]"#;
        let filtered: Value =
            serde_json::from_str(&threshold_filter(stdout, None).expect("must filter"))
                .expect("the filtered text must be JSON");
        assert_eq!(
            filtered.as_array().expect("an array").len(),
            0,
            "both must fall under the default threshold"
        );
        let kept: Value =
            serde_json::from_str(&threshold_filter(stdout, Some(0.0)).expect("must filter"))
                .expect("the filtered text must be JSON");
        assert_eq!(
            kept.as_array().expect("an array").len(),
            2,
            "a zero threshold keeps both"
        );
    }

    #[test]
    fn fields_are_preserved_through_the_round_trip() {
        let stdout = r#"[
            {"chunk_id":"chunk-001","source_file":"docs/config.md","page_number":1,
             "printed_page":"1","page_pos":0,"chunk_text":"The Qdrant URL.",
             "element_type":"paragraph","chunk_role":"body","section_label":"Config",
             "score":0.95,"future_field":{"nested":[1,2]}}
        ]"#;
        let filtered: Value =
            serde_json::from_str(&threshold_filter(stdout, Some(0.9)).expect("must filter"))
                .expect("the filtered text must be JSON");
        let result = &filtered.as_array().expect("an array")[0];
        assert_eq!(result["chunk_id"], "chunk-001");
        assert_eq!(result["source_file"], "docs/config.md");
        assert_eq!(result["page_number"], 1, "integers stay integers");
        assert_eq!(result["printed_page"], "1");
        assert_eq!(result["page_pos"], 0);
        assert_eq!(result["chunk_text"], "The Qdrant URL.");
        assert_eq!(result["element_type"], "paragraph");
        assert_eq!(result["chunk_role"], "body");
        assert_eq!(result["section_label"], "Config");
        assert_eq!(result["score"], 0.95);
        assert_eq!(
            result["future_field"]["nested"],
            serde_json::json!([1, 2]),
            "unknown fields are preserved verbatim"
        );
    }

    #[test]
    fn malformed_stdout_maps_to_an_error_not_a_panic() {
        let error =
            threshold_filter("Ceci n'est pas du JSON", None).expect_err("garbage must not parse");
        assert!(
            error.contains("malformed CLI output"),
            "the error must say the CLI output was malformed: {error}"
        );

        let error =
            threshold_filter(r#"{"not":"an array"}"#, None).expect_err("objects must not parse");
        assert!(
            error.contains("malformed CLI output"),
            "a non-array payload must be malformed: {error}"
        );
    }
}
