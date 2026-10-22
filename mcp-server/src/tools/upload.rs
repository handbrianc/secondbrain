//! The `upload_document` MCP tool: one-call upload-and-ingest
//! (`add-mcp-upload-tool`).
//!
//! A client submits a document's bytes (base64) with a filename; the tool
//! stores the decoded bytes inside the workspace under
//! `SECONDBRAIN_MCP_UPLOAD_DIR` (default `<workspace root>/uploads`), and
//! then drives the same confined CLI ingest invocation the `ingest_documents`
//! tool uses — no new ingestion pipeline.
//!
//! Nothing is stored until validation passes: the payload must decode as
//! strict base64, its decoded size must not exceed
//! `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES`, and the filename must reduce to a
//! usable bare name whose target does not already exist (uploads never
//! overwrite). After a successful ingest the staged file is deleted — the
//! upload directory is a transient inbox and the content lives in the
//! knowledge base. A failed ingest never removes the file: it stays in
//! place for a later re-ingest via `ingest_documents`.
//!
//! The upload directory itself is operator configuration, not client input;
//! it is validated at startup to resolve inside the workspace root (the same
//! canonical-first / lexical-fallback rules as the ingest tool's per-call
//! confinement), so the stored path the ingest invocation receives is
//! guaranteed to be an inside path.
//!
//! With `async_mode` every validation and the staging write stay inside the
//! call; only the CLI ingest and the delete-after-ingest disposition detach
//! into a job polled via `job_status` (`add-mcp-async-ingestion`), which
//! records exactly what the synchronous call would have returned — the
//! disposition sentence included.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use rmcp::ErrorData;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::schemars::JsonSchema;
use rmcp::{tool, tool_router};
use serde::Deserialize;
use tokio::io::AsyncWriteExt;

#[cfg(test)]
use crate::cli::CliError;
use crate::cli::CliOutcome;
use crate::config::{ConfigError, UPLOAD_DIR_VAR};
use crate::server::SecondBrainServer;

use super::describe_exit;
use super::ingest::{
    IngestOutcome, IngestParams, drive_ingest, ingest_argv, normalize_lexically, run_prepared,
};
use super::jobs::JobKind;
use super::tool_result;

/// Input of the `upload_document` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct UploadParams {
    /// Name the stored file gets; directory components are stripped
    /// (`nested/report.pdf` stores as `report.pdf`).
    pub filename: String,
    /// The document's bytes, base64-encoded (the wire payload is ~4/3 of the
    /// file size).
    pub content_base64: String,
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
    /// outcome. Every validation and the staging write still happen inside
    /// the call — only the ingest and the staged-file disposition move into
    /// the job.
    #[serde(default)]
    pub async_mode: bool,
}

/// The serde default for `skip_existing`.
fn default_true() -> bool {
    true
}

/// Registers the `upload_document` tool on the shared server.
#[tool_router(router = upload_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Store a document in the workspace and ingest it.
    #[tool(
        description = "Store a document in the workspace and ingest it into the \
                       secondbrain knowledge base in one call. The file travels \
                       base64-encoded in content_base64 and is stored under \
                       SECONDBRAIN_MCP_UPLOAD_DIR (default: the `uploads` directory \
                       inside the workspace root); the filename is reduced to its \
                       bare name and an existing file with the same name is never \
                       overwritten. Ingestion drives the same confined CLI flow as \
                       ingest_documents; the staged file is deleted once its \
                       ingest succeeds, and a failed ingest leaves the file \
                       in place for a later re-ingest. Set async_mode to start a \
                       background job and poll job_status instead of waiting for the \
                       run inside this call."
    )]
    async fn upload_document(
        &self,
        Parameters(params): Parameters<UploadParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run(self, params).await
    }
}

