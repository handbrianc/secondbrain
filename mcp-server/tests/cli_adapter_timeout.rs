//! CLI subprocess deadline: expiry kills the CLI's whole process group
//! (including any child it spawned), returns promptly, and leaves the runner
//! fully usable for the next call.

#![cfg(unix)] // process groups and POSIX signals

#[path = "../src/cli.rs"]
mod cli;

mod common;

use std::path::PathBuf;
use std::time::Duration;

use cli::{CliError, CliOutcome, CliRunner};
use common::fixture_stub;

/// The short deadline under test, standing in for
/// `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`.
const SHORT_TIMEOUT: Duration = Duration::from_millis(500);

/// Builds a runner pointed at a fixture stub with a given deadline.
fn runner_with_timeout(timeout: Duration, name: &str) -> CliRunner {
    let path = fixture_stub(name);
    CliRunner::new(path.to_str().expect("a UTF-8 stub path"), timeout)
        .expect("the stub must resolve")
}

/// A unique scratch directory for the spawner test's pid marker file.
fn scratch_dir(label: &str) -> PathBuf {
    let directory = std::env::temp_dir().join(format!(
        "secondbrain-mcp-cli-timeout-{}-{label}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&directory); // stale leftovers from a crashed run
    std::fs::create_dir_all(&directory).expect("a scratch directory");
    directory
}

/// Whether a process id is alive (`kill(pid, 0)`).
fn process_alive(pid: u32) -> bool {
    let Ok(pid) = libc::pid_t::try_from(pid) else {
        return false;
    };
    // SAFETY: the probe only queries the recorded test child's liveness.
    unsafe { libc::kill(pid, 0) == 0 }
}

#[tokio::test]
async fn sleeper_exceeding_the_deadline_times_out_promptly() {
    let runner = runner_with_timeout(SHORT_TIMEOUT, "stub_sleeper.sh");

    let started = std::time::Instant::now();
    let outcome = runner.run(&["60"], &[]).await;
    let elapsed = started.elapsed();

    match outcome {
        Err(CliError::Timeout { timeout }) => assert_eq!(timeout, SHORT_TIMEOUT),
        other => panic!("the sleeper must be killed at the deadline, got {other:?}"),
    }
    let grace = Duration::from_secs(3);
    assert!(
        elapsed >= SHORT_TIMEOUT && elapsed < SHORT_TIMEOUT + grace,
        "the call must return promptly after the deadline: {elapsed:?}"
    );
}

#[tokio::test]
async fn spawned_background_child_dies_with_the_group() {
    let marker = scratch_dir("spawner-marker").join("child.pid");
    let runner = runner_with_timeout(SHORT_TIMEOUT, "stub_spawner.sh");

    let outcome = runner
        .run(&[marker.to_str().expect("a UTF-8 marker path")], &[])
        .await;
    assert!(
        matches!(outcome, Err(CliError::Timeout { .. })),
        "the spawner must be killed at the deadline: {outcome:?}"
    );

    let child_pid: u32 = std::fs::read_to_string(&marker)
        .expect("the spawner must have written its background child's pid")
        .trim()
        .parse()
        .expect("a pid");

    // The background child must be dead once the group was killed; the
    // corpse is reaped asynchronously after the group kill, so poll briefly.
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    while process_alive(child_pid) {
        if std::time::Instant::now() >= deadline {
            panic!("the spawner's background child survived the group kill (pid {child_pid})");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

#[tokio::test]
async fn a_call_after_a_timeout_still_succeeds() {
    let runner = runner_with_timeout(SHORT_TIMEOUT, "stub_sleeper.sh");

    assert!(
        matches!(
            runner.run(&["60"], &[]).await,
            Err(CliError::Timeout { .. })
        ),
        "the first call must time out"
    );

    // The same runner, past a timeout, must still execute normally.
    match runner.run(&["0"], &[]).await {
        Ok(CliOutcome::Success { stdout, stderr }) => {
            assert_eq!(stdout, "", "an instant sleeper call must succeed cleanly");
            assert_eq!(stderr, "");
        }
        other => panic!("the call after the timeout must succeed, got {other:?}"),
    }
}
