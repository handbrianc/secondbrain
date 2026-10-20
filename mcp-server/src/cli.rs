//! Subprocess execution of the secondbrain CLI (`add-mcp-cli-adapter`).
//!
//! Every MCP tool drives the Python CLI through this layer: the binary is
//! resolved once from `SECONDBRAIN_MCP_CLI_BIN`, spawned with an argv vector
//! (never a shell), and its stdout/stderr are captured separately and mapped
//! onto a structured outcome. Subprocesses inherit the server's full
//! environment, with per-call overrides applied on top
//! (`add-mcp-cli-env-passthrough`). Every call is bounded by
//! `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS` (`add-mcp-cli-timeout`): on
//! expiry the CLI's whole process group is killed, so the process pools it
//! spawns for ingestion die with it.

use std::ffi::OsStr;
use std::io;
use std::path::PathBuf;
use std::process::{ExitStatus, Stdio};
use std::time::Duration;

use thiserror::Error;
use tokio::io::AsyncReadExt;
use tokio::process::Command;

/// The structured outcome of a CLI run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CliOutcome {
    /// The CLI exited 0.
    Success {
        /// Everything the CLI wrote to stdout.
        stdout: String,
        /// Everything the CLI wrote to stderr (its logging channel).
        stderr: String,
    },
    /// The CLI exited non-zero; a structured failure, not a panic.
    Exit {
        /// The exit status code (a signal death maps to `-1`).
        code: i32,
        /// Everything the CLI wrote to stdout.
        stdout: String,
        /// Everything the CLI wrote to stderr.
        stderr: String,
    },
}

/// A failure of the adapter itself: resolution or spawning.
///
/// Tool invocations that ran and exited non-zero are [`CliOutcome::Exit`],
/// not errors.
#[derive(Debug, Error)]
pub enum CliError {
    /// `SECONDBRAIN_MCP_CLI_BIN` could not be resolved to an executable.
    #[error("SECONDBRAIN_MCP_CLI_BIN: {reason}")]
    Resolve {
        /// Why the value was rejected.
        reason: String,
    },
    /// The resolved binary could not be spawned (e.g. vanished or lost its
    /// execute bit after startup resolution).
    #[error("cannot spawn the CLI from SECONDBRAIN_MCP_CLI_BIN ({binary:?}): {source}")]
    Spawn {
        /// The resolved binary path that failed to spawn.
        binary: PathBuf,
        /// The underlying spawn error.
        source: io::Error,
    },
    /// The call exceeded the configured deadline
    /// (`SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`); the CLI's process
    /// group was killed. Any partial output is discarded — the error carries
    /// no streams, so half-captured data cannot be mistaken for a result.
    #[error(
        "SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS: the CLI did not finish within {timeout:?}"
    )]
    Timeout {
        /// The deadline that was enforced.
        timeout: Duration,
    },
}

/// Executes the secondbrain CLI as a subprocess on behalf of the tools.
#[derive(Clone, Debug)]
pub struct CliRunner {
    /// The resolved CLI binary path.
    binary: PathBuf,
    /// The per-call deadline from `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`.
    timeout: Duration,
}

impl CliRunner {
    /// Resolves the configured CLI binary — an absolute path (or any path
    /// containing a separator, relative to the server's working directory),
    /// or an executable found on `PATH` — and stores the per-call deadline
    /// from `SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS`. Called once; every
    /// tool call reuses the resolved path and deadline.
    pub fn new(cli_bin: &str, timeout: Duration) -> Result<Self, CliError> {
        Ok(Self {
            binary: resolve(cli_bin)?,
            timeout,
        })
    }

