# DocumentIngestor Split — Implementation Plan

**Status:** Planned  
**Target:** `src/secondbrain/document/__init__.py` (2037 lines → ≤150 lines)  
**Blast Radius:** LOW — 2 direct callers: `AsyncDocumentIngestor` (extends), `cli/commands.py` (imports)

---

## Background

`DocumentIngestor` (line 529–1603, ~1075 lines) is a God class handling:
- Docling `DocumentConverter` lifecycle (heavy, eager on init)
- Text extraction from 20+ file formats
- Segment → chunk transformation (with deduplication, overlap, page-map merging)
- Batch embedding generation with in-memory `EmbeddingCache`
- Parallel processing via `ThreadPoolExecutor` and `multiprocessing`
- Storage dispatch to `VectorStorage`

`AsyncDocumentIngestor` (line 1607–2024, ~418 lines) extends it, overriding:
- `ingest_async`, `_stream_process_chunks_async`, `_store_embedding_batch_async`,
- `_build_documents_with_embeddings_async`, `_generate_embeddings_with_cache_async`

Both classes share the same `Segment` TypedDict (module-level, line 430–445).

**Critical constraint:** Docling has a 2-second cold-import cost. All docling imports are deferred
via `TYPE_CHECKING` or `try/except`. `patch_transformers_for_mps()` (line 34) must run before any
docling import and is already applied at module load.

---

## Proposed Architecture

### Module 1 — `protocols.py` (NEW, ~60 lines)
Pure abstract interfaces defining the document-processing pipeline contract.

```
Segment  — TypedDict (shared, moved here)
DocumentParsingProtocol  — ABC: parse(Path) → list[Segment]
ChunkAssemblyProtocol    — ABC: assemble(list[Segment]) → list[dict]
```

*No docling imports. No implementation.*

### Module 2 — `processor.py` (NEW, ~350 lines)
Docling converter lifecycle and segment extraction. Stateless helpers for the extraction phase.

```
convert_file(path) → list[Segment]              # replaces _extract_text
create_converter() → DocumentConverter          # lazily creates and caches
apply_mps_patch()                               # idempotent guard
```

*Applies `patch_transformers_for_mps()` on module load (idempotent).*
*Lazy docling imports inside function bodies.*

### Module 3 — `chunker.py` (NEW, ~200 lines)
Pure synchronous transformations. Zero docling, zero network, zero storage deps.

```
DEFAULT_MIN_SEGMENT_SIZE = 200
chunk_segments(segments, chunk_size, overlap) → list[dict]   # refactored from _chunk_segments
deduplicate_segments(segments) → list[dict]                   # refactored from _deduplicate_and_chunk_segments
merge_chunks_with_page_map(chunks, page_map) → list[dict]     # identity if not implemented
```

### Module 4 — `async_ingestor.py` (NEW, ~450 lines)
`AsyncDocumentIngestor` refactored into a standalone file. Preserves all async overrides.

```
class AsyncDocumentIngestor      # moved verbatim from __init__.py
```

Imports `DocumentIngestor` for inheritance; inherits all chunking/storage delegation methods.

### Module 5 — `__init__.py` (REFACTORED, ≤150 lines)
Thin facade wiring `DocumentIngestor` to the new modules. Re-exports the full `__all__` contract
unchanged.

```
DocumentIngestor  — class, shrinks to delegation stubs
SUPPORTED_EXTENSIONS, is_supported, get_file_type  — remain here (file-type utilities)
EmbeddingCache  — imported from utils.embedding_cache
VectorStorage   — imported from storage
Segment         — imported from protocols
config, patch_transformers_for_mps, trace_operation  — kept here
```

Backward-compat shim: `__getattr__` lazy-imports `AsyncDocumentIngestor` from `async_ingestor`
to avoid circular imports during transition.

---

## Wave Details

### Wave 1 — Scaffold + Characterization Tests

**Goal:** Create placeholder modules that re-export existing code unchanged; write tests that pin current behavior.

1. **Create `protocols.py`** — define `Segment` TypedDict (copy from `__init__.py:430–445`), add empty ABC stubs.
2. **Create `processor.py`** — copy the `_extract_and_chunk_file` and `_extract_chunk_and_embed_file` workers; add lazy docling import guards.
3. **Create `chunker.py`** — copy `_chunk_segments` and `_deduplicate_and_chunk_segments`.
4. **Update `__init__.py`** — add `from secondbrain.document.protocols import Segment` etc.; wire via assignment so `__all__` is unchanged.
5. **`__all__` stays identical** — `DocumentIngestor`, `AsyncDocumentIngestor`, `Segment`, `is_supported`, `get_file_type`, `SUPPORTED_EXTENSIONS`, `DocumentExtractionError`, `UnsupportedFileError`.
6. **Write characterization tests** in `tests/test_document/test_split_characterization.py` that assert:
   - `chunk_segments([{"text":"","page":1}], ...)` produces expected output shape
   - `Segment` dict has `text: str` and `page: int` keys
   - `is_supported(Path("file.pdf")) == True`
   - `get_file_type(Path("file.docx")) == "docx"`
   - Import paths resolve correctly

**Exit criterion:** `pytest tests/test_document/ -x` passes with same coverage as HEAD.