/// Runs one upload: validate the submitted content, store the decoded bytes
/// in the upload directory, then ingest the stored file through the shared
/// ingest invocation. Every validation happens before anything is stored; a
/// successful ingest deletes the staged file, and a failure after storage
/// keeps the file and reports the stored path.
///
/// With `async_mode` (`add-mcp-async-ingestion`) everything up to and
/// including the staging write stays inside the call, so a rejection is the
/// same immediate error as the synchronous call and creates no job; only the
/// CLI ingest and the delete-after-ingest disposition detach into a job.
pub(crate) async fn run(
    server: &SecondBrainServer,
    params: UploadParams,
) -> Result<CallToolResult, ErrorData> {
    let decoded = match decode_content(&params.content_base64) {
        Ok(decoded) => decoded,
        Err(rejection) => return Ok(CallToolResult::error(vec![ContentBlock::text(rejection)])),
    };
    if let Err(rejection) = check_size(&decoded, server.upload_max_bytes) {
        return Ok(CallToolResult::error(vec![ContentBlock::text(rejection)]));
    }
    let name = match bare_name(&params.filename) {
        Ok(name) => name,
        Err(rejection) => return Ok(CallToolResult::error(vec![ContentBlock::text(rejection)])),
    };

    let stored = match store(&server.upload_dir, &name, &decoded).await {
        Ok(stored) => stored,
        Err(StoreError::Collision(existing)) => {
            return Ok(CallToolResult::error(vec![ContentBlock::text(format!(
                "the upload target already exists: {existing:?}; uploads never overwrite an \
                 existing file — pick another filename, or ingest the stored file as-is"
            ))]));
        }
        Err(StoreError::Io { context, source }) => {
            return Ok(CallToolResult::error(vec![ContentBlock::text(format!(
                "the uploaded document could not be stored ({context}): {source}"
            ))]));
        }
    };

    let stored_relative = relative_to_workspace_root(&server.workspace_root, &stored);
    if !params.async_mode {
        // The synchronous continuation, byte for byte as before
        // (`add-mcp-async-ingestion`: the default contract is unchanged).
        let outcome = drive_ingest(server, ingest_params(&stored, &params)).await;
        let disposition = staged_disposition(&stored, &outcome).await;
        return map_stored_outcome(&stored_relative, outcome, disposition);
    }

    run_async(server, params, stored, stored_relative, decoded.len()).await
}

/// The async-mode continuation after the staged file exists
/// (`add-mcp-async-ingestion`): the CLI ingest and the
/// delete-after-ingest disposition detach into a job whose task records the
/// sync-equivalent text — the disposition sentence included. The call
/// returns immediately with the job id and the polling instruction.
async fn run_async(
    server: &SecondBrainServer,
    params: UploadParams,
    stored: PathBuf,
    stored_relative: String,
    decoded_len: usize,
) -> Result<CallToolResult, ErrorData> {
    // The argv is built here, from the stored path: it is an inside path by
    // construction (the upload directory is confined at startup), so no
    // per-call confinement is needed beyond the validations that already
    // passed.
    let argv = ingest_argv(&stored, &ingest_params(&stored, &params));

    let job_id = server.jobs.create(
        JobKind::Upload,
        &format!("upload {} ({} bytes decoded)", params.filename, decoded_len),
    );
    // The start text is rendered before the task moves the id into the job.
    let start_text = format!(
        "Started upload job {job_id}: upload {} ({} bytes decoded)\n\
         Poll the job_status tool with {{\"job_id\": \"{job_id}\"}} for the result; the job \
         runs to completion even if this connection closes.",
        params.filename, decoded_len
    );
    // The task owns everything it needs: the shared registry (a job id must
    // mean the same job to every stateless request), the cloned runner (or
    // its startup resolution failure — the resolution check moves inside the
    // job), the staged path for the disposition, and the argv. It runs to
    // completion regardless of the client connection, still bounded by the
    // adapter's subprocess deadline.
    let registry = Arc::clone(&server.jobs);
    let runner = server.cli.clone();
    tokio::spawn(async move {
        tracing::debug!(job = %job_id, path = %stored.display(), "async upload job started");
        let outcome = match &runner {
            Ok(runner) => run_prepared(runner, &argv).await,
            Err(message) => IngestOutcome::NotRun(message.clone()),
        };
        // The disposition is the job's own business: it runs after the CLI
        // run, inside the same task, under the same contract as the
        // synchronous call (success deletes, failure keeps, a failed delete
        // is reported without failing the job).
        let disposition = staged_disposition(&stored, &outcome).await;
        let (success, text) = render_stored_outcome(&stored_relative, &outcome, &disposition);
        let state = if success { "completed" } else { "failed" };
        // The caller may be long gone by now; the log is the audit trail for
        // detached work.
        tracing::info!(job = %job_id, state, "async upload job finished");
        registry.finish(&job_id, success, text);
    });

    Ok(CallToolResult::success(vec![ContentBlock::text(
        start_text,
    )]))
}

/// Strictly decodes the submitted base64 payload.
///
/// The standard alphabet with canonical padding is required: whitespace,
/// URL-safe characters, and non-canonical trailing bits are decode errors,
/// so a caller cannot accidentally submit mangled bytes.
fn decode_content(content_base64: &str) -> Result<Vec<u8>, String> {
    BASE64_STANDARD
        .decode(content_base64.as_bytes())
        .map_err(|error| format!("the uploaded content is not valid base64: {error}"))
}