    /// Runs the CLI with `args` and captures the structured outcome.
    ///
    /// Spawning uses the argv vector only — no shell is involved, so any
    /// argument passes through verbatim as a single element. stdout and
    /// stderr are captured separately; the working directory and the server's
    /// full environment are inherited, with `overrides` applied per call on
    /// top (no global mutation, no leakage into subsequent calls).
    ///
    /// The call is bounded by the configured deadline: if the CLI (or anything
    /// it spawned) is still running on expiry, the CLI's whole process group
    /// is killed and [`CliError::Timeout`] is returned; any partial output is
    /// discarded.
    pub async fn run<S: AsRef<OsStr>>(
        &self,
        args: &[S],
        overrides: &[(String, String)],
    ) -> Result<CliOutcome, CliError> {
        let mut command = Command::new(&self.binary);
        // argv only: no shell ever sees these bytes.
        command.args(args);
        command
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        // The child leads its own POSIX process group, so the deadline can
        // tear down everything it spawned, not just the direct child.
        #[cfg(unix)]
        command.process_group(0);
        // A run whose driving future is dropped is torn down with it
        // (`add-mcp-async-ingestion`): a detached job's CLI run is killed
        // when the server process exits (its Tokio runtime drops the job
        // tasks — the registry-lifecycle contract, "a CLI run detached at
        // restart time has been terminated with the process"), and a
        // synchronous call whose request is cancelled no longer leaves an
        // orphaned CLI running on.
        command.kill_on_drop(true);
        apply_overrides(&mut command, overrides);

        let mut child = command.spawn().map_err(|source| CliError::Spawn {
            binary: self.binary.clone(),
            source,
        })?;
        let pid = child.id();

        // The pipes are drained concurrently with the wait (a CLI writing
        // more than the pipe buffer must not deadlock against the wait), all
        // under one deadline.
        let mut stdout_bytes = Vec::new();
        let mut stderr_bytes = Vec::new();
        let mut stdout = child.stdout.take().expect("stdout was piped");
        let mut stderr = child.stderr.take().expect("stderr was piped");
        let drained = async {
            let (out_read, err_read, status) = tokio::join!(
                stdout.read_to_end(&mut stdout_bytes),
                stderr.read_to_end(&mut stderr_bytes),
                child.wait(),
            );
            out_read?;
            err_read?;
            status
        };

        match tokio::time::timeout(self.timeout, drained).await {
            Ok(Ok(status)) => {
                let stdout = decode(std::mem::take(&mut stdout_bytes));
                let stderr = decode(std::mem::take(&mut stderr_bytes));
                Ok(map_outcome(&status, stdout, stderr))
            }
            Ok(Err(source)) => {
                // An I/O failure while draining: tear the group down
                // best-effort so a half-dead CLI cannot linger, then surface
                // the spawn error.
                teardown(&pid, &mut child).await;
                Err(CliError::Spawn {
                    binary: self.binary.clone(),
                    source,
                })
            }
            Err(_elapsed) => {
                // Deadline exceeded: kill the CLI's entire process group and
                // reap the direct child. The partial streams are discarded.
                teardown(&pid, &mut child).await;
                Err(CliError::Timeout {
                    timeout: self.timeout,
                })
            }
        }
    }
}

/// Kills the CLI on deadline expiry (or a failed drain) and reaps the direct
/// child, so no zombie or orphan survives the call.
async fn teardown(pid: &Option<u32>, child: &mut tokio::process::Child) {
    #[cfg(unix)]
    {
        if let Some(pgid) = *pid {
            kill_process_group(pgid);
        }
    }
    #[cfg(not(unix))]
    {
        // Windows process management is a documented non-goal; kill the
        // direct child at least.
        let _ = pid;
        let _ = child.start_kill();
    }
    let _ = child.wait().await;
}

/// Kills the CLI's whole process group with `SIGKILL`.
///
/// The child was made its own group leader at spawn (`process_group(0)`), so
/// its pid is the group id, and every process it spawned belongs to the group
/// too. A failure (the group already being gone) is harmless.
#[cfg(unix)]
fn kill_process_group(pgid: u32) {
    let Ok(pgid) = libc::pid_t::try_from(pgid) else {
        return; // out of `pid_t` range: can never be a pid we spawned
    };
    // SAFETY: `killpg` only sends a POSIX signal to the CLI's own process
    // group.
    let _ = unsafe { libc::killpg(pgid, libc::SIGKILL) };
}

/// Applies the per-call environment overrides onto the child command, on top
/// of the inherited environment.
///
/// `Command` is per-call, so nothing here touches the server's process
/// environment, and an override set on one call cannot leak into another.
fn apply_overrides(command: &mut Command, overrides: &[(String, String)]) {
    command.envs(
        overrides
            .iter()
            .map(|(key, value)| (key.as_str(), value.as_str())),
    );
}

/// Maps a completed child's status and streams onto the structured outcome.
fn map_outcome(status: &ExitStatus, stdout: String, stderr: String) -> CliOutcome {
    if status.success() {
        CliOutcome::Success { stdout, stderr }
    } else {
        let code = status.code().unwrap_or(-1);
        CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }
    }
}

/// Decodes captured child output as UTF-8, replacing invalid bytes.
fn decode(bytes: Vec<u8>) -> String {
    String::from_utf8_lossy(&bytes).into_owned()
}

