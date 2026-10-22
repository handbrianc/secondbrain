# pdf-conversion Specification

## Purpose
The pdf-conversion capability covers converting PDFs into retrievable chunks: pluggable backends (docling vs pypdfium), chapter/page anchoring of chunks, device-scoped memory bounds for large documents, accelerator (XPU/CPU) selection, and the legacy knobs that keep prior behavior reachable. add-pdf-ingest-memory-bounds. Update Purpose after archive.

## Requirements

### Requirement: PDF backend is configurable with a bounded default

The system SHALL provide a `pdf_backend` configuration setting
(`SECONDBRAIN_PDF_BACKEND`) that selects the docling PDF parsing backend,
accepting `pypdfium` and `docling-parse`, and SHALL default to `pypdfium`.
Both values SHALL drive the same docling conversion pipeline (layout model,
OCR and table options unchanged); only the PDF parsing layer differs.
Invalid values SHALL be rejected at config validation with the accepted
values listed.

#### Scenario: Default backend bounds memory on a large PDF

- **WHEN** user ingests a large text-layer PDF (e.g. 1200 pages) without
  setting `SECONDBRAIN_PDF_BACKEND`
- **THEN** the conversion runs on the pypdfium backend
- **AND** the conversion completes with bounded, stable memory rather than
  growing past available RAM

#### Scenario: Explicit override restores the legacy backend

- **WHEN** `SECONDBRAIN_PDF_BACKEND=docling-parse` is set
- **THEN** the system uses docling's threaded docling-parse backend
- **AND** conversion behavior matches previous releases

#### Scenario: Invalid backend value rejected

- **WHEN** `SECONDBRAIN_PDF_BACKEND=foo` is set
- **THEN** configuration loading fails with an error naming `pypdfium` and
  `docling-parse` as the accepted values

### Requirement: Large PDFs convert in bounded page windows

The system SHALL provide a `pdf_max_pages_per_convert` configuration setting
(`SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT`, default 200, `0` disables) and,
when a PDF's page count exceeds the window size, SHALL convert it as a
sequence of sequential, non-overlapping page ranges covering each page
exactly once, releasing all conversion artifacts
(the backend page state, `ConversionResult`, and `DoclingDocument`) between
windows. Text segments SHALL be merged across windows so chunking, dedup,
embedding, and storage are unchanged; progress reporting SHALL continue
smoothly across window boundaries.

#### Scenario: 1200-page PDF converts in windows

- **WHEN** user ingests a 1200-page PDF with the default window of 200 pages
- **THEN** the document is converted in sequential windows covering all
  1200 pages exactly once
- **AND** peak memory stays near the single-window peak instead of growing
  with page count

#### Scenario: Windowing disabled restores whole-document conversion

- **WHEN** `SECONDBRAIN_PDF_MAX_PAGES_PER_CONVERT=0` is set
- **THEN** the document is converted as one unit, as in previous releases

#### Scenario: Segments merge across window boundaries

- **WHEN** a PDF is converted in more than one window
- **THEN** the produced segments cover the same text items as a
  whole-document conversion of the same backend
- **AND** no page's text is lost or duplicated at a window boundary

### Requirement: Conversion artifacts are released after use

The ingest worker SHALL release the `ConversionResult` and `DoclingDocument`
once segments are built, SHALL invoke the backend's `unload()` after each
conversion completes, and SHALL NOT retain either object through chunking,
embedding, or storage.

#### Scenario: Document structure does not outlive extraction

- **WHEN** a large PDF finishes conversion and segmentation
- **THEN** the worker's memory drops before chunking and embedding begin
- **AND** the full `ConversionResult`/`DoclingDocument` is no longer
  referenced

#### Scenario: Repeated conversions do not accumulate native memory

- **WHEN** the same worker process converts several PDFs in sequence
- **THEN** memory after each conversion returns to the pre-conversion level
  rather than stepping upward per file

### Requirement: Embeddings accumulate and transfer in fixed-width form

