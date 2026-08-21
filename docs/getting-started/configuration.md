# Configuration Guide

SecondBrain uses environment variables prefixed with `SECONDBRAIN_` for all configuration. This follows 12-factor app
principles for consistent, production-ready settings management.

## Quick Configuration

Create a `.env` file in your project root:

```bash
# Storage backend (qdrant or mock)
SECONDBRAIN_STORAGE_BACKEND=qdrant

# Vector database: Qdrant
SECONDBRAIN_QDRANT_URL=http://localhost:6333
SECONDBRAIN_QDRANT_API_KEY=
SECONDBRAIN_QDRANT_COLLECTION=embeddings

# Conversations/sessions: SQLite
SECONDBRAIN_SQLITE_PATH=~/.secondbrain/secondbrain.db

# Embedding provider
SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_EMBEDDING_API_KEY=your-api-key

# Document processing
SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
SECONDBRAIN_DEFAULT_TOP_K=20
```

## Configuration Loading Order

SecondBrain loads configuration in the following priority order (highest to lowest):

1. Environment variables
2. `.env` file values
3. Hardcoded defaults

During testing (`PYTEST_CURRENT_TEST` is set), configuration additionally loads from `.env.test` with test-specific defaults.

## Core Settings

### Storage Configuration

| Variable                       | Default                     | Description                                      |
| ------------------------------ | --------------------------- | ------------------------------------------------ |
| `SECONDBRAIN_STORAGE_BACKEND`  | `qdrant`                    | Storage backend: `qdrant` (production) or `mock` |
| `SECONDBRAIN_QDRANT_URL`       | `http://localhost:6333`     | Qdrant vector database URL                       |
| `SECONDBRAIN_QDRANT_API_KEY`   | *(unset)*                   | API key for authenticated Qdrant servers         |
| `SECONDBRAIN_QDRANT_COLLECTION` | `embeddings`               | Qdrant collection for vector storage             |
| `SECONDBRAIN_SQLITE_PATH`      | `~/.secondbrain/secondbrain.db` | SQLite database path for conversations/sessions |

All chunk metadata (`chunk_id`, `source_file`, `page_number`, `chunk_text`, `element_type`, `chunk_role`,
`section_label`) is stored in the Qdrant payload. Conversations, sessions, and messages persist to SQLite.

### Embedding Settings

| Variable                           | Default                  | Description                          |
| ---------------------------------- | ------------------------ | ------------------------------------ |
| `SECONDBRAIN_EMBEDDING_PROVIDER`   | `openai`                 | Provider type (openai or compatible) |
| `SECONDBRAIN_EMBEDDING_MODEL`      | `text-embedding-3-small` | Model name                           |
| `SECONDBRAIN_EMBEDDING_DIMENSIONS` | `1536`                   | Vector dimensionality                |
| `SECONDBRAIN_EMBEDDING_API_KEY`    | `None`                   | API key for provider                 |
| `SECONDBRAIN_EMBEDDING_API_BASE`   | `None`                   | Custom endpoint base URL             |
| `SECONDBRAIN_EMBEDDING_CACHE_SIZE` | `1000`                   | LRU cache size (0 disables)          |
| `SECONDBRAIN_EMBEDDING_BATCH_SIZE` | `100`                    | Batch size (1-100)                   |

### LLM Configuration (for RAG chat)

| Variable                      | Default       | Description                       |
| ----------------------------- | ------------- | --------------------------------- |
| `SECONDBRAIN_LLM_PROVIDER`    | `openai`      | Provider type (openai, anthropic) |
| `SECONDBRAIN_LLM_MODEL`       | `gpt-4o-mini` | Model name                        |
| `SECONDBRAIN_LLM_TEMPERATURE` | `0.1`         | Generation temperature (0.0-2.0)  |
| `SECONDBRAIN_LLM_MAX_TOKENS`  | `2048`        | Maximum response tokens           |
| `SECONDBRAIN_LLM_TIMEOUT`     | `120`         | Request timeout in seconds        |
| `SECONDBRAIN_OPENAI_BASE_URL` | `None`        | OpenAI-compatible API base URL    |

### Document Processing

Docling PDF parsing exposes several speed levers, all **off / preserving current
behavior by default**. Enable a lever only when you want the corresponding speed
or behavior change:

- `pdf_accelerator_device` / `pdf_num_threads` — select the docling inference
  device (`auto`, `cpu`, `mps`, `cuda`) and thread count.
- `pdf_threaded_pipeline` / `pdf_layout_batch_size` — use docling's threaded/batched
  PDF pipeline instead of the default, and set the layout-model batch size.
- `pdf_generate_page_images` / `pdf_generate_picture_images` / `pdf_images_scale` —
  render page/picture images during parsing (unused for storage; disabled for speed).

