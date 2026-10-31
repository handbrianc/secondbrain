# Proposal

## Why

A 2026-10-29 chat session against the Proxmox VE admin guide silently answered from
the wrong document and carried invisible infrastructure stalls. Post-mortem evidence:
an unscoped numbered-chapter query resolved its target document by a max-body-chunk
heuristic (`_pipeline.py:468-475`), so the 12,051-point VirtualBox manual outranked
the 7,314-point Proxmox guide; `chapter_id "15"` collides across sources (High
Availability vs VBoxManage); the stored tree's only numbered chapter nodes are ToC-page
ghosts (`1 Introduction` pp. 3–8, `7 Proxmox VE Storage` pp. 9–22) while the real
chapters 7/10/20 are number-less, so runtime number recovery cannot fix what capture
polluted; and a 9.9-second audio clip took 6m48s with the chat silent from 04:32:57 to
04:39:44, zero Qdrant requests in that window, and no default file log to attribute the
gap (`setup_logging` only writes a file when `SECONDBRAIN_LOG_FILE` is set). Four
integrity gaps remain uncovered by the two implemented (unarchived) changes
`fix-chapter-bucket-sampling` and `fix-chunk-heading-context`.

## What Changes

- **Per-source chapter resolution (query side)**: numbered chapter/section requests
  against stored trees SHALL resolve per-source. With multiple sources defining the
  same number and no source mention in the query, the pipeline produces per-source
  results or an explicit ambiguity prompt — it no longer silently picks one document
  by chunk-count heuristic. A resolved source mention scopes resolution to that
  source.
- **Cross-source window purity + attribution (query side)**: a chapter/section
  summary window contains chunks from exactly one source; multi-source answers
  attribute each part to its source.
- **ToC-ghost suppression at capture**: heading candidates lying on a document's ToC
  page span SHALL NOT become chapter/section nodes at capture time (today the runtime
  chapter-map guard filters them per query; the polluted tree itself stays wrong).
- **Physically-consistent number recovery (capture side)**: recovered chapter numbers
  map printed ToC page numbers through the document's page labels and are assigned
  only to nodes whose physical page range is consistent with the mapped listing page
  within a bounded tolerance; ambiguous assignments are refused.
- **Audio ingest stage observability + coherent worker wait bound**: each ingest
  stage (decode, transcription, segmentation, chunking, embedding) logs duration and
  outcome; the transcription worker wait bound derives from worst-case stage work
  instead of expiring mid-progress (observed: 300 s `future.result` bound vs a 408 s
  successful transcription).
- **New capability `service-observability`**: the CLI attaches a size-rotating file
  log under the user's data directory by default, and external service calls (LLM,
  embeddings, vector store) log a WARNING with operation and elapsed time past a
  configured threshold — a silent multi-minute stall becomes attributable without
  reproducing it under a debug env var.

## Capabilities

### New Capabilities

- `service-observability`: default rotating file log plus threshold-based slow-call
  WARNING logging for external service calls.

### Modified Capabilities

- `rag-pipeline`: ADDED requirements "Per-source resolution of numbered chapter and
  section queries" and "Cross-source window purity and attribution". Framed as ADDED:
  the existing "Chapter windows admit only in-range source chunks" covers page-range
  purity within one document; neither it nor any existing requirement constrains
  source scoping of chapter resolution in multi-source collections.
- `document-structure`: ADDED requirement "ToC-page heading suppression at capture";
  MODIFIED requirement "Chapter numbering recovery from ToC listings" (page-label
  mapping, physical-page consistency bound, collision refusal). The existing
  "Audio anchors" requirement is untouched.
- `document-ingestion`: ADDED requirements "Audio ingest stage observability" and
  "Transcription worker wait bound". Framed as ADDED: no existing requirement governs
  ingest-stage logging or worker wait bounds; "Document Ingestion" and "File Type
  Detection" stay as-is.

## Impact

- **Code**: `src/secondbrain/rag/pipeline/_pipeline.py` (unscoped max-chunk
  document pick, legacy path), `src/secondbrain/rag/pipeline/_structure_mixin.py`
  (chapter resolution/window assembly), `src/secondbrain/document/structure_capture.py`
  (heading capture, `recover_chapter_numbers`), `src/secondbrain/document/ingestor/_sync.py`
  and `_async.py` (audio path stage logging, worker wait), `src/secondbrain/logging/__init__.py`
  + `src/secondbrain/cli/__init__.py` (default rotating file log), and a small
  slow-call instrumentation helper applied at LLM/embedding/vector-store call sites.
  Tests under `tests/unit/`.
- **Data**: no live re-ingest is required for verification; tests and fixtures only.
  The user's existing trees keep their polluted nodes until a backfill re-ingest
  (runtime guard from the archived `fix-chapter-coverage` change continues to shield
  query-side behavior meanwhile).
- **Dependencies**: none added.
- **Spec interplay**: complements the archived runtime guard (query side) with a
  capture-side fix; overlaps no requirement of the two in-flight changes
  (`fix-chapter-bucket-sampling`, `fix-chunk-heading-context`).
- **No breaking changes**: CLI flags, stored schemas, and APIs unchanged; behavior
  changes are corrections plus additive logging.
