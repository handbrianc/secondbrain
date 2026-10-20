//! CLI adapter core: argv-only spawning, separate stream capture, exit-code
//! mapping, and `SECONDBRAIN_MCP_CLI_BIN` resolution — proven hermetically
//! against shell stubs (no Python or Qdrant required).
//!
//! The crate is a binary, so the module is included directly; it has no
//! crate-internal dependencies.

#![cfg(unix)] // the fixtures are POSIX shell scripts

#[path = "../src/cli.rs"]
mod cli;

mod common;

use cli::{CliError, CliOutcome, CliRunner};
use common::fixture_stub;

/// A generous deadline for the stubs, which finish instantly; the deadline
/// itself is under test in `cli_adapter_timeout.rs`.
const TEST_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

/// Builds a runner pointed at a fixture stub.
fn runner(name: &str) -> CliRunner {
    let path = fixture_stub(name);
    CliRunner::new(path.to_str().expect("a UTF-8 stub path"), TEST_TIMEOUT)
        .expect("the stub must resolve")
}

#[tokio::test]
async fn success_captures_both_streams() {
    let runner = runner("stub_success.sh");

    let outcome = runner
        .run::<&str>(&[], &[])
        .await
        .expect("the stub must run");
    match outcome {
        CliOutcome::Success { stdout, stderr } => {
            assert!(
                stdout.contains("stub-success-stdout line 1")
                    && stdout.contains("stub-success-stdout line 2"),
                "the full stdout must be captured: {stdout:?}"
            );
            assert!(
                stderr.contains("stub-success-stderr"),
                "stderr must be captured separately: {stderr:?}"
            );
        }
        other => panic!("a zero exit must map to success, got {other:?}"),
    }
}

#[tokio::test]
async fn exit_three_carries_code_and_streams() {
    let runner = runner("stub_failure.sh");

    let outcome = runner
        .run::<&str>(&[], &[])
        .await
        .expect("the stub must run");
    match outcome {
        CliOutcome::Exit {
            code,
            stdout,
            stderr,
        } => {
            assert_eq!(
                code, 3,
                "the exit code must be carried: {code}, stdout {stdout:?}, stderr {stderr:?}"
            );
            assert!(
                stdout.contains("stub-failure-stdout"),
                "stdout of a failing run must be captured: {stdout:?}"
            );
            assert!(
                stderr.contains("stub-failure-stderr"),
                "stderr of a failing run must be captured: {stderr:?}"
            );
        }
        other => panic!("exit 3 must map to a structured Exit, got {other:?}"),
    }
}

#[tokio::test]
async fn metacharacters_pass_through_verbatim() {
    let runner = runner("stub_argv.sh");

    let args = ["$(rm -rf /)", "a;b", "`whoami`", "|pipe&", ""];
    let outcome = runner.run(&args, &[]).await.expect("the stub must run");
    match outcome {
        CliOutcome::Success { stdout, .. } => {
            let echoed: Vec<&str> = stdout.lines().collect();
            assert_eq!(
                echoed,
                args.to_vec(),
                "each argument must arrive verbatim as one argv element: {stdout:?}"
            );
        }
        other => panic!("the argv stub must succeed, got {other:?}"),
    }
}

#[test]
fn unresolvable_binary_fails_without_spawning() {
    let error =
        CliRunner::new("/nonexistent/secondbrain-cli", TEST_TIMEOUT).expect_err("must not resolve");
    match &error {
        CliError::Resolve { reason } => {
            assert!(
                reason.contains("`/nonexistent/secondbrain-cli`"),
                "the reason must name the configured value: {reason}"
            );
        }
        other => panic!("resolution failure must be Resolve, got {other:?}"),
    }
    // The fail-fast contract: the message names the variable.
    assert!(
        error.to_string().contains("SECONDBRAIN_MCP_CLI_BIN"),
        "the error must name the variable: {error}"
    );
}
