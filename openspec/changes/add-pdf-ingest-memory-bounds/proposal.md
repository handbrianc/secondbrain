# Bounded-Memory PDF Ingestion with GPU Acceleration — Proposal

## Why

Ingesting a large PDF through the CLI exhausts the host's memory. Measured on
this deployment (6 GB RAM, Intel Arc iGPU, docling 2.138.0, torch 2.14+xpu)
with the real worst case, `/home/bchand/UserManual.pdf` (1200 pages, 9.6 MB,
3.9 M chars, word-fragmented text: 65,172 docling text items):

| Path taken | Peak RSS | Outcome |
| --- | --- | --- |
| CLI default (docling-parse threaded backend, `device=auto` → XPU) | >3.7 GB within ~10–30 s, before finishing its first 4-page batch | grows unbounded; swap thrash / OOM on a 6 GB host |
| Same backend, `device=cpu` | >3.6 GB at ~4–6 s | same explosion — the backend, not the device, dominates |
| pypdfium backend, `device=cpu`, 50 pages | 2296 MiB | completed |
| pypdfium backend, `device=auto` (XPU), 50 pages | >3.6 GB at ~4 s | killed — XPU adds ≥1.3 GB (iGPU shares system RAM 1:1) |
| pypdfium backend, `device=cpu`, whole 1200-page document | 2749 MiB, plateau 2.2–2.7 GB | completed in 968 s — bounded |
| **Implemented change**, real CLI run, `device=auto` (XPU), windows of 200, stub embeddings | tree 3851 MiB (worker 3398 MiB), flat plateau from 186 s | completed in 710 s — six 200-page windows, zero per-window growth; SYCL JIT cache persisted to disk (914 MB) |

Four independent causes stack up:

1. **Backend**: docling 2.138's default PDF backend (threaded docling-parse)
   renders every page natively, decodes ahead, buffers up to 100 pages per
   stage queue (batches of 4), and releases native parsed-page memory only
   every 128 pages. secondbrain never overrides the backend, and for
   word-fragmented PDFs the effective native cost is tens of MB per page
   (upstream: docling #4705, #2209, #2779).
2. **Whole-document conversion**: no `page_range` windowing exists anywhere
   in secondbrain, so a 1200-page PDF converts as one unit.
3. **Retention**: the ingest worker holds the `ConversionResult`
   + `DoclingDocument` and never frees them, then builds `segments` →
   `chunks` → `unique_chunks` → `embeddings` → `documents` with nothing
   released between stages; the whole result is pickled to the parent
   (×2: marshal + unpickle) and the parent holds a full live copy while
   storing. At the deployed config (`SECONDBRAIN_CHUNK_SIZE=512`) that is
   9,111 chunks → **401 MiB of live Python-float embedding objects** in the
   worker plus ~400 MiB again in the parent.
4. **Accelerator**: `pdf_accelerator_device="auto"` (the default) resolves
   CUDA → MPS → **XPU** (docling `accelerator_utils`); on an integrated
   Intel Arc GPU there is no dedicated VRAM, so weights, the level-zero/SYCL
   runtime context, and the unbounded in-memory JIT kernel cache all count
   against system RAM (~1.3 GB measured overhead).

The correct fix keeps the GPU in use (it is wanted for layout-model speed)
while bounding every allocation that scales with document size.

## What Changes

- **Configurable PDF backend, bounded default**: new `pdf_backend` setting
  (`SECONDBRAIN_PDF_BACKEND`) with values `pypdfium` (new default) and
  `docling-parse` (today's behavior, opt back in explicitly). Both run the
  same docling layout pipeline; only the PDF parsing layer changes. Measured
  default flips the 1200-page conversion from "explodes before its first page
  batch" to a 2.75 GB bounded peak.
- **Page-window conversion**: new `pdf_max_pages_per_convert` setting
  (default 200; `0` restores whole-document conversion). PDFs larger than the
  window convert in sequential page ranges, releasing all conversion
  artifacts between windows; segments merge across windows so chunking and
  downstream behavior are unchanged. Peak RSS no longer grows with page count.
- **Conversion artifacts released**: after segments are built the worker
  deletes the `ConversionResult`/`DoclingDocument`, calls the backend's
  `unload()`, and garbage-collects — the full document structure no longer
  lives through chunking/embedding/storing, and reused converters stop
  accumulating native memory across files (upstream docling #2209 pattern).
- **Compact embedding transport**: embeddings travel through the process
  boundary and accumulate as fixed-width `float32` arrays (~6 KB per chunk)
  instead of Python float-object lists (~49 KB per chunk) — an ~8× cut to the
  worker's and parent's accumulation and to the pickle. The existing
  `embedding_dtype` setting (validated but unused today) becomes the real
  dtype; Qdrant receives vectors in the same form.
- **GPU (XPU) hardening**: `auto` keeps preferring the GPU, but (a) a new
  `pdf_pipeline_queue_max_size` setting (default 16) bounds the pages held
  between pipeline stages; (b) when the resolved device is XPU, the SYCL JIT
  program cache is persisted to disk (`SYCL_CACHE_PERSISTENT=1`) instead of
  growing unbounded in RAM; (c) converter preflight warns — loudly but
  without failing — when the resolved device shares system RAM and free
  memory is below `accelerator_min_free_ram_mib` (default 2048), naming
  `SECONDBRAIN_PDF_ACCELERATOR_DEVICE=cpu` as the fallback.

## Impact

- **New spec**: `pdf-conversion` (this change's delta is its initial spec).
  `multicore-ingestion` concurrency semantics are untouched.
- **Code**: `config/processing.py` + `config/embedding.py` (new/used fields),
  `document/docling_factory.py` (backend selection, queue bound, SYCL cache,
  preflight), `document/processor.py` (windowed conversion, artifact release,
  array embeddings), `document/ingestor/_sync.py` (result transport,
  per-batch store of arrays), `storage/qdrant.py` (accept array vectors).
- **Compatibility**: existing flags and configs keep working;
  `SECONDBRAIN_PDF_BACKEND=docling-parse` + `pdf_max_pages_per_convert=0`
  reproduces today's behavior exactly. Embedding cache keys and stored
  vectors are unchanged (same values, compact form).
- **Risks**: pypdfium backend yields leaner structure than docling-parse
  (upstream notes some fidelity differences on complex vector/table pages);
  window boundaries can split a heading or table that spans pages (upstream
  #2779) — window size is configurable, and the structure probe + fast path
  already skip docling entirely for plain text-layer PDFs. Measured fidelity
  on this deployment's corpus is the acceptance gate.
- **Measured acceptance**: the reference 1200-page PDF must complete with
  no OOM/swap collapse on a 6 GB host, with a device-scoped peak worker
  RSS budget — ≤ ~3 GiB on `cpu`, ≤ ~3.5 GiB with the XPU accelerator
  active on an integrated GPU that shares system RAM. Measured on the
  implemented change (real CLI, XPU): worker 3398 MiB, tree 3851 MiB,
  flat plateau across all six page windows.
