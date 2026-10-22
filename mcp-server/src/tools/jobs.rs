//! The asynchronous job registry and the `job_status` MCP tool
//! (`add-mcp-async-ingestion`).
//!
//! The ingest-family tools can run their CLI invocation as a detached job:
//! the call performs the fast validation synchronously, spawns the CLI run
//! into a Tokio task, and returns a job id immediately. The job runs to
//! completion regardless of the client connection — still bounded by the
//! adapter's subprocess deadline (`add-mcp-cli-timeout`) — and its outcome
//! is retrievable via `job_status`, which records the exact result text the
//! synchronous call would have produced.
//!
//! The registry lives in server memory for the process lifetime: ids are
//! sequential per process (`job-1`, `job-2`, …), finished jobs are retained
//! up to a bounded count (the oldest evicted; running jobs are never
//! evicted), and a restart starts from an empty registry — previously issued
//! ids are reported as unknown. Persistence and cancellation are recorded
//! non-goals of the change.

use std::collections::{HashMap, VecDeque};
use std::sync::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Instant;

use rmcp::ErrorData;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{CallToolResult, ContentBlock};
use rmcp::schemars::JsonSchema;
use rmcp::{tool, tool_router};
use serde::Deserialize;

use crate::server::SecondBrainServer;

use super::tool_result;

/// How many finished jobs are retained before the oldest is evicted. The
/// bound only caps the finished tail — a running job is never evicted, so a
/// live job's id always resolves.
const FINISHED_RETENTION: usize = 100;

/// What a job runs: one shared ingest invocation, either started directly
/// (`ingest_documents`) or through a stored upload (`upload_document`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum JobKind {
    Ingest,
    Upload,
}

impl JobKind {
    /// The kind's name in job-status renderings.
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Ingest => "ingest",
            Self::Upload => "upload",
        }
    }
}

/// A job's lifecycle state: running until its task records a terminal result.
///
/// A job's own failure never fails the poll — it is conveyed by the `failed`
/// state and the recorded text (`add-mcp-async-ingestion`: "the poll worked,
/// the job failed" stays distinguishable).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum JobState {
    Running,
    Completed,
    Failed,
}

impl JobState {
    /// The state's name in job-status renderings.
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Running => "running",
            Self::Completed => "completed",
            Self::Failed => "failed",
        }
    }
}

/// One job's record, as kept in the registry.
#[derive(Debug)]
struct JobRecord {
    kind: JobKind,
    state: JobState,
    /// When the job was created; renders the elapsed seconds in job status.
    started: Instant,
    /// One-line summary of what the job runs (e.g. `ingest report.txt`).
    summary: String,
    /// The terminal outcome: (success, the exact text the synchronous call
    /// would have produced). `None` while the job is still running.
    result: Option<(bool, String)>,
}

/// A plain snapshot of one job for the `job_status` tool.
#[derive(Debug, Clone)]
pub(crate) struct JobView {
    /// The job's id (`job-<n>`).
    pub(crate) id: String,
    pub(crate) kind: JobKind,
    pub(crate) state: JobState,
    /// Whole seconds elapsed since the job was created.
    pub(crate) elapsed_secs: u64,
    pub(crate) summary: String,
    /// The terminal outcome, once recorded.
    pub(crate) result: Option<(bool, String)>,
}

/// The mutable state behind one [`JobRegistry`]: the live records plus the
/// finished-id queue that drives the bounded retention. One lock covers both
/// so eviction never races a lookup.
#[derive(Debug, Default)]
struct RegistryInner {
    jobs: HashMap<String, JobRecord>,
    /// Finished job ids in completion order, oldest first; at most
    /// [`FINISHED_RETENTION`] entries.
    finished: VecDeque<String>,
}

/// The process-lifetime registry of asynchronous jobs.
///
/// One registry is created at startup and shared by every server instance:
/// the stateless transport builds a fresh handler per request, so the
/// registry must live behind a shared `Arc` for a job id to mean the same
/// job to every request.
pub(crate) struct JobRegistry {
    inner: Mutex<RegistryInner>,
    /// The next job's sequence number, rendered as `job-<n + 1>` (so ids
    /// start at `job-1`).
    next: AtomicU64,
}

impl JobRegistry {
    /// Creates an empty registry; job ids start at `job-1`.
    pub(crate) fn new() -> Self {
        Self {
            inner: Mutex::new(RegistryInner::default()),
            next: AtomicU64::new(0),
        }
    }

