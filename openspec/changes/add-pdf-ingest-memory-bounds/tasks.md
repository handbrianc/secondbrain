# Bounded-Memory PDF Ingestion with GPU Acceleration — Tasks

## 1. Configuration

- [x] 1.1 Add `pdf_backend` (`pypdfium` | `docling-parse`, default `pypdfium`),
  `pdf_max_pages_per_convert` (int ≥ 0, default 200),
  `pdf_pipeline_queue_max_size` (int ≥ 1, default 16), and
  `accelerator_min_free_ram_mib` (int ≥ 0, default 2048) to
  `src/secondbrain/config/processing.py`, with validators and docstrings; all
  four read as `SECONDBRAIN_*` env vars like the existing `pdf_*` fields.

- [x] 1.2 Wire the previously validation-only `embedding_dtype`
  (`src/secondbrain/config/processing.py:74`) into actual use: embeddings are
  produced, accumulated, transported, and stored as `float32` when the value
  is `float32` (only supported value for now; keep validating, raise a clear
  error for unsupported values).

## 2. Backend selection and accelerator hardening (`document/docling_factory.py`)

- [x] 2.1 Thread `cfg.pdf_backend` through `_build_pdf_format_option`: map
  `pypdfium` → `docling.backend.pypdfium2_backend.PyPdfiumDocumentBackend`,
  `docling-parse` → current default (threaded docling-parse backend). Same
  `PdfPipelineOptions` for both.

- [x] 2.2 Pass `queue_max_size=cfg.pdf_pipeline_queue_max_size` into the
  pipeline options (docling 2.138 supports it,
  `docling/datamodel/pipeline_options.py:2297`).

- [x] 2.3 When `decide_device(cfg.pdf_accelerator_device)` resolves to `xpu`,
  set `SYCL_CACHE_PERSISTENT=1` and a `SYCL_CACHE_DIR` under the secondbrain
  cache root (os.environ.setdefault, before docling/torch import — mirror the
  existing `HF_HUB_*` setdefault pattern at `docling_factory.py:295-298`).

- [x] 2.4 Extend `_preflight_accelerator_device`: after device resolution,
  when the device shares system RAM (xpu on integrated GPU) and free host
  memory < `accelerator_min_free_ram_mib`, log a warning naming the device,
  measured headroom, and `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` as the
  fallback. Never raise.

## 3. Windowed conversion and artifact release (`document/processor.py`)