/// The decoded-size rule: at most `SECONDBRAIN_MCP_UPLOAD_MAX_BYTES` bytes.
fn check_size(decoded: &[u8], max_bytes: u64) -> Result<(), String> {
    let size = decoded.len() as u64;
    if size <= max_bytes {
        return Ok(());
    }
    Err(format!(
        "the uploaded content is too large: {size} decoded bytes exceed \
         SECONDBRAIN_MCP_UPLOAD_MAX_BYTES ({max_bytes} bytes); nothing was stored"
    ))
}

/// Reduces the requested filename to the bare name the file is stored under:
/// directory components are stripped (`nested/report.pdf` → `report.pdf`,
/// absolute paths included). A filename that reduces to nothing — empty,
/// `.`/`..`, or a bare separator — is rejected.
fn bare_name(filename: &str) -> Result<String, String> {
    Path::new(filename)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty() && *name != "." && *name != "..")
        .map(str::to_string)
        .ok_or_else(|| {
            format!(
                "the requested filename is not usable: {filename:?} does not reduce to a bare \
                 file name (directory components are stripped; empty names, `.` and `..` are \
                 rejected)"
            )
        })
}

/// Why storing one upload failed.
#[derive(Debug)]
enum StoreError {
    /// The derived target already exists; uploads never overwrite.
    Collision(PathBuf),
    /// The directory could not be created or the bytes could not be written.
    Io {
        /// What the failing step touched (the directory or the target path).
        context: String,
        /// The underlying I/O error.
        source: std::io::Error,
    },
}

/// Stores the decoded bytes under `name` inside `upload_dir`, creating the
/// directory on demand, and returns the stored path.
///
/// The file is created exclusively (`create_new`): a collision is detected
/// without ever opening the existing file for writing, so an existing file
/// cannot be truncated by a racing call. A failed write removes the partial
/// file, so a corrected retry is not blocked by leftover bytes.
async fn store(upload_dir: &Path, name: &str, decoded: &[u8]) -> Result<PathBuf, StoreError> {
    tokio::fs::create_dir_all(upload_dir)
        .await
        .map_err(|source| StoreError::Io {
            context: format!("the upload directory is {upload_dir:?}"),
            source,
        })?;

    let stored = upload_dir.join(name);
    let mut file = tokio::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&stored)
        .await
        .map_err(|source| match source.kind() {
            std::io::ErrorKind::AlreadyExists => StoreError::Collision(stored.clone()),
            _ => StoreError::Io {
                context: format!("the upload target is {stored:?}"),
                source,
            },
        })?;
    if let Err(source) = file.write_all(decoded).await {
        let _ = tokio::fs::remove_file(&stored).await;
        return Err(StoreError::Io {
            context: format!("the upload target is {stored:?}"),
            source,
        });
    }
    // tokio's file writes are buffered and drained on the blocking pool:
    // flushing queues the buffered tail, so the bytes are on disk before
    // the ingest subprocess reads the file.
    if let Err(source) = file.flush().await {
        let _ = tokio::fs::remove_file(&stored).await;
        return Err(StoreError::Io {
            context: format!("the upload target is {stored:?}"),
            source,
        });
    }
    Ok(stored)
}

/// Maps the upload's ingest knobs onto the shared ingest parameters: the
/// stored path is the ingest target, recursion does not apply (one file, not
/// a directory), and every tuning flag passes through unchanged.
///
/// `async_mode` is always false here: the upload call has already consumed
/// its own `async_mode` knob — the synchronous path drives this flow inline,
/// and the async path builds the argv from these parameters and runs the CLI
/// inside the job task (`add-mcp-async-ingestion`).
fn ingest_params(stored: &Path, params: &UploadParams) -> IngestParams {
    IngestParams {
        path: stored.to_string_lossy().into_owned(),
        recursive: false,
        skip_existing: params.skip_existing,
        chunk_size: params.chunk_size,
        chunk_overlap: params.chunk_overlap,
        batch_size: params.batch_size,
        cores: params.cores,
        async_mode: false,
    }
}

