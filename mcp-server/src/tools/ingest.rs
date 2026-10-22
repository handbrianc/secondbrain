//! The `ingest_documents` MCP tool: file ingestion by driving the
//! secondbrain CLI's `ingest` command through the adapter
//! (`add-mcp-ingest-tool`).
//!
//! Relative paths resolve against the workspace root; validation beyond
//! that (the workspace allow-list) is the confinement proposal's unit
//! (`add-mcp-ingest-path-confinement`). The result text carries the CLI's
//! human-readable ingest summary — a documented limitation, since the CLI
//! has no JSON ingest output.
//!
//! With `async_mode` the call keeps every fast step synchronous (path
//! resolution, confinement, argv build) and detaches only the CLI run into
//! a job polled via `job_status` (`add-mcp-async-ingestion`); the job
//! records exactly what the synchronous call would have returned.

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use rmcp::ErrorData;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::schemars::JsonSchema;
use rmcp::{tool, tool_router};
use serde::Deserialize;

use crate::cli::{CliError, CliOutcome, CliRunner};
use crate::server::SecondBrainServer;

use super::jobs::JobKind;
use super::{describe_exit, render_adapter_error, tool_result};

/// Input of the `ingest_documents` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct IngestParams {
    /// File or directory to ingest; relative paths resolve against the
    /// workspace root (`SECONDBRAIN_MCP_WORKSPACE_ROOT`).
    pub path: String,
    /// Recurse into subdirectories (default false).
    #[serde(default)]
    pub recursive: bool,
    /// Skip chunks already present from a previous ingest (default true;
    /// false passes `--no-skip-existing`).
    #[serde(default = "default_true")]
    pub skip_existing: bool,
    /// Override the default chunk size.
    #[serde(default)]
    pub chunk_size: Option<u64>,
    /// Override the default chunk overlap.
    #[serde(default)]
    pub chunk_overlap: Option<u64>,
    /// Batch size for the CLI's processing pool.
    #[serde(default)]
    pub batch_size: Option<u64>,
    /// Number of CPU cores for parallel processing.
    #[serde(default)]
    pub cores: Option<u64>,
    /// Run the CLI ingest as a detached background job and return a job id
    /// immediately (`add-mcp-async-ingestion`); poll `job_status` for the
    /// outcome. Every fast step — path resolution, confinement, argv build —
    /// still happens inside the call, so an invalid call fails immediately
    /// and creates no job.
    #[serde(default)]
    pub async_mode: bool,
}

/// The serde default for `skip_existing`.
fn default_true() -> bool {
    true
}

/// Registers the `ingest_documents` tool on the shared server.
#[tool_router(router = ingest_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Ingest a file or directory into the knowledge base.
    #[tool(
        description = "Ingest a file or directory into the secondbrain knowledge base \
                       (documents are chunked, embedded, and stored in the vector store). \
                       Relative paths resolve against the workspace root. Returns the \
                       CLI's human-readable ingest summary. Set async_mode to start a \
                       background job and poll job_status instead of waiting for the run \
                       inside this call."
    )]
    async fn ingest_documents(
        &self,
        Parameters(params): Parameters<IngestParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run(self, params).await
    }
}

/// The synchronously prepared part of one ingest: the resolved path and the
/// argv it produced (`add-mcp-async-ingestion` — async mode runs exactly
/// this preparation inside the call and defers only the CLI run to the job).
pub(crate) struct PreparedIngest {
    /// The resolved (absolute) ingest target.
    pub(crate) resolved: PathBuf,
    /// The argv the CLI receives.
    pub(crate) argv: Vec<OsString>,
}

/// Resolves the requested path, confines it to the workspace root, and
/// builds the argv — everything that must happen before a subprocess can
/// start. The error is caller-ready (it names the offending
/// `SECONDBRAIN_MCP_*` variable or the rule): synchronous mode maps it onto
/// [`IngestOutcome::NotRun`], async mode returns it as an immediate tool
/// error that creates no job.
///
/// Deliberately without the runner check: async mode checks the CLI
/// resolution inside the job (the resolution failure is the job's recorded
/// outcome), while synchronous mode checks it first, exactly as before.
pub(crate) fn prepare(
    server: &SecondBrainServer,
    params: &IngestParams,
) -> Result<PreparedIngest, String> {
    let resolved = resolve_path(&server.workspace_root, &params.path);
    // Before any argv build or subprocess: the confinement rule is enforced
    // first.
    confine(&server.workspace_root, &resolved)?;
    Ok(PreparedIngest {
        argv: ingest_argv(&resolved, params),
        resolved,
    })
}