| Variable                                    | Default              | Description                                                          |
| ------------------------------------------- | -------------------- | -------------------------------------------------------------------- |
| `SECONDBRAIN_CHUNK_SIZE`                    | `4096`               | Target chunk size in characters                                      |
| `SECONDBRAIN_CHUNK_OVERLAP`                 | `50`                 | Overlap between chunks                                               |
| `SECONDBRAIN_SUPPORTED_EXTENSIONS`          | (comprehensive list) | Comma-separated file extensions                                      |
| `SECONDBRAIN_MAX_FILE_SIZE_BYTES`           | `104857600`          | Maximum file size (100MB)                                            |
| `SECONDBRAIN_PDF_OCR_ENABLED`               | `false`              | Run OCR on PDFs (`pdf_ocr_enabled`). `false` = OCR only when the PDF has no embedded text layer (scanned); `true` = always OCR all PDFs |
| `SECONDBRAIN_PDF_FAST_TEXT_ENABLED`         | `true`               | Skip docling's layout/OCR models for PDFs that have a native text layer, extracting text with pypdfium2 directly (`pdf_fast_text_enabled`). Falls back to the full docling pipeline when the PDF has no/insufficient native text (scanned/empty). Ignored when `SECONDBRAIN_PDF_OCR_ENABLED=true` |
| `SECONDBRAIN_PDF_TABLE_STRUCTURE_ENABLED`   | `false`              | Detect table structure in PDFs (`pdf_table_structure_enabled`). Disabled by default for speed; set `true` to enable |
| `SECONDBRAIN_PDF_TABLE_FAST_MODE`           | `true`               | When table structure is enabled, use TableFormer 'fast' mode instead of the slower, more accurate mode (`pdf_table_fast_mode`) |
| `SECONDBRAIN_PDF_TABLE_CELL_MATCHING`       | `false`              | Enable docling table cell matching (post-processing); disabled by default for speed and OCR compatibility (`pdf_table_cell_matching`) |
| `SECONDBRAIN_PDF_ACCELERATOR_DEVICE`        | `auto`               | Docling accelerator device: `auto` \| `cpu` \| `mps` \| `cuda` (`pdf_accelerator_device`) |
| `SECONDBRAIN_PDF_NUM_THREADS`               | `4`                  | Threads for docling inference, must be >= 1 (`pdf_num_threads`)      |
| `SECONDBRAIN_PDF_THREADED_PIPELINE`         | `false`              | Use docling's threaded/batched PDF pipeline instead of the default (`pdf_threaded_pipeline`) |
| `SECONDBRAIN_PDF_LAYOUT_BATCH_SIZE`         | `4`                  | Layout-model batch size for the threaded pipeline, must be >= 1; only used when `pdf_threaded_pipeline` is true (`pdf_layout_batch_size`) |
| `SECONDBRAIN_PDF_GENERATE_PAGE_IMAGES`      | `false`              | Render full-page images during parsing; unused for storage, disabled for speed (`pdf_generate_page_images`) |
| `SECONDBRAIN_PDF_GENERATE_PICTURE_IMAGES`   | `false`              | Render embedded picture images during parsing; unused for storage, disabled for speed (`pdf_generate_picture_images`) |
| `SECONDBRAIN_PDF_IMAGES_SCALE`              | `1.0`                | Rendering scale for generated images, must be > 0 (`pdf_images_scale`) |

### Search Settings

| Variable                    | Default | Description                             |
| --------------------------- | ------- | --------------------------------------- |
| `SECONDBRAIN_DEFAULT_TOP_K` | `50`    | Default number of search results        |
| `MIN_SCORE`                 | `0.46`  | Minimum similarity threshold (constant) |

## Advanced Settings

### RAG/Pipeline Settings