Embedding vectors SHALL be accumulated in the ingest worker, pickled across
the process boundary, and held by the parent as fixed-width `float32` values
(determined by the existing `embedding_dtype` setting) rather than as Python
float-object lists, and the storage layer SHALL accept them in that form.
Stored vectors and cache behavior SHALL be numerically unchanged.

#### Scenario: Large-document embeddings stay compact

- **WHEN** a single PDF produces ~9,000 chunks at 1536 dimensions
- **THEN** the worker's and the parent's embedding accumulation together
  stays below ~120 MiB (previously ~800 MiB)
- **AND** the result pickled from worker to parent shrinks proportionally

#### Scenario: Stored vectors are unchanged

- **WHEN** chunks are stored to Qdrant from compact `float32` embeddings
- **THEN** each stored vector equals the provider's returned values at
  float32 precision
- **AND** existing re-ingest skip logic (`text_hash`) is unaffected

### Requirement: GPU acceleration stays enabled within bounded memory

The `pdf_accelerator_device` setting (`SECONDBRAIN_PDF_ACCELERATOR_DEVICE`)
SHALL keep `auto` resolving to the GPU when one is available (CUDA → MPS →
XPU preference, CPU last), and the system SHALL bound the accelerator's
host-memory side effects:

- a `pdf_pipeline_queue_max_size` setting
  (`SECONDBRAIN_PDF_PIPELINE_QUEUE_MAX_SIZE`, default 16) passed to the
  pipeline, bounding pages buffered between conversion stages;
- when the resolved device is XPU, the SYCL JIT program cache SHALL be
  persisted to disk (persistent cache enabled, cache directory under the
  secondbrain cache root) instead of accumulating unbounded in host RAM;
- converter preflight SHALL emit a warning — without failing — when the
  resolved device shares system RAM (integrated GPU) and free host memory is
  below `accelerator_min_free_ram_mib`
  (`SECONDBRAIN_ACCELERATOR_MIN_FREE_RAM_MIB`, default 2048), naming
  `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` as the fallback.

#### Scenario: GPU is used by default and stays usable on a small host

- **WHEN** user ingests a large PDF on a host with an Intel Arc GPU and
  6 GB RAM without device overrides
- **THEN** the layout model runs on the XPU device
- **AND** ingestion completes without out-of-memory failure

#### Scenario: Low-memory host is warned

- **WHEN** the resolved accelerator device shares system RAM and free memory
  is below the configured minimum
- **THEN** the converter build logs a warning naming the device, the
  headroom, and the CPU fallback variable
- **AND** ingestion proceeds

#### Scenario: CPU fallback removes the accelerator overhead

- **WHEN** `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` is set
- **THEN** no XPU context, weights, or JIT cache is allocated in system RAM
- **AND** conversion completes with measurably lower peak memory

### Requirement: Single large-PDF ingest completes within a host-memory budget

Ingesting a single large text-layer PDF (1000+ pages) SHALL complete on a
small host (6 GB RAM) without triggering the OOM killer or sustained swap
collapse. Using defaults on the reference deployment (1200-page PDF), the
ingest worker's peak RSS SHALL stay at or below ~3 GiB with the CPU
device, and at or below ~3.5 GiB when the GPU accelerator is active on an
integrated GPU that shares system RAM.

#### Scenario: Reference large PDF ingests successfully on a 6 GB host

- **WHEN** user runs `secondbrain ingest /path/UserManual.pdf` (1200 pages)
  with default settings on a 6 GB host with an Intel Arc GPU
- **THEN** ingestion completes: extraction, chunking, embedding, and storage
  all finish
- **AND** the worker's peak RSS stays within the device-scoped budget
  (~3 GiB on `cpu`; ~3.5 GiB with the shared-RAM GPU active)
- **AND** free system memory never approaches zero during the run

#### Scenario: Smaller PDFs are unaffected

- **WHEN** user ingests a PDF smaller than one page window
- **THEN** behavior, progress reporting, and results match a single-window
  conversion