---

### Wave 2 — Migration (Implementation into New Modules)

**Goal:** Move real implementation into modules; shrink `__init__.py`.

1. **`processor.py`** gets the `DocumentConverter` singleton creation and `_extract_text` logic.
   - Expose `converter_from_config()` factory function
   - Keep lazy docling import discipline

2. **`chunker.py`** gets `_chunk_segments` algorithm (pure, no state) and deduplication logic.
   - Export `chunk_segments(segments, chunk_size, overlap) -> list[dict]`
   - Export `deduplicate_segments(segments, file_path) -> list[dict]` (file_path in metadata)

3. **`DocumentIngestor.__init__`** — inject `processor` and `chunker` instances; delegate to them.
   - `self._extract_text = lambda path: processor.extract_segments(path)`
   - `self._deduplicate_and_chunk_segments = lambda fp, segs: chunker.deduplicate(fp, segs)`

4. **`__init__.py`** removes migrated code (~900 lines removed).

**Exit criterion:** Same tests pass; `ruff check src/secondbrain/document/` clean.

---

### Wave 3 — AsyncIngestor + Facade Polish

**Goal:** Extract `AsyncDocumentIngestor` cleanly; finalize `__init__.py` facade.

1. Copy `AsyncDocumentIngestor` body into `async_ingestor.py` verbatim.
2. In `async_ingestor.py`, add import: `from secondbrain.document import DocumentIngestor`.
3. In `__init__.py`, add `from secondbrain.document.async_ingestor import AsyncDocumentIngestor`.
4. Verify `DocumentIngestor` still subclasses `AsyncDocumentIngestor` if inheritance chain matters for CLI
   (it does — `cli/commands.py` instantiates `DocumentIngestor` directly).

**Facade goal:** `DocumentIngestor` becomes ≤150 lines of initialization + delegation wiring only.

---

### Wave 4 — Cleanup

**Goal:** Deleted code gone; final verification.

1. Confirm `document/__init__.py` line count ≤ 150.
2. Confirm no duplicate symbol definitions.
3. Run full quality gate: `ruff check . && ruff format . && mypy . && pytest tests/test_document/ -x`.

---

## Backward Compatibility Contract

| Old Import | New Import Path | Status |
|---|---|---|
| `from secondbrain.document import DocumentIngestor` | unchanged | ✓ preserved |
| `from secondbrain.document import AsyncDocumentIngestor` | unchanged | ✓ preserved |
| `from secondbrain.document import Segment` | unchanged (now from protocols) | ✓ preserved |
| `from secondbrain.document import is_supported` | unchanged | ✓ preserved |
| `from secondbrain.document import get_file_type` | unchanged | ✓ preserved |

The `__all__` list never changes order or membership during waves 1–3. Only internal file organization changes.

---

## Key Constraints During Migration

1. **Never rename public symbols** (`DocumentIngestor`, `AsyncDocumentIngestor`, `Segment`, `is_supported`, `get_file_type`) until wave 4 cleanup.
2. **Keep `__all__` stable** — every wave must export the same public API.
3. **`patch_transformers_for_mps()`** is applied once in `processor.py` module-init guard.
4. **Docling lazy-loading** stays intact — never `import docling` at module level.
5. **EmbeddingCache** stays in `utils/embedding_cache.py`; `DocumentIngestor` holds an instance as `self.embedding_cache`.
6. **`_extract_text`** returns `list[Segment]`, same as today.
7. **`_process_file_for_storage`** signature unchanged.

---

## Verification Gates

Every wave concludes with:

```bash
ruff check src/secondbrain/document/ && ruff format --check src/secondbrain/document/
mypy src/secondbrain/document/
pytest tests/test_document/ -x -q
```

No wave may increase error/warning count. If gate fails, wave is reverted before proceeding.

---

## File Inventory

| File | Fate |
|---|---|
| `src/secondbrain/document/__init__.py` | Shrinks from 2037 → ≤150 lines |
| `src/secondbrain/document/protocols.py` | NEW — interfaces + Segment |
| `src/secondbrain/document/processor.py` | NEW — docling lifecycle, extraction |
| `src/secondbrain/document/chunker.py` | NEW — pure chunk/dedupe transforms |
| `src/secondbrain/document/async_ingestor.py` | NEW — AsyncDocumentIngestor |
| `tests/test_document/test_split_characterization.py` | NEW — behavioral pinning tests |

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Circular import: `async_ingestor → document → async_ingestor` | Low | `__getattr__` lazy import in `__init__.py` |
| `DocumentIngestor` inheriting from `AsyncDocumentIngestor` breaks | Medium | Keep inheritance chain intact; only relocate code |
| Thread-pool workers in `_process_parallel_with_progress` rely on module-level state | Medium | Ensure workers stay unpicklable-safe; test parallel tests |
| Characterization tests miss edge-case behavior | Medium | Cover: empty segments, title-merging, overlap math, dedup hashes |

---

## Order of Operations

```
Wave 1: scaffold          → files exist, all tests green, zero behaviour change
Wave 2: migrate impl      → real code moves, still re-exported from __init__.py
Wave 3: async extraction  → AsyncDocumentIngestor lands in own file
Wave 4: shrink __init__   → delete dead code, final gate
```