| Variable                                   | Default | Description                                                                                                                                                                            |
| ------------------------------------------ | ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SECONDBRAIN_RAG_CONTEXT_WINDOW`           | `5`     | Recent messages in conversation context                                                                                                                                                |
| `SECONDBRAIN_RAG_MAX_RETRIES`              | `3`     | Maximum LLM retry attempts                                                                                                                                                             |
| `SECONDBRAIN_RAG_LLM_FALLBACK_ENABLED`     | `true`  | When no documents are found in the vector DB, allow the LLM to answer from its own knowledge if it has any                                                                             |
| `SECONDBRAIN_RAG_MIN_SIMILARITY_THRESHOLD` | `0.46`  | Minimum cosine-similarity score for a retrieved chunk to count as relevant context in the RAG/chat path; chunks below this trigger the LLM-knowledge fallback (same as the search CLI) |
| `SECONDBRAIN_RAG_MAX_CONTEXT_CHARS`        | `16000` | Maximum context characters                                                                                                                                                             |
| `SECONDBRAIN_RAG_CHUNK_PREVIEW_CHARS`      | `1200`  | Per-chunk preview length                                                                                                                                                               |
| `SECONDBRAIN_STREAMING_ENABLED`            | `true`  | Enable streaming processing                                                                                                                                                            |
| `SECONDBRAIN_STREAMING_CHUNK_BATCH_SIZE`   | `150`   | Streaming batch size (1-200)                                                                                                                                                           |

### Performance Settings

| Variable                                | Default | Description                             |
| --------------------------------------- | ------- | --------------------------------------- |
| `SECONDBRAIN_MAX_WORKERS`               | `None`  | Worker processes (auto-detect if unset) |
| `SECONDBRAIN_MAX_INGEST_PROCESSES`      | `0`     | Cap on AUTO-detected process-pool workers (`max_ingest_processes`); `0` = unlimited/auto. Explicit `--cores` or configured `max_workers` always win |
| `SECONDBRAIN_INGEST_POOL`               | `process` | Pool type for CPU-bound extraction (`ingest_pool`): `process` (multicore, default) or `thread` |
| `SECONDBRAIN_SKIP_EXISTING_ON_REINGEST` | `true`  | Skip re-embedding and re-storing chunks whose text hash already exists from a previous ingest (`skip_existing_on_reingest`) |
| `SECONDBRAIN_RATE_LIMIT_ENABLED`        | `true`  | Enable rate limiting                    |
| `SECONDBRAIN_RATE_LIMIT_MAX_REQUESTS`   | `10`    | Requests per window                     |
| `SECONDBRAIN_RATE_LIMIT_WINDOW_SECONDS` | `1.0`   | Rate limit window duration              |
| `SECONDBRAIN_INDEX_READY_RETRY_COUNT`   | `15`    | Index check retries                     |

### Storage Optimization

| Variable                                  | Default   | Description                        |
| ----------------------------------------- | --------- | ---------------------------------- |
| `SECONDBRAIN_STORAGE_COMPRESSION_ENABLED` | `true`    | Enable zstd compression            |
| `SECONDBRAIN_TEXT_COMPRESSION_ENABLED`    | `false`   | Enable text compression            |
| `SECONDBRAIN_TEXT_COMPRESSION_ALGORITHM`  | `gzip`    | Algorithm: gzip, brotli, zstd      |
| `SECONDBRAIN_EMBEDDING_DTYPE`             | `float32` | Storage precision                  |
| `SECONDBRAIN_EMBEDDING_STORAGE_FORMAT`    | `array`   | Storage format (array recommended) |

## Logging

SecondBrain follows the 12-Factor principle for logs: structured logs are written to
**stdout/stderr by default**, so a process manager or container runtime can collect them (Factor XI).
Set `SECONDBRAIN_LOG_FORMAT=json` for structured output suitable for downstream log aggregation.

**File logging is an opt-in operator choice** for long-running agents that must persist logs
beyond their process lifetime. Enable it only when you need on-disk retention:

| Variable                       | Default            | Purpose                                                          |
| ------------------------------ | ------------------ | ---------------------------------------------------------------- |
| `SECONDBRAIN_LOG_FILE`         | *(unset — stdout)* | Path to a rotating log file. When unset, logs go to stdout only. |
| `SECONDBRAIN_LOG_MAX_BYTES`    | `10485760`         | Max file size before rotation (10 MB).                           |
| `SECONDBRAIN_LOG_BACKUP_COUNT` | `5`                | Number of rotated backup files to keep.                          |

When `SECONDBRAIN_LOG_FILE` is unset, no file handler is created and all output stays on stdout,
preserving the 12-Factor delivery model.

## Configuration Validation

On startup, SecondBrain validates configuration values. Invalid configurations raise errors:

```python
# chunk_overlap must be less than chunk_size
# embedding_dimensions must be positive
# embedding_batch_size must be between 1 and 100
# ingest_pool must be one of {'process', 'thread'}
```

## Example Production Configuration

```bash
# Production .env.example
SECONDBRAIN_STORAGE_BACKEND=qdrant

SECONDBRAIN_QDRANT_URL=http://localhost:6333
SECONDBRAIN_QDRANT_API_KEY=
SECONDBRAIN_QDRANT_COLLECTION=embeddings_v2

SECONDBRAIN_SQLITE_PATH=~/.secondbrain/secondbrain.db

SECONDBRAIN_EMBEDDING_MODEL=text-embedding-3-small
SECONDBRAIN_EMBEDDING_API_KEY=$OPENAI_API_KEY
SECONDBRAIN_EMBEDDING_DIMENSIONS=1536
SECONDBRAIN_EMBEDDING_BATCH_SIZE=100

SECONDBRAIN_LLM_MODEL=gpt-4o-mini
SECONDBRAIN_LLM_PROVIDER=openai
SECONDBRAIN_LLM_MAX_TOKENS=2048
SECONDBRAIN_LLM_TIMEOUT=120

SECONDBRAIN_CHUNK_SIZE=4096
SECONDBRAIN_CHUNK_OVERLAP=50
SECONDBRAIN_DEFAULT_TOP_K=20

SECONDBRAIN_MAX_WORKERS=4
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true

SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=json
```
