//! CLI environment contract: subprocesses inherit the server's full
//! environment, per-call overrides apply on top of it, and nothing leaks
//! into subsequent calls.

#![cfg(unix)] // the fixtures are POSIX shell scripts

#[path = "../src/cli.rs"]
mod cli;

mod common;

use cli::{CliOutcome, CliRunner};
use common::fixture_stub;

/// A generous deadline for the stubs, which finish instantly; the deadline
/// itself is under test in `cli_adapter_timeout.rs`.
const TEST_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);

/// Builds a runner pointed at the env probe stub.
fn runner() -> CliRunner {
    let path = fixture_stub("stub_env.sh");
    CliRunner::new(path.to_str().expect("a UTF-8 stub path"), TEST_TIMEOUT)
        .expect("the stub must resolve")
}

/// Runs the stub with the given probe variable names and returns its stdout.
async fn probe(runner: &CliRunner, names: &[&str], overrides: &[(String, String)]) -> String {
    match runner
        .run(names, overrides)
        .await
        .expect("the stub must run")
    {
        CliOutcome::Success { stdout, .. } => stdout,
        other => panic!("the env stub must succeed, got {other:?}"),
    }
}

#[tokio::test]
async fn inherited_environment_reaches_the_child() {
    // SAFETY: one test-scoped mutation of the process environment under a
    // name unique to this test; the value must be inherited by the child.
    unsafe { std::env::set_var("SECONDBRAIN_TEST_INHERITED_PROBE", "inherited-value") };

    let runner = runner();
    let stdout = probe(&runner, &["SECONDBRAIN_TEST_INHERITED_PROBE"], &[]).await;
    assert!(
        stdout.contains("SECONDBRAIN_TEST_INHERITED_PROBE=inherited-value"),
        "the child must observe the server's inherited environment: {stdout:?}"
    );
}

#[tokio::test]
async fn per_call_override_reaches_the_child() {
    let runner = runner();
    let stdout = probe(
        &runner,
        &["SECONDBRAIN_SHOW_THINKING"],
        &[("SECONDBRAIN_SHOW_THINKING".to_string(), "0".to_string())],
    )
    .await;
    assert!(
        stdout.contains("SECONDBRAIN_SHOW_THINKING=0"),
        "the child must observe the per-call override: {stdout:?}"
    );
}

#[tokio::test]
async fn override_wins_over_an_inherited_value() {
    // SAFETY: one test-scoped mutation of the process environment under a
    // name unique to this test; the inherited value must lose to the
    // per-call override.
    unsafe { std::env::set_var("SECONDBRAIN_TEST_OVERRIDE_PROBE", "inherited") };

    let runner = runner();
    let stdout = probe(
        &runner,
        &["SECONDBRAIN_TEST_OVERRIDE_PROBE"],
        &[(
            "SECONDBRAIN_TEST_OVERRIDE_PROBE".to_string(),
            "override".to_string(),
        )],
    )
    .await;
    assert!(
        stdout.contains("SECONDBRAIN_TEST_OVERRIDE_PROBE=override"),
        "the override must win over the inherited value: {stdout:?}"
    );
}

#[tokio::test]
async fn override_does_not_leak_into_the_next_call() {
    let runner = runner();

    let first = probe(
        &runner,
        &["SECONDBRAIN_TEST_LEAK_PROBE"],
        &[("SECONDBRAIN_TEST_LEAK_PROBE".to_string(), "1".to_string())],
    )
    .await;
    assert!(
        first.contains("SECONDBRAIN_TEST_LEAK_PROBE=1"),
        "the override must apply to its own call: {first:?}"
    );

    let second = probe(&runner, &["SECONDBRAIN_TEST_LEAK_PROBE"], &[]).await;
    assert!(
        second.contains("SECONDBRAIN_TEST_LEAK_PROBE=<unset>"),
        "the next call must observe the inherited state, not the override: {second:?}"
    );
}