    /// Registers a new running job and returns its id (`job-<n>`).
    pub(crate) fn create(&self, kind: JobKind, summary: &str) -> String {
        let sequence = self.next.fetch_add(1, Ordering::Relaxed) + 1;
        let id = format!("job-{sequence}");
        let mut inner = self
            .inner
            .lock()
            .expect("the job registry must not be poisoned");
        inner.jobs.insert(
            id.clone(),
            JobRecord {
                kind,
                state: JobState::Running,
                started: Instant::now(),
                summary: summary.to_string(),
                result: None,
            },
        );
        id
    }

    /// Records a job's terminal outcome: the state flips to completed or
    /// failed and the text is kept verbatim.
    ///
    /// Finishing is a once-per-job event (the job's own task calls it); a
    /// second finish is a no-op so the first recorded outcome cannot be
    /// overwritten. An unknown id (evicted, or from a previous process) is
    /// equally a no-op — a running job is never evicted, so a live job's
    /// finish always lands.
    pub(crate) fn finish(&self, id: &str, success: bool, text: String) {
        let mut inner = self
            .inner
            .lock()
            .expect("the job registry must not be poisoned");
        let Some(record) = inner.jobs.get_mut(id) else {
            return;
        };
        if record.result.is_some() {
            return;
        }
        record.state = if success {
            JobState::Completed
        } else {
            JobState::Failed
        };
        record.result = Some((success, text));
        inner.finished.push_back(id.to_string());
        // Bounded retention: the oldest finished jobs are evicted; running
        // jobs are never in the queue, so they are never evicted.
        while inner.finished.len() > FINISHED_RETENTION {
            let oldest = inner
                .finished
                .pop_front()
                .expect("the finished queue is non-empty");
            inner.jobs.remove(&oldest);
        }
    }

    /// Snapshots one job, or `None` for an unknown id.
    pub(crate) fn get(&self, id: &str) -> Option<JobView> {
        let inner = self
            .inner
            .lock()
            .expect("the job registry must not be poisoned");
        inner.jobs.get(id).map(|record| view(id, record))
    }

    /// Snapshots every job known to this process, in stable id order.
    ///
    /// Ids are sequential, so the numeric suffix is the creation order
    /// (a lexicographic sort would interleave `job-10` after `job-1`).
    pub(crate) fn list(&self) -> Vec<JobView> {
        let inner = self
            .inner
            .lock()
            .expect("the job registry must not be poisoned");
        let mut views: Vec<JobView> = inner
            .jobs
            .iter()
            .map(|(id, record)| view(id, record))
            .collect();
        views.sort_by_key(|view| {
            view.id
                .trim_start_matches("job-")
                .parse::<u64>()
                .unwrap_or(u64::MAX)
        });
        views
    }
}

/// Renders a record into its snapshot.
fn view(id: &str, record: &JobRecord) -> JobView {
    JobView {
        id: id.to_string(),
        kind: record.kind,
        state: record.state,
        elapsed_secs: record.started.elapsed().as_secs(),
        summary: record.summary.clone(),
        result: record.result.clone(),
    }
}

/// Input of the `job_status` tool.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub(crate) struct JobStatusParams {
    /// The job to report (a `job-<n>` id from an async start response);
    /// omit it to list every job known to this server process.
    #[serde(default)]
    pub job_id: Option<String>,
}

/// Registers the `job_status` tool on the shared server.
#[tool_router(router = job_status_router, vis = "pub(crate)")]
impl SecondBrainServer {
    /// Check the status of asynchronous ingest/upload jobs.
    #[tool(
        description = "Check the status of asynchronous ingest/upload jobs started with \
                       async_mode=true. Pass job_id for one job; omit it to list all jobs \
                       known to this server process."
    )]
    async fn job_status(
        &self,
        Parameters(params): Parameters<JobStatusParams>,
    ) -> Result<CallToolResult, ErrorData> {
        run_job_status(self, params).await
    }
}

/// Runs one `job_status` call. With a `job_id` it reports that job; without
/// one it lists every job known to this server process. Job-status results
/// are always success results — the job's own failure lives in the status
/// text — except for an unknown id, which is an error naming the id.
async fn run_job_status(
    server: &SecondBrainServer,
    params: JobStatusParams,
) -> Result<CallToolResult, ErrorData> {
    match &params.job_id {
        Some(id) => Ok(match server.jobs.get(id) {
            Some(view) => tool_result(true, render_single(&view)),
            None => CallToolResult::error(vec![ContentBlock::text(format!(
                "Unknown job id: {id}. Jobs are kept in server memory and are cleared when \
                 the server restarts; call job_status without arguments to list known jobs."
            ))]),
        }),
        None => Ok(tool_result(true, render_list(&server.jobs.list()))),
    }
}