/// What one shared ingest invocation produced, structured so each tool can
/// map it onto its own result shape (`ingest_documents` verbatim,
/// `upload_document` with the stored path carried through).
pub(crate) enum IngestOutcome {
    /// The invocation never started: the CLI binary is unresolved, or the
    /// path failed the confinement rule. The diagnostic is caller-ready (it
    /// names the offending `SECONDBRAIN_MCP_*` variable or the rule).
    NotRun(String),
    /// The CLI was spawned and ran to completion.
    Ran(CliOutcome),
    /// The adapter itself failed before a complete run (spawn failure,
    /// deadline — the CLI's process group was killed and the streams are
    /// discarded by contract).
    AdapterFailed(CliError),
}

/// Runs one ingest: resolve the path, confine it to the workspace root,
/// build the argv, and drive the CLI. Shared by `ingest_documents` (which
/// maps the outcome verbatim) and `upload_document` (which ingests a stored
/// upload through the same confined flow).
pub(crate) async fn drive_ingest(
    server: &SecondBrainServer,
    params: IngestParams,
) -> IngestOutcome {
    let runner = match &server.cli {
        Ok(runner) => runner,
        Err(message) => return IngestOutcome::NotRun(message.clone()),
    };

    let prepared = match prepare(server, &params) {
        Ok(prepared) => prepared,
        Err(rejection) => return IngestOutcome::NotRun(rejection),
    };

    run_prepared(runner, &prepared.argv).await
}

/// Runs the prepared argv through the adapter and maps the result onto the
/// shared outcome — the only part of an ingest that can block on the CLI
/// (and the only part an async job defers, `add-mcp-async-ingestion`).
pub(crate) async fn run_prepared(runner: &CliRunner, argv: &[OsString]) -> IngestOutcome {
    match runner.run(argv, &[]).await {
        Ok(outcome) => IngestOutcome::Ran(outcome),
        Err(error) => IngestOutcome::AdapterFailed(error),
    }
}