- [x] 3.1 In `_extract_chunk_and_embed_file`, replace the single
  `converter.convert(file_path)` with a page-window loop:
  `pdf_page_count(file_path)` → windows of `pdf_max_pages_per_convert` pages
  (`0` or count ≤ window → one whole-document convert, exactly today's path);
  convert each range with `converter.convert(file_path, page_range=(start,
  end))`; extend `segments` per window.

- [x] 3.2 Release artifacts per window and after the final one: `del`
  `result`/`content` after segments are built, call
  `result.input._backend.unload()` when available, `gc.collect()`; verify
  against docling's unload contract (upstream docling #2209 workaround).

- [x] 3.3 Keep progress correct across windows: page ticks
  (`_emit_extract`) advance continuously over the concatenated windows; the
  docling DEBUG page-batch scraper (`scrape_docling_pages`) keeps working
  (its counters are per-conversion — emit offsets per window).

- [x] 3.4 Fast-path interplay: `try_fast_pdf_extraction` behavior is
  unchanged (windowing applies only on the docling path).

## 4. Compact embedding transport

- [x] 4.1 `_embed_unique_chunks` (`processor.py:377-415`) returns
  `numpy.ndarray` rows of `float32` (per `cfg.embedding_dtype`) instead of
  lists of Python floats; provider batches unchanged.

- [x] 4.2 Parent-side store path: `MAX_MEMORY_BATCH_SIZE` slices in
  `document/ingestor/_sync.py:1005-1024` and
  `storage/qdrant.py:326` (`vector=...`) accept array vectors (qdrant-client
  1.19 accepts them); no per-chunk list copies at the boundary.

- [x] 4.3 Confirm the worker→parent pickle of the result carries arrays
  (≈6 KB/chunk at 1536 dims vs ≈49 KB today) and that `EmbeddingCache`
  round-trips arrays correctly (thread-pool path shares it,
  `_sync.py:916`).

## 5. Tests

- [x] 5.1 Config tests: new fields validated (invalid `pdf_backend` rejected;
  bounds for window/queue/min-ram; env-var forms).
- [x] 5.2 `tests/test_document/test_docling_factory.py`: backend mapping
  (`pypdfium`/`docling-parse` produce the configured backend class,
  identical pipeline options), `queue_max_size` passthrough, SYCL cache env
  set only when device resolves to xpu, preflight warning emitted/not emitted
  (mock free-RAM).
- [x] 5.3 Windowed conversion unit tests with a fake converter: window math
  (edge cases: pages == window, pages == window+1, window=0, page_range
  values), segment merge equality vs whole-document conversion, artifact
  release called per window, continuous progress ticks.
- [x] 5.4 Embedding transport tests: `_embed_unique_chunks` returns arrays of
  the configured dtype; store path accepts arrays; stored vector equals
  float32-rounded provider values; pickle size regression test asserting the
  compact form.
- [x] 5.5 Mocked end-to-end single-large-PDF ingest (extend
  `tests/integration/mocked/test_end_to_end.py`): multipage fake PDF through
  the real CLI ingest path with windowing active; success counts unchanged.

## 6. Manual verification (reference deployment)

- [x] 6.1 On the 6 GB host with Intel Arc iGPU: ingest
  `/home/bchand/UserManual.pdf` (1200 pages) with defaults; record peak worker
  RSS (guard at 4.5 GiB tree), completion, and stored-chunk count; verify free
  memory never approaches zero. Target: device-scoped budget per spec
  (~3 GiB cpu, ~3.5 GiB with shared-RAM XPU active).
  Done (2026-10-20): completed rc=0 — worker peak 3376 MiB, tree peak
  4162 MiB (store-phase transient over a flat 3963 MiB conversion plateau,
  zero per-window growth across six 200-page windows), 710 s cold / 166 s
  with warm on-disk SYCL JIT cache, 12,593 chunks stored. Host never
  approached OOM; guard never fired. Embedding values from a local
  OpenAI-compatible stub (user's remote provider was unreachable); transport
  and storage fully exercised.
- [x] 6.2 Repeat with `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` and record the
  delta; repeat with `SECONDBRAIN_PDF_BACKEND=docling-parse`
  `SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT=0` to confirm legacy behavior is
  still reachable.
  Done (2026-10-20): cpu run completed rc=0 — peak tree 3136 MiB, worker
  ~2.43 GiB, 1029 s (vs XPU: 4162 MiB tree / 3.3 GiB worker / 166 s) → the
  shared-RAM XPU adds ~0.9 GiB on the bounded path, well under the device
  budgets. Legacy leg (`docling-parse`, windowing off) reached the same
  unbounded-growth signature as the pre-fix default (4938 MiB tree within
  8.5 s of conversion start) and was stopped by the guard — legacy knob is
  reachable and reproduces the documented pathology on this reference PDF.
- [ ] 6.3 Spot-check retrieval quality of the ingested manual (search hits on
  known page content) to confirm the pypdfium backend's fidelity is
  acceptable for the corpus; document any regressions found.
  Blocked externally (2026-10-20): the user's remote embedding provider
  (LiteLLM proxy) was unreachable, so no semantically meaningful vectors
  exist to search; a stub-hash provider proves transport but not retrieval
  quality. Run after the provider is reachable: ingest with real embeddings
  against a test collection, then 2–3 known-page-content search queries.

## 7. Documentation

- [x] 7.1 `docs/getting-started/troubleshooting.md`: new "PDF ingestion uses
  too much memory" section — the four causes, the new knobs
  (`SECONDBRAIN_PDF_BACKEND`, `SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT`,
  `SECONDBRAIN_PDF_PIPELINE_QUEUE_MAX_SIZE`,
  `SECONDBRAIN_ACCELERATOR_MIN_FREE_RAM_MIB`,
  `SECONDBRAIN_PDF_ACCELERATOR_DEVICE`), and measured reference numbers.
- [x] 7.2 Config reference: document the five new/changed settings
  (defaults, accepted values, when to change them).