/// Renders one job's status: the running state carries the summary and the
/// polling instruction; a terminal state carries the recorded result text —
/// exactly what the synchronous call would have produced.
fn render_single(view: &JobView) -> String {
    let header = format!(
        "Job {} [{}] kind={} elapsed={}s",
        view.id,
        view.state.as_str(),
        view.kind.as_str(),
        view.elapsed_secs
    );
    match &view.result {
        Some((_, text)) => format!("{header}\n{text}"),
        None => format!(
            "{header}\n{}\nPoll again with job_status to check completion.",
            view.summary
        ),
    }
}

/// Renders the no-argument listing: one line per job, oldest first, or the
/// empty-registry sentence.
fn render_list(views: &[JobView]) -> String {
    if views.is_empty() {
        return "No jobs have been started since the server started.".to_string();
    }
    views
        .iter()
        .map(|view| {
            // The summary is one line by construction; the first-line cut
            // keeps the listing one line per job even so.
            let summary = view.summary.lines().next().unwrap_or("");
            format!(
                "[{}] {} kind={} elapsed={}s {}",
                view.state.as_str(),
                view.id,
                view.kind.as_str(),
                view.elapsed_secs,
                summary
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;
    use std::time::Duration;

    /// Finishes every id in `ids` with the same (success, text).
    fn finish_all(registry: &JobRegistry, ids: &[String], success: bool) {
        for id in ids {
            registry.finish(id, success, format!("result of {id}"));
        }
    }

    #[test]
    fn created_jobs_get_sequential_ids_and_start_running() {
        let registry = JobRegistry::new();
        let first = registry.create(JobKind::Ingest, "ingest report.txt");
        let second = registry.create(JobKind::Upload, "upload sample.txt");
        let third = registry.create(JobKind::Ingest, "ingest docs");

        assert_eq!(first, "job-1");
        assert_eq!(second, "job-2");
        assert_eq!(third, "job-3");

        let view = registry.get("job-2").expect("the created job must exist");
        assert_eq!(view.kind, JobKind::Upload);
        assert_eq!(view.state, JobState::Running);
        assert_eq!(view.summary, "upload sample.txt");
        assert!(
            view.result.is_none(),
            "a running job carries no terminal result"
        );
    }

    #[test]
    fn an_unknown_id_is_not_found_and_the_registry_starts_empty() {
        let registry = JobRegistry::new();
        assert!(registry.get("job-1").is_none(), "a fresh registry is empty");
        assert!(registry.get("job-99").is_none());
        assert!(registry.list().is_empty());

        registry.create(JobKind::Ingest, "ingest report.txt");
        assert!(
            registry.get("job-99").is_none(),
            "an id that was never issued is unknown"
        );
    }

    #[test]
    fn finishing_records_the_terminal_state_and_the_recorded_text() {
        let registry = JobRegistry::new();
        let id = registry.create(JobKind::Ingest, "ingest report.txt");

        registry.finish(
            &id,
            false,
            "the secondbrain CLI failed with exit code 1".into(),
        );
        let view = registry.get(&id).expect("the finished job must exist");
        assert_eq!(view.state, JobState::Failed);
        assert_eq!(
            view.result,
            Some((
                false,
                "the secondbrain CLI failed with exit code 1".to_string()
            ))
        );

        // A second finish is a no-op: the first recorded outcome stands.
        registry.finish(&id, true, "ingest summary".into());
        let view = registry.get(&id).expect("the finished job must exist");
        assert_eq!(view.state, JobState::Failed, "the first outcome stands");
        assert_eq!(
            view.result,
            Some((
                false,
                "the secondbrain CLI failed with exit code 1".to_string()
            ))
        );
    }

    #[test]
    fn finishing_on_an_unknown_id_is_a_no_op() {
        let registry = JobRegistry::new();
        registry.finish("job-1", true, "orphan finish".into());
        assert!(
            registry.get("job-1").is_none(),
            "a finish for an unknown id must not create anything"
        );
    }

    #[test]
    fn finished_jobs_are_evicted_oldest_first_beyond_the_bound() {
        let registry = JobRegistry::new();
        let ids: Vec<String> = (0..FINISHED_RETENTION as u64 + 5)
            .map(|_| registry.create(JobKind::Ingest, "ingest report.txt"))
            .collect();
        finish_all(&registry, &ids, true);

        assert_eq!(
            registry.list().len(),
            FINISHED_RETENTION,
            "the finished tail is capped at the retention bound"
        );
        // The oldest five are evicted, the newest hundred stay.
        for evicted in ids.iter().take(5) {
            assert!(
                registry.get(evicted).is_none(),
                "{evicted} must be evicted oldest-first"
            );
        }
        for kept in ids.iter().skip(5) {
            assert!(registry.get(kept).is_some(), "{kept} must be retained");
        }
    }

    #[test]
    fn running_jobs_are_never_evicted_even_when_finished_ones_are() {
        let registry = JobRegistry::new();
        // Far more running jobs than the finished bound: none may be evicted.
        let running: Vec<String> = (0..FINISHED_RETENTION as u64 + 50)
            .map(|_| registry.create(JobKind::Ingest, "ingest report.txt"))
            .collect();
        assert_eq!(registry.list().len(), running.len());

        // A finished tail beyond the bound is trimmed around them.
        let finished: Vec<String> = (0..FINISHED_RETENTION as u64 + 5)
            .map(|_| registry.create(JobKind::Upload, "upload sample.txt"))
            .collect();
        finish_all(&registry, &finished, true);

        for id in &running {
            let view = registry
                .get(id)
                .unwrap_or_else(|| panic!("{id} must never be evicted while running"));
            assert_eq!(view.state, JobState::Running);
        }
        let finished_kept = registry
            .list()
            .into_iter()
            .filter(|view| view.kind == JobKind::Upload)
            .count();
        assert_eq!(
            finished_kept, FINISHED_RETENTION,
            "the finished tail is capped while the running jobs stay"
        );
    }

    #[test]
    fn list_orders_jobs_by_id() {
        let registry = JobRegistry::new();
        // Ten jobs cross the lexicographic boundary (job-10 < job-2 as text):
        // the listing must stay in numeric id order.
        let ids: Vec<String> = (0..10)
            .map(|_| registry.create(JobKind::Ingest, "ingest report.txt"))
            .collect();
        // Finish in reverse order: completion order must not matter.
        for id in ids.iter().rev() {
            registry.finish(id, true, format!("result of {id}"));
        }

        let listed: Vec<String> = registry.list().into_iter().map(|view| view.id).collect();
        assert_eq!(listed, ids, "the listing must follow the id order");
    }

    #[test]
    fn elapsed_seconds_render_from_the_creation_instant() {
        let registry = JobRegistry::new();
        let id = registry.create(JobKind::Ingest, "ingest report.txt");
        thread::sleep(Duration::from_millis(20));
        let view = registry.get(&id).expect("the job must exist");
        assert!(
            view.elapsed_secs <= 1,
            "a job created ~20ms ago renders a small elapsed count: {view:?}"
        );
    }

    #[test]
    fn render_single_shows_the_running_state_and_the_polling_instruction() {
        let registry = JobRegistry::new();
        let id = registry.create(JobKind::Upload, "upload sample.txt");
        let text = render_single(&registry.get(&id).expect("the job must exist"));
        assert!(
            text.starts_with(&format!("Job {id} [running] kind=upload elapsed=")),
            "{text}"
        );
        assert!(text.contains("upload sample.txt"), "{text}");
        assert!(
            text.contains("Poll again with job_status to check completion."),
            "{text}"
        );
    }

    #[test]
    fn render_single_shows_the_recorded_result_once_terminal() {
        let registry = JobRegistry::new();
        let id = registry.create(JobKind::Ingest, "ingest report.txt");
        registry.finish(
            &id,
            true,
            "ingest summary (from the secondbrain CLI):\n…".into(),
        );
        let text = render_single(&registry.get(&id).expect("the job must exist"));
        assert!(
            text.starts_with(&format!("Job {id} [completed] kind=ingest elapsed=")),
            "{text}"
        );
        assert!(
            text.contains("ingest summary (from the secondbrain CLI):\n…"),
            "the recorded text must be carried verbatim: {text}"
        );
    }

    #[test]
    fn render_list_shows_one_line_per_job_or_the_empty_sentence() {
        assert_eq!(
            render_list(&[]),
            "No jobs have been started since the server started."
        );

        let registry = JobRegistry::new();
        let first = registry.create(JobKind::Ingest, "ingest report.txt");
        let second = registry.create(JobKind::Upload, "upload sample.txt");
        registry.finish(&second, false, "boom".into());

        let listed = render_list(&registry.list());
        let lines: Vec<&str> = listed.lines().collect();
        assert_eq!(lines.len(), 2, "one line per job: {listed}");
        assert!(
            lines[0].starts_with(&format!("[running] {first} kind=ingest elapsed="))
                && lines[0].ends_with("ingest report.txt"),
            "the running line carries state, id, kind, elapsed, summary: {listed}"
        );
        assert!(
            lines[1].starts_with(&format!("[failed] {second} kind=upload elapsed="))
                && lines[1].ends_with("upload sample.txt"),
            "the failed line carries the summary, not the recorded text: {listed}"
        );
    }
}