/// Renders the stored path relative to the workspace root when possible
/// (canonical root minus canonical stored path), falling back to the stored
/// path verbatim when either cannot be canonicalized. The relative form is
/// what callers can hand straight back to `ingest_documents`.
fn relative_to_workspace_root(workspace_root: &Path, stored: &Path) -> String {
    let canonical_root = std::fs::canonicalize(workspace_root).ok();
    let canonical_stored = std::fs::canonicalize(stored).ok();
    if let (Some(root), Some(stored)) = (canonical_root.as_deref(), canonical_stored.as_deref())
        && let Ok(relative) = stored.strip_prefix(root)
    {
        let rendered = relative.to_string_lossy();
        if !rendered.is_empty() {
            return rendered.into_owned();
        }
    }
    stored.to_string_lossy().into_owned()
}

/// What happened to the staged file once its ingest finished.
///
/// A successful ingest deletes the file — the upload directory is a
/// transient inbox and the ingested content lives in the knowledge base. A
/// failed ingest keeps it for a later re-ingest (the documented contract),
/// and a deletion that itself fails is carried through so the success
/// result can report it instead of silently keeping the file.
enum StagedDisposition {
    Deleted,
    DeleteFailed(std::io::Error),
    Kept,
}

/// Deletes the staged file after a successful ingest; every other outcome
/// keeps it in place.
async fn staged_disposition(stored: &Path, outcome: &IngestOutcome) -> StagedDisposition {
    match outcome {
        IngestOutcome::Ran(CliOutcome::Success { .. }) => {
            match tokio::fs::remove_file(stored).await {
                Ok(()) => StagedDisposition::Deleted,
                Err(error) => StagedDisposition::DeleteFailed(error),
            }
        }
        _ => StagedDisposition::Kept,
    }
}

/// Maps one post-storage ingest outcome onto (success, caller-ready text),
/// carrying the stored path through every shape — on success (the path stays
/// in the result even though the staged file is gone: it is the source path
/// recorded in the knowledge base) and on failure alike (a failed ingest
/// leaves the file in place for a later re-ingest via `ingest_documents`).
///
/// This is the exact rendering the synchronous `upload_document` call
/// returns; the async job records the same text, disposition sentence
/// included (`add-mcp-async-ingestion`).
fn render_stored_outcome(
    stored_relative: &str,
    outcome: &IngestOutcome,
    disposition: &StagedDisposition,
) -> (bool, String) {
    match outcome {
        IngestOutcome::Ran(CliOutcome::Success { stdout, .. }) => {
            let staged = match disposition {
                StagedDisposition::Deleted => {
                    "the staged file was deleted after the successful ingest".to_string()
                }
                StagedDisposition::DeleteFailed(error) => format!(
                    "deleting the staged file after the successful ingest failed \
                     ({error}); the file remains in place — remove it manually if \
                     it is no longer needed"
                ),
                // Unreachable by construction: the disposition is derived
                // from this same outcome, so a success never arrives with
                // `Kept`. The neutral fallback keeps the mapping total
                // instead of panicking the server.
                StagedDisposition::Kept => "the staged file remains at the stored path".to_string(),
            };
            (
                true,
                format!(
                    "stored at {stored_relative} (relative to the workspace root); {staged}\n\
                     ingest summary (from the secondbrain CLI):\n{stdout}"
                ),
            )
        }
        IngestOutcome::Ran(CliOutcome::Exit {
            code,
            stdout,
            stderr,
        }) => (
            false,
            format!(
                "the document was stored at {stored_relative}, but its ingestion failed:\n{}",
                describe_exit(*code, stdout, stderr)
            ),
        ),
        IngestOutcome::AdapterFailed(error) => (
            false,
            format!(
                "the document was stored at {stored_relative}, but its ingestion failed:\n{error}"
            ),
        ),
        IngestOutcome::NotRun(message) => (
            false,
            format!(
                "the document was stored at {stored_relative}, but its ingestion did not run:\n\
                 {message}"
            ),
        ),
    }
}

/// Wraps the rendered outcome into the tool result (`add-mcp-async-ingestion`:
/// the sync call and the async job share one rendering).
fn map_stored_outcome(
    stored_relative: &str,
    outcome: IngestOutcome,
    disposition: StagedDisposition,
) -> Result<CallToolResult, ErrorData> {
    let (success, text) = render_stored_outcome(stored_relative, &outcome, &disposition);
    Ok(tool_result(success, text))
}

