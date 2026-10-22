//! The asynchronous ingest/upload jobs and the `job_status` tool over the
//! full HTTP surface (`add-mcp-async-ingestion`): the start response returns
//! a job id instead of the CLI result, polling reaches the sync-equivalent
//! text, the upload's delete-after-ingest disposition matches the sync
//! contract, invalid async calls fail immediately and create no job, and the
//! unknown-id diagnostic is an error that explains the in-memory registry —
//! against a stub CLI and a per-test workspace copy, so no Python, Qdrant,
//! or fixture writes are involved.

mod common;

use common::{
    RunningServer, WorkspaceCopy, boot_with_workspace, call_tool, fixture_upload, json_body,
    post_mcp, sample_upload_base64, tool_text,
};
use serde_json::json;
use std::thread;
use std::time::{Duration, Instant};

/// How long one poll loop waits for a job to reach a terminal state before
/// the test fails with the last polled text.
const POLL_DEADLINE: Duration = Duration::from_secs(10);

/// The pause between two `job_status` polls.
const POLL_INTERVAL: Duration = Duration::from_millis(50);

/// Whether a tools/call result is a success (`isError` absent or false).
fn is_success(body: &serde_json::Value) -> bool {
    body["result"]["isError"].is_null() || body["result"]["isError"] == false
}

/// Extracts the `job-<n>` id from an async start response text.
fn extract_job_id(text: &str) -> String {
    let from = text
        .find("job-")
        .unwrap_or_else(|| panic!("the start text must carry a job-<n> id: {text}"));
    let mut id = String::from("job-");
    for character in text[from + 4..].chars() {
        if character.is_ascii_digit() {
            id.push(character);
        } else {
            break;
        }
    }
    assert!(id.len() > 4, "the start text must carry a job id: {text}");
    id
}