/// Maps an ingest outcome onto (success, caller-ready text) exactly as the
/// synchronous `ingest_documents` call returns it
/// (`add-mcp-async-ingestion`: a detached job records this same rendering,
/// so the job status carries the sync-equivalent text).
pub(crate) fn render_outcome(outcome: &IngestOutcome) -> (bool, String) {
    match outcome {
        IngestOutcome::NotRun(message) => (false, message.clone()),
        IngestOutcome::Ran(CliOutcome::Success { stdout, .. }) => {
            // The CLI emits a human-readable summary (no JSON ingest output
            // exists); the prefix makes its origin explicit.
            (
                true,
                format!("ingest summary (from the secondbrain CLI):\n{stdout}"),
            )
        }
        IngestOutcome::Ran(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => (false, describe_exit(*code, stdout, stderr)),
        IngestOutcome::AdapterFailed(error) => (false, render_adapter_error(error)),
    }
}

/// Runs one `ingest_documents` call. Synchronous mode (the default) maps the
/// shared ingest outcome onto the tool result verbatim; `async_mode` keeps
/// the fast preparation inside the call and detaches the CLI run into a job.
pub(crate) async fn run(
    server: &SecondBrainServer,
    params: IngestParams,
) -> Result<CallToolResult, ErrorData> {
    if params.async_mode {
        return run_async(server, params).await;
    }

    let outcome = drive_ingest(server, params).await;
    let (success, text) = render_outcome(&outcome);
    Ok(tool_result(success, text))
}

/// The async-mode flow (`add-mcp-async-ingestion`): resolve + confine + argv
/// build stay inside the call — a rejection is an immediate tool error that
/// creates no job — and the CLI run detaches into a job whose task records
/// the sync-equivalent rendering.
async fn run_async(
    server: &SecondBrainServer,
    params: IngestParams,
) -> Result<CallToolResult, ErrorData> {
    let prepared = match prepare(server, &params) {
        Ok(prepared) => prepared,
        Err(rejection) => {
            // The same immediate error the synchronous call would produce,
            // and no job: nothing was started.
            return Ok(CallToolResult::error(vec![ContentBlock::text(rejection)]));
        }
    };

    let job_id = server
        .jobs
        .create(JobKind::Ingest, &format!("ingest {}", params.path));
    // The start text is rendered before the task moves the id into the job.
    let start_text = format!(
        "Started ingest job {job_id}: ingest {}\n\
         Poll the job_status tool with {{\"job_id\": \"{job_id}\"}} for the result; the job \
         runs to completion even if this connection closes.",
        params.path
    );
    // The task owns everything it needs: the shared registry (a job id must
    // mean the same job to every stateless request), the cloned runner (or
    // its startup resolution failure — the resolution check moves inside the
    // job), and the prepared target + argv. It runs to completion regardless
    // of the client connection, still bounded by the adapter's subprocess
    // deadline.
    let registry = Arc::clone(&server.jobs);
    let runner = server.cli.clone();
    let resolved = prepared.resolved;
    let argv = prepared.argv;
    tokio::spawn(async move {
        tracing::debug!(job = %job_id, path = %resolved.display(), "async ingest job started");
        let outcome = match &runner {
            Ok(runner) => run_prepared(runner, &argv).await,
            Err(message) => IngestOutcome::NotRun(message.clone()),
        };
        let (success, text) = render_outcome(&outcome);
        let state = if success { "completed" } else { "failed" };
        // The caller may be long gone by now; the log is the audit trail for
        // detached work.
        tracing::info!(job = %job_id, state, "async ingest job finished");
        registry.finish(&job_id, success, text);
    });

    Ok(CallToolResult::success(vec![ContentBlock::text(
        start_text,
    )]))
}

/// Resolves the requested path against the workspace root: relative paths
/// join the root and are made absolute; absolute paths pass through.
///
/// No validation beyond resolution at this stage — confinement is
/// [`confine`]'s unit.
fn resolve_path(workspace_root: &Path, path: &str) -> PathBuf {
    let joined = if Path::new(path).is_absolute() {
        PathBuf::from(path)
    } else {
        workspace_root.join(path)
    };
    // Made absolute without touching the filesystem (no symlink resolution;
    // nonexistent paths stay resolvable so the CLI can report them).
    std::path::absolute(joined).unwrap_or_else(|_| PathBuf::from(path))
}

/// The workspace confinement rule: the target must lie inside the workspace
/// root. Returns the full rejection diagnostic (describing the rule and
/// naming `SECONDBRAIN_MCP_WORKSPACE_ROOT`) on escape.
///
/// Both the canonical root and the canonical target are compared, so `..`
/// traversal, absolute paths outside the root, and symlinks pointing outside
/// all resolve to targets outside the canonical root and are rejected. A
/// target that cannot be canonicalized because it does not exist cannot be
/// ingested anyway; it is compared lexically instead, so a still-missing
/// inside path reaches the CLI (which reports it), while lexically escaping
/// paths are rejected here.
fn confine(workspace_root: &Path, resolved: &Path) -> Result<(), String> {
    let canonical_root = std::fs::canonicalize(workspace_root).map_err(|error| {
        format!(
            "the workspace root cannot be used: SECONDBRAIN_MCP_WORKSPACE_ROOT is \
             {workspace_root:?}, which cannot be canonicalized: {error}"
        )
    })?;

    let target = match std::fs::canonicalize(resolved) {
        Ok(target) => target,
        // The target does not exist (or is unreadable): compare lexically.
        Err(_) => normalize_lexically(resolved),
    };

    if target.starts_with(&canonical_root) {
        return Ok(());
    }
    Err(format!(
        "ingest path escapes the workspace: SECONDBRAIN_MCP_WORKSPACE_ROOT is {canonical_root:?} \
         and only paths inside it may be ingested, but the requested path resolves to \
         {target:?}, which is outside it"
    ))
}

/// Lexically normalizes `.` and `..` components without touching the
/// filesystem (the fallback for targets that cannot be canonicalized).
///
/// `pub(crate)`: the upload tool's startup confinement
/// (`tools/upload.rs::validate_upload_dir`) reuses this exact normalization
/// for a not-yet-existing upload directory, so both tools share one rule.
pub(crate) fn normalize_lexically(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            std::path::Component::CurDir => {}
            // `PathBuf::pop` never removes the root, so `..` above `/` (or
            // above nothing) is a no-op, matching realpath semantics.
            std::path::Component::ParentDir => {
                normalized.pop();
            }
            component => normalized.push(component.as_os_str()),
        }
    }
    if normalized.as_os_str().is_empty() {
        normalized.push(".");
    }
    normalized
}