/// The startup confinement rule for `SECONDBRAIN_MCP_UPLOAD_DIR`: the
/// configured upload directory must resolve inside the workspace root.
///
/// The same canonical-first / lexical-fallback comparison as the ingest
/// tool's per-call confinement applies: an existing directory is
/// canonicalized (so `..` traversal and symlinks that resolve outside are
/// caught), while a not-yet-created directory is compared after lexical
/// `.`/`..` normalization — it is then created on demand at upload time. A
/// dangling symlink is not an existing path, so it is compared lexically
/// too, exactly like the ingest tool treats a dangling outbound symlink.
/// Both sides are absolutized first, so the default `uploads` inside a
/// relative workspace root compares cleanly before anything exists.
pub(crate) fn validate_upload_dir(
    workspace_root: &Path,
    upload_dir: &Path,
) -> Result<(), ConfigError> {
    let resolved_upload = std::path::absolute(upload_dir).map_err(|error| {
        ConfigError::invalid(
            UPLOAD_DIR_VAR,
            format!("the upload directory {upload_dir:?} cannot be made absolute: {error}"),
        )
    })?;
    let resolved_root = std::path::absolute(workspace_root).map_err(|error| {
        ConfigError::invalid(
            UPLOAD_DIR_VAR,
            format!("the workspace root {workspace_root:?} cannot be made absolute: {error}"),
        )
    })?;

    // Canonical root when it exists (the usual case); lexical fallback
    // otherwise, mirroring the ingest confinement's fallback. Unlike the
    // per-call rule, a root that cannot be canonicalized does not refuse
    // startup here — ingestion keeps its per-call refusal and uploads fall
    // back to the lexical comparison below.
    let canonical_root = std::fs::canonicalize(&resolved_root).ok();
    let root = canonical_root.as_deref().unwrap_or(&resolved_root);
    let upload = match std::fs::canonicalize(&resolved_upload) {
        Ok(canonical_upload) => canonical_upload,
        // The directory does not exist yet (the default case): compare
        // lexically.
        Err(_) => normalize_lexically(&resolved_upload),
    };

    if upload.starts_with(root) {
        return Ok(());
    }
    Err(ConfigError::invalid(
        UPLOAD_DIR_VAR,
        format!(
            "the upload directory escapes the workspace: it resolves to {upload:?}, which is \
             outside SECONDBRAIN_MCP_WORKSPACE_ROOT ({root:?}); only directories inside the \
             workspace root may store uploads"
        ),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Builds params with the ingest knobs settable.
    fn params(filename: &str, skip_existing: bool, tuning: Option<u64>) -> UploadParams {
        UploadParams {
            filename: filename.to_string(),
            content_base64: String::new(),
            skip_existing,
            chunk_size: tuning,
            chunk_overlap: tuning,
            batch_size: tuning,
            cores: tuning,
            async_mode: false,
        }
    }

    /// A fresh self-contained directory under the system temp dir.
    fn fresh_dir(tag: &str) -> PathBuf {
        let base =
            std::env::temp_dir().join(format!("mcp-upload-unit-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        std::fs::create_dir_all(&base).expect("the test directory must create");
        base
    }

    #[test]
    fn decode_rejects_non_base64_payloads() {
        assert!(
            decode_content("not base64!!").is_err(),
            "characters outside the alphabet must be rejected"
        );
        assert!(
            decode_content("aGVsbG8=").is_ok(),
            "canonical standard-alphabet input must decode"
        );
    }

    #[test]
    fn decode_is_strict_about_whitespace_and_trailing_bits() {
        // The standard engine requires canonical padding: no whitespace
        // tolerated.
        assert!(
            decode_content("aGVsbG8=\n").is_err(),
            "embedded whitespace must be rejected"
        );
        // Non-canonical trailing bits (`RG` would be `RG8=`'s prefix) must
        // be rejected too.
        assert!(
            decode_content("QUJDRA").is_err(),
            "a non-canonical unpadded tail must be rejected"
        );
    }

    #[test]
    fn size_at_the_limit_is_admitted_and_one_past_it_is_rejected() {
        let decoded = vec![0u8; 1024];
        assert_eq!(check_size(&decoded, 1024), Ok(()), "at the limit is fine");
        let rejection = check_size(&decoded, 1023).expect_err("one past the limit must reject");
        assert!(
            rejection.contains("SECONDBRAIN_MCP_UPLOAD_MAX_BYTES"),
            "the rejection must name the variable: {rejection}"
        );
        assert!(
            rejection.contains("nothing was stored"),
            "the rejection must state that nothing was stored: {rejection}"
        );
    }

    #[test]
    fn filenames_reduce_to_their_bare_name() {
        assert_eq!(bare_name("report.pdf").expect("usable"), "report.pdf");
        assert_eq!(
            bare_name("nested/report.pdf").expect("usable"),
            "report.pdf"
        );
        assert_eq!(
            bare_name("/absolute/path/report.pdf").expect("usable"),
            "report.pdf",
            "absolute paths reduce to the bare name too"
        );
        assert_eq!(bare_name("a/./b.txt").expect("usable"), "b.txt");
    }

    #[test]
    fn unusable_filenames_are_rejected() {
        for unusable in ["", ".", "..", "/", "nested/..", "//"] {
            let rejection = bare_name(unusable).expect_err("an unusable filename must be rejected");
            assert!(
                rejection.contains("not usable"),
                "the rejection must describe the rule: {rejection}"
            );
        }
    }

    #[tokio::test]
    async fn store_creates_the_directory_and_writes_the_bytes() {
        let base = fresh_dir("store-ok");
        let upload_dir = base.join("uploads");
        let stored = store(&upload_dir, "report.txt", b"hello")
            .await
            .expect("must store");
        assert_eq!(stored, upload_dir.join("report.txt"));
        assert_eq!(
            std::fs::read(&stored).expect("the stored file must read"),
            b"hello",
            "the stored bytes must be the decoded payload"
        );
    }

    #[tokio::test]
    async fn store_rejects_a_collision_without_touching_the_existing_file() {
        let base = fresh_dir("store-collision");
        let upload_dir = base.join("uploads");
        std::fs::create_dir_all(&upload_dir).expect("the upload dir must create");
        std::fs::write(upload_dir.join("taken.txt"), "keep me").expect("the existing file");

        let error = store(&upload_dir, "taken.txt", b"new bytes")
            .await
            .expect_err("a collision must be rejected");
        match error {
            StoreError::Collision(existing) => {
                assert_eq!(existing, upload_dir.join("taken.txt"));
            }
            other => panic!("a collision must map to the Collision variant: {other:?}"),
        }
        assert_eq!(
            std::fs::read_to_string(upload_dir.join("taken.txt")).expect("the file must read"),
            "keep me",
            "the existing file must be untouched"
        );
    }

    #[tokio::test]
    async fn store_reports_a_directory_failure_without_creating_anything() {
        // The upload dir's parent is a file: creation fails, nothing is
        // stored, and the error carries the offending path.
        let base = fresh_dir("store-blocked");
        std::fs::write(base.join("blocker"), "a file, not a directory").expect("the blocker");
        let upload_dir = base.join("blocker").join("uploads");

        let error = store(&upload_dir, "report.txt", b"bytes")
            .await
            .expect_err("storing below a file must fail");
        match error {
            StoreError::Io { context, .. } => {
                assert!(
                    context.contains("upload directory"),
                    "the context must name the upload directory: {context}"
                );
            }
            other => panic!("a directory failure must map to the Io variant: {other:?}"),
        }
        assert!(
            !base.join("blocker").join("uploads").exists(),
            "nothing may be created below the blocker"
        );
    }

    #[test]
    fn ingest_parameters_map_onto_the_shared_argv() {
        // The upload maps onto the same IngestParams the ingest tool builds,
        // so the argv must come out identical (verified against the shared
        // argv builder).
        let stored = Path::new("/w/uploads/report.txt");
        let upload = params("report.txt", false, Some(1024));
        let argv = ingest_argv(stored, &ingest_params(stored, &upload));
        let strings: Vec<String> = argv
            .iter()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            strings,
            [
                "ingest",
                "/w/uploads/report.txt",
                "--no-skip-existing",
                "--chunk-size",
                "1024",
                "--chunk-overlap",
                "1024",
                "-b",
                "1024",
                "-c",
                "1024",
            ],
            "skip_existing: false and the tuning flags must map like ingest_documents"
        );

        let defaults = params("report.txt", true, None);
        let argv = ingest_argv(stored, &ingest_params(stored, &defaults));
        let strings: Vec<String> = argv
            .iter()
            .map(|argument| argument.to_string_lossy().into_owned())
            .collect();
        assert_eq!(
            strings,
            ["ingest", "/w/uploads/report.txt"],
            "defaults must map to the bare ingest invocation, and recursion never applies"
        );
    }

    #[test]
    fn stored_outcomes_carry_the_stored_path_and_the_cli_summary() {
        let result = map_stored_outcome(
            "uploads/report.txt",
            IngestOutcome::Ran(CliOutcome::Success {
                stdout: "ingested 1 document".to_string(),
                stderr: String::new(),
            }),
            StagedDisposition::Deleted,
        )
        .expect("a success must map to a success result");
        assert_eq!(result.is_error, Some(false), "a success is not an error");
        let text = &result.content[0].as_text().expect("a text block").text;
        assert!(
            text.contains("stored at uploads/report.txt"),
            "the success must carry the stored path: {text}"
        );
        assert!(
            text.contains("the staged file was deleted after the successful ingest"),
            "the success must state that the staged file was deleted: {text}"
        );
        assert!(
            text.contains("ingest summary (from the secondbrain CLI):\ningested 1 document"),
            "the success must carry the CLI summary with the usual prefix: {text}"
        );
    }

    #[test]
    fn stored_failures_carry_the_stored_path_and_diagnostics() {
        let exit = map_stored_outcome(
            "uploads/BOOM.txt",
            IngestOutcome::Ran(CliOutcome::Exit {
                code: 1,
                stdout: String::new(),
                stderr: "exploded".to_string(),
            }),
            StagedDisposition::Kept,
        )
        .expect("a tool-level error result, not a protocol error");
        assert_eq!(exit.is_error, Some(true), "a failed run is a tool error");
        let text = &exit.content[0].as_text().expect("a text block").text;
        assert!(
            text.contains("stored at uploads/BOOM.txt")
                && text.contains("exit code 1")
                && text.contains("exploded"),
            "the error must carry the stored path and the CLI diagnostics: {text}"
        );

        let adapter = map_stored_outcome(
            "uploads/report.txt",
            IngestOutcome::AdapterFailed(CliError::Timeout {
                timeout: std::time::Duration::from_secs(900),
            }),
            StagedDisposition::Kept,
        )
        .expect("a tool-level error result, not a protocol error");
        let text = &adapter.content[0].as_text().expect("a text block").text;
        assert!(
            text.contains("stored at uploads/report.txt")
                && text.contains("SECONDBRAIN_MCP_SUBPROCESS_TIMEOUT_SECONDS"),
            "an adapter failure must carry the stored path and name the variable: {text}"
        );

        let not_run = map_stored_outcome(
            "uploads/report.txt",
            IngestOutcome::NotRun(
                "ingest path escapes the workspace: SECONDBRAIN_MCP_WORKSPACE_ROOT …".to_string(),
            ),
            StagedDisposition::Kept,
        )
        .expect("a tool-level error result, not a protocol error");
        let text = &not_run.content[0].as_text().expect("a text block").text;
        assert!(
            text.contains("stored at uploads/report.txt")
                && text.contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "a not-run outcome must carry the stored path and the diagnostic: {text}"
        );
    }

    #[tokio::test]
    async fn a_successful_ingest_deletes_the_staged_file_and_a_failure_keeps_it() {
        let base = fresh_dir("disposition");
        let staged = base.join("report.txt");

        // Success: the file is removed from disk.
        std::fs::write(&staged, "ingested").expect("the staged file");
        let outcome = IngestOutcome::Ran(CliOutcome::Success {
            stdout: "Successfully ingested 1 files".to_string(),
            stderr: String::new(),
        });
        assert!(matches!(
            staged_disposition(&staged, &outcome).await,
            StagedDisposition::Deleted
        ));
        assert!(
            !staged.exists(),
            "a successful ingest must delete the staged file"
        );

        // A failed run keeps the file for a later re-ingest.
        std::fs::write(&staged, "kept").expect("the staged file");
        let outcome = IngestOutcome::Ran(CliOutcome::Exit {
            code: 1,
            stdout: String::new(),
            stderr: "exploded".to_string(),
        });
        assert!(matches!(
            staged_disposition(&staged, &outcome).await,
            StagedDisposition::Kept
        ));
        assert!(
            staged.exists(),
            "a failed ingest must keep the file for a later re-ingest"
        );
    }

    #[tokio::test]
    async fn a_failed_deletion_is_reported_without_failing_the_call() {
        // A directory stands in for an unremovable staged file: remove_file
        // refuses directories everywhere, so the failure is deterministic.
        let base = fresh_dir("delete-failed");
        let staged = base.join("stuck");
        std::fs::create_dir_all(&staged).expect("the stand-in");
        let outcome = IngestOutcome::Ran(CliOutcome::Success {
            stdout: "Successfully ingested 1 files".to_string(),
            stderr: String::new(),
        });
        let disposition = staged_disposition(&staged, &outcome).await;
        assert!(matches!(disposition, StagedDisposition::DeleteFailed(_)));
        assert!(
            staged.exists(),
            "the stand-in must survive the failed delete"
        );

        let result = map_stored_outcome("uploads/report.txt", outcome, disposition)
            .expect("the ingest itself succeeded, so the call must too");
        assert_eq!(
            result.is_error,
            Some(false),
            "a deletion failure must not fail an ingested upload"
        );
        let text = &result.content[0].as_text().expect("a text block").text;
        assert!(
            text.contains("deleting the staged file after the successful ingest failed"),
            "the deletion failure must be reported in the success text: {text}"
        );
        assert!(
            text.contains("the file remains in place"),
            "the report must say the staged file stays: {text}"
        );
        assert!(
            text.contains("ingest summary (from the secondbrain CLI)"),
            "the CLI summary must still be carried: {text}"
        );
    }

    #[test]
    fn the_stored_path_renders_relative_to_the_workspace_root() {
        let base = fresh_dir("relative");
        let workspace = base.join("workspace");
        std::fs::create_dir_all(workspace.join("uploads")).expect("the dirs must create");
        std::fs::write(workspace.join("uploads").join("report.txt"), "x").expect("the stored file");
        let workspace = workspace.canonicalize().expect("the workspace must exist");

        let stored = workspace.join("uploads").join("report.txt");
        assert_eq!(
            relative_to_workspace_root(&workspace, &stored),
            "uploads/report.txt",
            "the stored path must render relative to the workspace root"
        );
    }

    #[test]
    fn the_stored_path_falls_back_verbatim_when_the_root_cannot_canonicalize() {
        let base = fresh_dir("relative-fallback");
        // A root that does not exist cannot be canonicalized; the stored path
        // (also nonexistent here) is then rendered verbatim.
        let missing_root = base.join("no-such-root");
        let stored = missing_root.join("uploads").join("report.txt");
        assert_eq!(
            relative_to_workspace_root(&missing_root, &stored),
            stored.to_string_lossy(),
            "the fallback renders the stored path verbatim"
        );
    }

    #[test]
    fn upload_dir_inside_the_root_is_admitted() {
        let base = fresh_dir("validate-inside");
        let workspace = base.join("workspace");
        let upload_dir = workspace.join("uploads");

        // Not created yet: the lexical comparison admits it.
        validate_upload_dir(&workspace, &upload_dir)
            .expect("a missing inside upload dir must be admitted");

        // Existing: the canonical comparison admits it.
        std::fs::create_dir_all(&upload_dir).expect("the upload dir must create");
        validate_upload_dir(&workspace, &upload_dir)
            .expect("an existing inside upload dir must be admitted");
    }

    #[test]
    fn upload_dir_outside_the_root_is_refused_with_the_variable_named() {
        let base = fresh_dir("validate-outside");
        let workspace = base.join("workspace");
        std::fs::create_dir_all(&workspace).expect("the workspace must create");
        let workspace = workspace.canonicalize().expect("the workspace must exist");
        let outside = base.join("outside");
        std::fs::create_dir_all(&outside).expect("the outside dir must create");

        let error = validate_upload_dir(&workspace, &outside.canonicalize().expect("canonical"))
            .expect_err("an outside upload dir must be refused");
        assert_eq!(error.variable, UPLOAD_DIR_VAR);
        assert!(
            error.to_string().contains("escapes the workspace"),
            "the refusal must describe the rule: {error}"
        );

        // Traversal in the configured value, directory missing: the lexical
        // comparison refuses it too.
        let error = validate_upload_dir(&workspace, Path::new("../outside-uploads"))
            .expect_err("a traversal escape must be refused");
        assert_eq!(error.variable, UPLOAD_DIR_VAR);
    }

    #[test]
    fn upload_dir_symlinked_outside_the_root_is_refused() {
        let base = fresh_dir("validate-symlink");
        let workspace = base.join("workspace");
        std::fs::create_dir_all(&workspace).expect("the workspace must create");
        let workspace = workspace.canonicalize().expect("the workspace must exist");
        let outside = base.join("outside");
        std::fs::create_dir_all(&outside).expect("the outside dir must create");
        std::os::unix::fs::symlink(&outside, workspace.join("up")).expect("the symlink");

        let error = validate_upload_dir(&workspace, &workspace.join("up"))
            .expect_err("a symlinked-outside upload dir must be refused");
        assert_eq!(error.variable, UPLOAD_DIR_VAR);
        assert!(
            error.to_string().contains("SECONDBRAIN_MCP_WORKSPACE_ROOT"),
            "the refusal must name the workspace root variable: {error}"
        );
    }

    #[test]
    fn upload_dir_defaults_admit_a_relative_workspace_root() {
        // The default configuration: workspace root "." (the server's
        // working directory) and upload dir "./uploads" — both relative,
        // both absolutized before the comparison.
        validate_upload_dir(Path::new("."), Path::new("./uploads"))
            .expect("the default upload dir must be admitted against the default root");
    }
}