/// Polls `job_status` for one job and returns the status text. The poll is
/// always a success result (the job's failure lives in the text), so only
/// the HTTP and result shapes are asserted here.
fn poll_once(server: &RunningServer, job_id: &str, id: i64) -> String {
    let response = call_tool(server, id, "job_status", json!({"job_id": job_id}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        is_success(&body),
        "a poll for a known id must never fail while the job is live: {body}"
    );
    tool_text(&body).to_string()
}

/// Polls `job_status` for one job until it reaches a terminal state
/// (`[completed]` or `[failed]` in the status text), with a small sleep
/// between polls, and returns the final status text. Fails the test on the
/// deadline with the last polled text.
fn poll_until_terminal(server: &RunningServer, job_id: &str) -> String {
    let deadline = Instant::now() + POLL_DEADLINE;
    let mut sequence = 0;
    loop {
        let text = poll_once(server, job_id, 100 + sequence);
        if text.contains("[completed]") || text.contains("[failed]") {
            return text;
        }
        assert!(
            Instant::now() < deadline,
            "job {job_id} did not reach a terminal state in time; last poll: {text}"
        );
        thread::sleep(POLL_INTERVAL);
        sequence += 1;
    }
}

#[test]
fn tools_list_declares_job_status_and_the_async_mode_knobs() {
    let workspace = WorkspaceCopy::new("jobs-discovery");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = post_mcp(
        &server,
        json!({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let tools = json_body(&response)["result"]["tools"]
        .as_array()
        .expect("a tools array")
        .clone();

    let job_status = tools
        .iter()
        .find(|tool| tool["name"] == "job_status")
        .expect("the registry must contain job_status")
        .clone();
    let description = job_status["description"].as_str().expect("a description");
    assert!(
        description.contains("async_mode=true"),
        "the description must point at the async start tools: {description}"
    );
    let schema = &job_status["inputSchema"];
    assert!(
        schema["properties"]
            .as_object()
            .expect("the input schema must declare properties")
            .contains_key("job_id"),
        "the input schema must declare job_id: {schema}"
    );
    // `job_id` must be optional: the no-argument listing is the tool's
    // other half.
    let required = schema["required"].as_array().map(|r| r.len()).unwrap_or(0);
    assert_eq!(required, 0, "job_id must be optional: {schema}");

    for name in ["ingest_documents", "upload_document"] {
        let tool = tools
            .iter()
            .find(|tool| tool["name"] == name)
            .unwrap_or_else(|| panic!("the registry must contain {name}"))
            .clone();
        let properties = tool["inputSchema"]["properties"]
            .as_object()
            .expect("the input schema must declare properties");
        assert!(
            properties.contains_key("async_mode"),
            "{name} must declare async_mode: {properties:?}"
        );
        let description = tool["description"].as_str().expect("a description");
        assert!(
            description.contains("async_mode to start a background job and poll job_status"),
            "{name}'s description must point at the async mode: {description}"
        );
    }
}

#[test]
fn an_async_ingest_returns_a_job_id_and_polls_to_the_ingest_summary() {
    let workspace = WorkspaceCopy::new("jobs-ingest");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "report.txt", "async_mode": true}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        is_success(&body),
        "a valid async start must succeed: {body}"
    );

    let start_text = tool_text(&body);
    assert!(
        start_text.contains("Started ingest job job-1: ingest report.txt"),
        "{start_text}"
    );
    assert!(
        start_text.contains("{\"job_id\": \"job-1\"}"),
        "the start text must carry the polling instruction: {start_text}"
    );
    assert!(
        !start_text.contains("ingest summary"),
        "the start response must not carry the ingest summary: {start_text}"
    );
    let job_id = extract_job_id(start_text);

    let final_text = poll_until_terminal(&server, &job_id);
    assert!(
        final_text.contains("[completed]"),
        "a successful stub ingest must complete the job: {final_text}"
    );
    assert!(
        final_text.contains("ingest summary (from the secondbrain CLI)"),
        "the terminal text must carry the sync-equivalent summary: {final_text}"
    );
    assert!(
        final_text.contains("1 documents, 3 chunks"),
        "the CLI's summary must be carried: {final_text}"
    );

    // The no-argument listing shows the finished job too, one line, oldest
    // first.
    let listing = call_tool(&server, 2, "job_status", json!({}));
    assert_eq!(listing.status, 200, "{listing:?}");
    let listing_body = json_body(&listing);
    assert!(is_success(&listing_body), "{listing_body}");
    let listed = tool_text(&listing_body);
    assert!(
        listed.contains(&format!("[completed] {job_id} kind=ingest elapsed=")),
        "the listing must carry the finished job: {listed}"
    );
    assert!(
        listed.lines().count() == 1 && listed.ends_with("ingest report.txt"),
        "the listing line must end with the job summary: {listed}"
    );
}

#[test]
fn an_async_ingest_with_an_escaping_path_fails_immediately_and_creates_no_job() {
    let workspace = WorkspaceCopy::new("jobs-escape");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = call_tool(
        &server,
        1,
        "ingest_documents",
        json!({"path": "../outside.txt", "async_mode": true}),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "the escape must be an immediate tool error: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("escapes the workspace") && text.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
        "the rejection must name the rule and the variable, like the sync call: {text}"
    );
    assert!(
        !text.contains("Started ingest job"),
        "a rejected call must create no job: {text}"
    );

    // And the registry stays empty: the no-argument listing reports no jobs.
    let listing = call_tool(&server, 2, "job_status", json!({}));
    assert_eq!(listing.status, 200, "{listing:?}");
    let listing_body = json_body(&listing);
    assert!(is_success(&listing_body), "{listing_body}");
    assert_eq!(
        tool_text(&listing_body),
        "No jobs have been started since the server started.",
        "an immediately-rejected call must leave no job behind"
    );
}

#[test]
fn an_async_upload_polls_to_the_disposition_and_deletes_the_staged_file() {
    let workspace = WorkspaceCopy::new("jobs-upload");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let decoded_len = std::fs::read(fixture_upload("sample-document.txt"))
        .expect("the fixture must read")
        .len();
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "sample.txt",
            "content_base64": sample_upload_base64(),
            "async_mode": true
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(
        is_success(&body),
        "a valid async upload start must succeed: {body}"
    );

    let start_text = tool_text(&body);
    let expected_start =
        format!("Started upload job job-1: upload sample.txt ({decoded_len} bytes decoded)");
    assert!(
        start_text.contains(&expected_start),
        "the start text must carry the job id, filename, and decoded size: {start_text}"
    );
    assert!(
        !start_text.contains("ingest summary"),
        "the start response must not carry the ingest summary: {start_text}"
    );
    let job_id = extract_job_id(start_text);

    let final_text = poll_until_terminal(&server, &job_id);
    assert!(
        final_text.contains("[completed]"),
        "a successful stub ingest must complete the job: {final_text}"
    );
    assert!(
        final_text.contains("stored at uploads/sample.txt (relative to the workspace root)"),
        "the recorded text must carry the stored path, like the sync call: {final_text}"
    );
    assert!(
        final_text.contains("the staged file was deleted after the successful ingest"),
        "the recorded text must carry the disposition sentence: {final_text}"
    );
    assert!(
        final_text.contains("ingest summary (from the secondbrain CLI)"),
        "the recorded text must carry the CLI summary: {final_text}"
    );

    // Disposition parity with the sync contract: the staged file is gone.
    assert!(
        !workspace.upload_dir().join("sample.txt").exists(),
        "a successful async ingest must delete the staged file"
    );
}

#[test]
fn an_async_upload_with_a_failing_ingest_keeps_the_staged_file() {
    let workspace = WorkspaceCopy::new("jobs-upload-failure");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    // The stub fails on BOOM.txt by name, like the real CLI failing on an
    // unsupported extension or an unreachable Qdrant: the file is already
    // stored when the job's CLI runs.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "BOOM.txt",
            "content_base64": sample_upload_base64(),
            "async_mode": true
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(is_success(&body), "the start itself must succeed: {body}");
    let job_id = extract_job_id(tool_text(&body));

    let final_text = poll_until_terminal(&server, &job_id);
    assert!(
        final_text.contains("[failed]"),
        "a failed ingest must fail the job, in the status text: {final_text}"
    );
    assert!(
        final_text
            .contains("the document was stored at uploads/BOOM.txt, but its ingestion failed"),
        "the recorded text must carry the stored path and the sync-equivalent wording: {final_text}"
    );
    assert!(
        final_text.contains("exit code 1") && final_text.contains("exploded"),
        "the recorded text must carry the CLI's captured output: {final_text}"
    );

    // The staged file remains in place, holding the uploaded bytes, for a
    // later re-ingest — the failed-ingest contract, unchanged in async mode.
    let stored = workspace.upload_dir().join("BOOM.txt");
    assert!(stored.is_file(), "a failed async ingest must keep the file");
    assert_eq!(
        std::fs::read(&stored).expect("the stored file must read"),
        std::fs::read(fixture_upload("sample-document.txt")).expect("the fixture must read"),
        "the retained file must hold the uploaded bytes"
    );
}

#[test]
fn an_async_upload_with_a_failing_deletion_completes_with_the_failure_sentence() {
    let workspace = WorkspaceCopy::new("jobs-upload-delete-blocked");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    // The stub replaces STUCK.txt with a same-named directory before
    // exiting 0: the job's post-ingest cleanup then fails deterministically
    // (remove_file refuses directories), exercising the delete-failure path
    // end to end.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "STUCK.txt",
            "content_base64": sample_upload_base64(),
            "async_mode": true
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(is_success(&body), "the start itself must succeed: {body}");
    let job_id = extract_job_id(tool_text(&body));

    let final_text = poll_until_terminal(&server, &job_id);
    assert!(
        final_text.contains("[completed]"),
        "a failed deletion must not fail an ingested upload: {final_text}"
    );
    assert!(
        final_text.contains("stored at uploads/STUCK.txt"),
        "the recorded text must carry the stored path: {final_text}"
    );
    assert!(
        final_text.contains("deleting the staged file after the successful ingest failed"),
        "the recorded text must report the failed deletion, like the sync call: {final_text}"
    );
    assert!(
        final_text.contains("the file remains in place"),
        "the recorded text must say the staged file stays: {final_text}"
    );
    assert!(
        final_text.contains("ingest summary (from the secondbrain CLI)"),
        "the CLI summary must still be carried: {final_text}"
    );
    assert!(
        workspace.upload_dir().join("STUCK.txt").is_dir(),
        "the unremovable staged path must remain in place"
    );
}

#[test]
fn an_async_upload_of_a_slow_file_is_observable_as_running() {
    let workspace = WorkspaceCopy::new("jobs-slow");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    // The stub sleeps ~2s for a SLOW filename, so the job's CLI run is
    // typically still executing when the first poll lands.
    let response = call_tool(
        &server,
        1,
        "upload_document",
        json!({
            "filename": "SLOW.txt",
            "content_base64": sample_upload_base64(),
            "async_mode": true
        }),
    );
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert!(is_success(&body), "the start itself must succeed: {body}");
    let start_text = tool_text(&body);
    assert!(
        start_text.contains("Started upload job job-1: upload SLOW.txt"),
        "{start_text}"
    );
    assert!(
        !start_text.contains("ingest summary"),
        "the start response must not carry the ingest summary: {start_text}"
    );
    let job_id = extract_job_id(start_text);

    // First poll: [running] with the summary and the polling instruction,
    // or — on a fast machine that raced the 2s stub sleep — already
    // terminal. Either way the start response above carried no result.
    let first = poll_once(&server, &job_id, 2);
    if first.contains("[running]") {
        assert!(
            first.contains(&format!("Job {job_id} [running] kind=upload elapsed=")),
            "the running status carries id, state, kind, elapsed: {first}"
        );
        assert!(
            first.contains("upload SLOW.txt"),
            "the running status carries the summary: {first}"
        );
        assert!(
            first.contains("Poll again with job_status to check completion."),
            "{first}"
        );
        assert!(
            !first.contains("ingest summary"),
            "a running job must not carry the result: {first}"
        );
    } else {
        assert!(
            first.contains("[completed]"),
            "the first poll is either running or terminal: {first}"
        );
    }

    let final_text = poll_until_terminal(&server, &job_id);
    assert!(final_text.contains("[completed]"), "{final_text}");
    assert!(
        final_text.contains("the staged file was deleted after the successful ingest"),
        "{final_text}"
    );
    assert!(
        !workspace.upload_dir().join("SLOW.txt").exists(),
        "a successful async ingest deletes the staged file"
    );
}

#[test]
fn job_status_reports_an_unknown_id_and_lists_known_jobs() {
    let workspace = WorkspaceCopy::new("jobs-unknown");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

    let response = call_tool(&server, 1, "job_status", json!({"job_id": "job-99"}));
    assert_eq!(response.status, 200, "{response:?}");
    let body = json_body(&response);
    assert_eq!(
        body["result"]["isError"], true,
        "an unknown id must be an error result: {body}"
    );
    let text = tool_text(&body);
    assert!(
        text.contains("Unknown job id: job-99"),
        "the error must name the id: {text}"
    );
    assert!(
        text.contains("server memory") && text.contains("restart"),
        "the error must explain the in-memory registry: {text}"
    );
    assert!(
        text.contains("job_status without arguments"),
        "the error must point at the listing: {text}"
    );

    // A fresh process lists nothing.
    let listing = call_tool(&server, 2, "job_status", json!({}));
    assert_eq!(listing.status, 200, "{listing:?}");
    let listing_body = json_body(&listing);
    assert!(is_success(&listing_body), "{listing_body}");
    assert_eq!(
        tool_text(&listing_body),
        "No jobs have been started since the server started.",
        "a fresh registry lists no jobs"
    );
}

#[test]
fn a_sync_upload_call_behaves_as_before_when_async_mode_is_absent() {
    // The sync contract is asserted in depth by the existing suites
    // (tests/tools_upload.rs et al.); this one guards the same call shape
    // inside the jobs suite, so the two live side by side.
    let workspace = WorkspaceCopy::new("jobs-sync-unchanged");
    let server = boot_with_workspace("stub_ingest_upload.sh", &workspace.workspace, &[]);

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
    assert!(is_success(&body), "{body}");
    assert!(
        tool_text(&body).contains("ingest summary (from the secondbrain CLI)"),
        "without async_mode the call waits for the run and carries the summary: {body}"
    );
    assert!(
        !workspace.upload_dir().join("sample.txt").exists(),
        "the sync disposition deletes the staged file"
    );

    // And no job was created: the sync call never enters the registry.
    let listing = call_tool(&server, 2, "job_status", json!({}));
    assert_eq!(
        tool_text(&json_body(&listing)),
        "No jobs have been started since the server started.",
        "a synchronous call must leave no job behind"
    );
}