/// Builds the CLI argv: `ingest <resolved-path> [-r] [--no-skip-existing]
/// [--chunk-size N] [--chunk-overlap N] [-b N] [-c N]`.
///
/// `pub(crate)` so the upload tool's unit tests can assert the argv its
/// mapped parameters produce against the same builder `ingest_documents`
/// drives.
pub(crate) fn ingest_argv(resolved_path: &Path, params: &IngestParams) -> Vec<OsString> {
    let mut argv = vec![OsString::from("ingest"), OsString::from(resolved_path)];
    if params.recursive {
        argv.push(OsString::from("-r"));
    }
    if !params.skip_existing {
        argv.push(OsString::from("--no-skip-existing"));
    }
    if let Some(chunk_size) = params.chunk_size {
        argv.push(OsString::from("--chunk-size"));
        argv.push(OsString::from(chunk_size.to_string()));
    }
    if let Some(chunk_overlap) = params.chunk_overlap {
        argv.push(OsString::from("--chunk-overlap"));
        argv.push(OsString::from(chunk_overlap.to_string()));
    }
    if let Some(batch_size) = params.batch_size {
        argv.push(OsString::from("-b"));
        argv.push(OsString::from(batch_size.to_string()));
    }
    if let Some(cores) = params.cores {
        argv.push(OsString::from("-c"));
        argv.push(OsString::from(cores.to_string()));
    }
    argv
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Builds params with every knob settable.
    fn params(
        path: &str,
        recursive: bool,
        skip_existing: bool,
        tuning: Option<u64>,
    ) -> IngestParams {
        IngestParams {
            path: path.to_string(),
            recursive,
            skip_existing,
            chunk_size: tuning,
            chunk_overlap: tuning,
            batch_size: tuning,
            cores: tuning,
            async_mode: false,
        }
    }

    #[test]
    fn relative_paths_resolve_against_the_workspace_root() {
        let resolved = resolve_path(Path::new("/data/workspace"), "docs/report.pdf");
        assert_eq!(
            resolved,
            PathBuf::from("/data/workspace/docs/report.pdf"),
            "relative paths join the workspace root and are made absolute"
        );
    }

    #[test]
    fn absolute_paths_pass_through() {
        let resolved = resolve_path(Path::new("/data/workspace"), "/etc/hosts");
        assert_eq!(resolved, PathBuf::from("/etc/hosts"));
    }

    #[test]
    fn a_relative_workspace_root_resolves_against_the_cwd() {
        // The default workspace root is "." — resolution must still produce
        // an absolute path (anchored at the server's working directory).
        let resolved = resolve_path(Path::new("."), "notes.txt");
        assert!(
            resolved.is_absolute(),
            "resolution must absolutize: {resolved:?}"
        );
    }

    #[test]
    fn argv_covers_every_flag_combination() {
        for with_recursive in [false, true] {
            for skip_existing in [false, true] {
                for with_tuning in [false, true] {
                    let argv = ingest_argv(
                        Path::new("/data/workspace/docs/report.pdf"),
                        &params(
                            "docs/report.pdf",
                            with_recursive,
                            skip_existing,
                            with_tuning.then_some(1024),
                        ),
                    );
                    let strings: Vec<String> = argv
                        .iter()
                        .map(|argument| argument.to_string_lossy().into_owned())
                        .collect();

                    assert_eq!(strings[0], "ingest");
                    assert_eq!(
                        strings[1], "/data/workspace/docs/report.pdf",
                        "the resolved path is the first positional"
                    );

                    let rest = strings[2..].to_vec();
                    let mut flags = rest.into_iter();
                    if with_recursive {
                        assert_eq!(flags.next().as_deref(), Some("-r"));
                    }
                    if !skip_existing {
                        assert_eq!(flags.next().as_deref(), Some("--no-skip-existing"));
                    }
                    if with_tuning {
                        assert_eq!(flags.next().as_deref(), Some("--chunk-size"));
                        assert_eq!(flags.next().as_deref(), Some("1024"));
                        assert_eq!(flags.next().as_deref(), Some("--chunk-overlap"));
                        assert_eq!(flags.next().as_deref(), Some("1024"));
                        assert_eq!(flags.next().as_deref(), Some("-b"));
                        assert_eq!(flags.next().as_deref(), Some("1024"));
                        assert_eq!(flags.next().as_deref(), Some("-c"));
                        assert_eq!(flags.next().as_deref(), Some("1024"));
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
    fn default_skip_existing_emits_no_flag() {
        let argv = ingest_argv(
            Path::new("/w/report.txt"),
            &params("report.txt", false, true, None),
        );
        let strings: Vec<String> = argv
            .iter()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            strings,
            ["ingest", "/w/report.txt"],
            "defaults must map to the bare ingest invocation"
        );
    }

    /// The async jobs record `render_outcome`'s rendering
    /// (`add-mcp-async-ingestion`), so it must map every outcome onto
    /// exactly the shape the synchronous call returns.
    #[test]
    fn the_render_maps_every_outcome_onto_the_sync_shapes() {
        use std::time::Duration;

        let (success, text) = render_outcome(&IngestOutcome::Ran(CliOutcome::Success {
            stdout: "1 documents".to_string(),
            stderr: String::new(),
        }));
        assert!(success);
        assert_eq!(
            text,
            "ingest summary (from the secondbrain CLI):\n1 documents"
        );

        let (success, text) = render_outcome(&IngestOutcome::Ran(CliOutcome::Exit {
            code: 1,
            stdout: String::new(),
            stderr: "exploded".to_string(),
        }));
        assert!(
            !success && text.contains("exit code 1") && text.contains("exploded"),
            "{text}"
        );

        let (success, text) = render_outcome(&IngestOutcome::AdapterFailed(CliError::Timeout {
            timeout: Duration::from_secs(900),
        }));
        assert!(
            !success && text.contains("SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS"),
            "{text}"
        );

        let (success, text) =
            render_outcome(&IngestOutcome::NotRun("escapes the workspace".to_string()));
        assert!(!success);
        assert_eq!(text, "escapes the workspace");
    }

    /// Builds a small workspace (an inside file, a nested directory) plus an
    /// outside file, and returns the canonical workspace path and the
    /// canonical outside-file path. Self-contained per test, under the
    /// system temp dir.
    fn confined_setup(tag: &str) -> (PathBuf, PathBuf) {
        let base =
            std::env::temp_dir().join(format!("mcp-ingest-confine-{tag}-{}", std::process::id()));
        let workspace = base.join("workspace");
        std::fs::create_dir_all(workspace.join("sub")).expect("the workspace must create");
        std::fs::write(workspace.join("report.txt"), "inside").expect("the inside file");
        std::fs::write(base.join("outside.txt"), "outside").expect("the outside file");
        let workspace = workspace.canonicalize().expect("a canonical workspace");
        let outside = base.join("outside.txt");
        (workspace, outside)
    }

    fn cleanup_confined_setup(base_of_workspace: &Path) {
        // Best effort: the parent of the workspace holds everything.
        let _ = std::fs::remove_dir_all(base_of_workspace);
    }

    #[test]
    fn confinement_admits_existing_inside_paths() {
        let (workspace, outside) = confined_setup("inside");
        let base = outside
            .parent()
            .expect("the outside file has a parent")
            .to_path_buf();

        let relative = resolve_path(&workspace, "report.txt");
        confine(&workspace, &relative).expect("a relative inside path must be admitted");

        let absolute = resolve_path(&workspace, workspace.join("sub").to_str().expect("utf-8"));
        confine(&workspace, &absolute).expect("an absolute inside path must be admitted");

        cleanup_confined_setup(&base);
    }

    #[test]
    fn confinement_admits_missing_inside_paths_so_the_cli_reports_them() {
        let (workspace, outside) = confined_setup("missing-inside");
        let base = outside
            .parent()
            .expect("the outside file has a parent")
            .to_path_buf();

        // A nonexistent path inside the workspace cannot be canonicalized;
        // the lexical fallback admits it so the CLI (which validates
        // existence) produces its own error, exactly like the base tool.
        let missing = resolve_path(&workspace, "no-such-file.txt");
        confine(&workspace, &missing).expect("a missing inside path must reach the CLI");

        cleanup_confined_setup(&base);
    }

    #[test]
    fn confinement_rejects_traversal_escapes() {
        let (workspace, outside) = confined_setup("traversal");
        let base = outside
            .parent()
            .expect("the outside file has a parent")
            .to_path_buf();

        // Existing outside target: canonicalization resolves the `..` chain.
        let escape = resolve_path(&workspace, "../outside.txt");
        let rejection = confine(&workspace, &escape).expect_err("traversal must be rejected");
        assert!(
            rejection.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "the rejection must name the variable: {rejection}"
        );
        assert!(
            rejection.contains("escapes the workspace"),
            "the rejection must describe the rule: {rejection}"
        );

        // Missing outside target: the lexical fallback still catches the
        // `..` chain.
        let missing_escape = resolve_path(&workspace, "../missing.txt");
        let rejection = confine(&workspace, &missing_escape)
            .expect_err("traversal to a missing path must still be rejected");
        assert!(
            rejection.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "the rejection must name the variable: {rejection}"
        );

        cleanup_confined_setup(&base);
    }

    #[test]
    fn confinement_rejects_absolute_paths_outside_the_root() {
        let (workspace, outside) = confined_setup("absolute");
        let base = outside
            .parent()
            .expect("the outside file has a parent")
            .to_path_buf();

        let existing_outside = resolve_path(&workspace, outside.to_str().expect("utf-8"));
        let rejection = confine(&workspace, &existing_outside)
            .expect_err("an absolute path outside the root must be rejected");
        assert!(
            rejection.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "the rejection must name the variable: {rejection}"
        );

        let missing_outside = resolve_path(&workspace, "/definitely-not-here-anywhere/x.txt");
        confine(&workspace, &missing_outside)
            .expect_err("a nonexistent absolute path outside the root must be rejected");

        cleanup_confined_setup(&base);
    }

    #[test]
    #[cfg(unix)]
    fn confinement_rejects_symlink_escapes() {
        use std::os::unix::fs::symlink;

        let (workspace, outside) = confined_setup("symlink");
        let base = outside
            .parent()
            .expect("the outside file has a parent")
            .to_path_buf();

        symlink(&outside, workspace.join("escape")).expect("the outbound symlink must create");
        let escape = resolve_path(&workspace, "escape");
        let rejection =
            confine(&workspace, &escape).expect_err("a symlink escape must be rejected");
        assert!(
            rejection.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "the rejection must name the variable: {rejection}"
        );
        assert!(
            rejection.contains("escapes the workspace"),
            "the rejection must describe the rule: {rejection}"
        );

        cleanup_confined_setup(&base);
    }

    #[test]
    fn lexical_normalization_resolves_dot_components() {
        assert_eq!(
            normalize_lexically(Path::new("/a/b/../c/./d")),
            // `..` pops the preceding component (`b`) and `.` is dropped:
            // realpath("/a/b/../c/./d") == "/a/c/d".
            PathBuf::from("/a/c/d"),
        );
        assert_eq!(normalize_lexically(Path::new("/..")), PathBuf::from("/"));
        assert_eq!(
            normalize_lexically(Path::new("/x/../../y")),
            PathBuf::from("/y"),
        );
        assert_eq!(
            normalize_lexically(Path::new("/w/missing.txt")),
            PathBuf::from("/w/missing.txt"),
        );
    }
}