/// Resolves the configured CLI binary to an executable path.
fn resolve(cli_bin: &str) -> Result<PathBuf, CliError> {
    if cli_bin.contains('/') {
        // A path (absolute, or relative to the server's working directory).
        let path = PathBuf::from(cli_bin);
        if is_executable(&path) {
            return Ok(path);
        }
        return Err(CliError::Resolve {
            reason: format!("`{cli_bin}` is not an executable file"),
        });
    }

    // A bare name: look it up on `PATH`.
    if let Some(path) = path_lookup(cli_bin) {
        return Ok(path);
    }
    Err(CliError::Resolve {
        reason: format!("`{cli_bin}` was not found as a file or on PATH"),
    })
}

/// Scans `PATH` for an executable `dir/name`.
fn path_lookup(name: &str) -> Option<PathBuf> {
    std::env::split_paths(&std::env::var_os("PATH")?)
        .map(|dir| dir.join(name))
        .find(|candidate| is_executable(candidate))
}

/// Whether the path is an existing file with an execute bit (Unix).
#[cfg(unix)]
fn is_executable(path: &std::path::Path) -> bool {
    use std::os::unix::fs::PermissionsExt;

    match std::fs::metadata(path) {
        Ok(metadata) => metadata.is_file() && metadata.permissions().mode() & 0o111 != 0,
        Err(_) => false,
    }
}

/// Whether the path is an existing file (non-Unix fallback).
#[cfg(not(unix))]
fn is_executable(path: &std::path::Path) -> bool {
    std::fs::metadata(path)
        .map(|metadata| metadata.is_file())
        .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(unix)]
    fn status_from_exit_code(code: i32) -> ExitStatus {
        std::os::unix::process::ExitStatusExt::from_raw(code << 8)
    }

    #[cfg(unix)]
    #[test]
    fn exit_zero_maps_to_success() {
        let outcome = map_outcome(
            &status_from_exit_code(0),
            "stdout-body".to_string(),
            "stderr-body".to_string(),
        );
        assert_eq!(
            outcome,
            CliOutcome::Success {
                stdout: "stdout-body".to_string(),
                stderr: "stderr-body".to_string(),
            }
        );
    }

    #[cfg(unix)]
    #[test]
    fn exit_three_maps_to_structured_exit() {
        let outcome = map_outcome(
            &status_from_exit_code(3),
            "stdout-body".to_string(),
            "stderr-body".to_string(),
        );
        assert_eq!(
            outcome,
            CliOutcome::Exit {
                code: 3,
                stdout: "stdout-body".to_string(),
                stderr: "stderr-body".to_string(),
            }
        );
    }

    #[test]
    fn override_wins_over_the_inherited_value() {
        // SAFETY: one test-scoped mutation of the process environment under a
        // name unique to this test; the stub and other tests only read their
        // own probe variables. The point is an already-set (inherited)
        // variable that the override must win over.
        unsafe { std::env::set_var("SECONDBRAIN_TEST_UNIT_OVERRIDE_PROBE", "inherited") };

        let mut command = Command::new("probe");
        apply_overrides(
            &mut command,
            &[(
                "SECONDBRAIN_TEST_UNIT_OVERRIDE_PROBE".to_string(),
                "override".to_string(),
            )],
        );
        let recorded: Vec<_> = command.as_std().get_envs().collect();
        assert!(
            recorded.contains(&(
                std::ffi::OsStr::new("SECONDBRAIN_TEST_UNIT_OVERRIDE_PROBE"),
                Some(std::ffi::OsStr::new("override"))
            )),
            "the override must be recorded on the child command over the inherited value \
             (explicit command environment takes precedence at spawn): {recorded:?}"
        );
    }

    #[cfg(unix)]
    fn fixture_path(name: &str) -> PathBuf {
        use std::os::unix::fs::PermissionsExt;

        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures")
            .join(name);
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755))
            .expect("the stub fixture must be chmod-able");
        path.canonicalize().expect("the stub fixture must exist")
    }

    #[cfg(unix)]
    #[test]
    fn timeout_maps_to_the_error_variant_without_panicking() {
        // Runs the sleeper stub under a tiny deadline: the elapsed branch
        // must produce `Err(CliError::Timeout)` — not a panic — and the
        // error carries no partial stdout or stderr (they are discarded on
        // timeout by contract).
        let runner = CliRunner::new(
            fixture_path("stub_sleeper.sh")
                .to_str()
                .expect("a UTF-8 stub path"),
            Duration::from_millis(300),
        )
        .expect("the stub must resolve");
        let runtime = tokio::runtime::Runtime::new().expect("a test runtime");

        let outcome = runtime.block_on(runner.run(&["60"], &[]));
        match outcome {
            Err(CliError::Timeout { timeout }) => {
                assert_eq!(timeout, Duration::from_millis(300));
            }
            other => panic!("the sleeper must time out, got {other:?}"),
        }
    }
}
