# Structure-Aware Ingestion — Design

## 1. Context

Verified facts this design rests on (worktree = master `8904ff4` for all
touched files; installed stack in `/home/bchand/secondbrain/.venv`):

- Query-time reconstruction is the root cause: `_iterative_query`
  (`rag/pipeline/_pipeline.py:92`, ~1400 lines) rebuilds a chapter map from
  regex scans over chunk text; placeholders come from
  `_pipeline.py:1195-1208` + `_fallback_mixin.py:566-585`; the HCD replay
  reproduces every defect exactly.
- Ingest discards structure: `processor.py:204-230` keeps only
  `text_item.text` + `prov.page_no`; `docling_factory.py:432-495` never sets
  `heading_hierarchy_options`; outline and `/PageLabels` are never read.
- `chunker.py:134-135` downgrades section-numbered headings to `body`
  (statistical path only — `_merge_segments` at 228-304 keys off
  `_is_likely_title`/`_is_section_numbered`, both text-shape heuristics, so
  role changes cannot move chunk boundaries).
- `storage/qdrant.py:45-53` indexes `chapter_id`/`section_id` (never written);
  `_point_from_document` (321-328) writes whatever keys the chunk dict
  carries, so new structural fields ride along automatically.
- Store APIs verified: `pypdfium2.PdfDocument.get_toc`,
  `pypdfium2.raw.FPDF_GetPageLabel`, docling `HeadingHierarchyOptions`
  (fields: `enabled=False, use_bookmarks=True, use_numbering=True,
  use_style=True, use_font_style=True, style_size_tolerance=0.05,
  numbering_schemes=None, max_level=6, bookmark_match_threshold=0.8`).
- Live store: Qdrant `embeddings` @ localhost:6333 (~23k points; hcd=160
  chunks all `body`; UserManual=12,593 w/ 2,160 headings; pve=7,804 w/ 2,206;
  Tampa m4a = 1 monolithic chunk); SQLite `~/.secondbrain/secondbrain.db`
  holds only `sessions`/`messages`.

## 2. Goals / non-goals

Goals: structure captured once at ingest from authoritative sources; query
time becomes a lookup; legacy regex machinery preserved untouched as fallback;
backfill without re-embedding; honest degradation everywhere.

Non-goals: hand-editing trees; deleting legacy tiers; automatic corpus-wide
re-ingest; changing legacy behavior for treeless documents (byte-identical).

## 3. Shared contract (pinned across implementation lanes)

Lanes may not change these signatures/types without reporting back; they are
the interface between ingest-side, query-side, and CLI lanes.

```python
# storage/structure_sqlite.py (self-contained: store + models)
class StructureNode(BaseModel):
    node_id: str            # deterministic: "ch05", "sec05.02", "partI.1", "seg03"
    parent_id: str | None
    kind: Literal["part", "chapter", "section", "subsection", "segment"]
    level: int              # 1 = top
    number: str | None      # "5", "5.2", "I.1"; None for unnumbered
    title: str
    page_start: int | None  # 1-based physical page (same axis as payload page_number)
    page_end: int | None    # inclusive; spans to next sibling boundary
    t_start: float | None   # seconds (audio)
    t_end: float | None
    heading_path: str       # "Chapter 1 — Installing > 1.2 > 1.2.3"

class PageLabelRange(BaseModel):
    page_start: int; page_end: int; label: str; style: str | None

class AudioSegment(BaseModel):
    seg_id: int; t_start: float; t_end: float; title: str | None

class DocumentStructure(BaseModel):
    source_file: str        # MUST equal the qdrant payload source_file string
    nodes: list[StructureNode]
    page_labels: list[PageLabelRange]
    audio_segments: list[AudioSegment]
    sources: dict[str, bool]   # {"outline":…, "heading_hierarchy":…, "page_labels":…, "audio":…}
    captured_at: str

class StructureStore(ValidatableService):   # mirrors ConversationStorage
    SCHEMA: str  # CREATE TABLE IF NOT EXISTS x4 (nodes, page_labels, audio_segments, structure_meta)
    def save_structure(self, structure: DocumentStructure) -> None          # INSERT OR REPLACE per source_file
    def load_tree(self, source_file: str) -> DocumentStructure | None       # None = no tree
    def has_tree(self, source_file: str) -> bool
    def delete_structure(self, source_file: str) -> None
    # each with an *_async twin via asyncio.to_thread
```

```python
# document/structure_capture.py
def capture_pdf_outline(path: Path) -> DocumentStructure          # pypdfium2 only
def capture_page_labels(path: Path) -> list[PageLabelRange]       # FPDF_GetPageLabel, grouped runs
def capture_docling_headings(docling_doc, path: Path) -> DocumentStructure | None
def merge_structures(*parts: DocumentStructure | None) -> DocumentStructure
def capture_structure(path: Path, docling_doc: Any = None, file_type: str = "") -> DocumentStructure | None  # dispatcher; never raises

# document/structure_annotate.py
def annotate_chunks(chunks: list[Mapping[str, Any]], tree: DocumentStructure) -> list[Mapping[str, Any]]
# adds (does not remove keys): node_id, heading_path, chapter_id, section_id, section_label
```

Ownership map (file → owning lane):

| Lane | Files |
| --- | --- |
| 1a ingest-tree | `storage/structure_sqlite.py`, `document/structure_capture.py`, `docling_factory.py`, `processor.py`, `ingestor/_sync.py`, `_async.py`, `tests` for these |
| 1b annotate+payload | `document/structure_annotate.py`, `document/chunker.py`, `storage/qdrant.py`, ingest-path payload refresh, audio capture in `structure_capture.py` |
| 2 query | `rag/pipeline/_pipeline.py`, `_structure_mixin.py`, `_fallback_mixin.py` |
| 3 CLI/docs | `cli/structure.py`, `cli/__init__.py`, `management/__init__.py`, docs/README |

## 4. Data model (SQLite, same file as conversations)

```sql
CREATE TABLE IF NOT EXISTS structure_nodes (
  source_file TEXT NOT NULL, node_id TEXT NOT NULL, parent_id TEXT,
  kind TEXT NOT NULL, level INTEGER NOT NULL, number TEXT, title TEXT NOT NULL,
  page_start INTEGER, page_end INTEGER, t_start REAL, t_end REAL,
  heading_path TEXT NOT NULL,
  PRIMARY KEY (source_file, node_id));
CREATE INDEX IF NOT EXISTS idx_structure_nodes_doc ON structure_nodes(source_file, page_start);
CREATE TABLE IF NOT EXISTS page_labels (
  source_file TEXT NOT NULL, page_start INTEGER NOT NULL, page_end INTEGER NOT NULL,
  label TEXT NOT NULL, style TEXT, PRIMARY KEY (source_file, page_start));
CREATE TABLE IF NOT EXISTS audio_segments (
  source_file TEXT NOT NULL, seg_id INTEGER NOT NULL, t_start REAL NOT NULL,
  t_end REAL NOT NULL, title TEXT, PRIMARY KEY (source_file, seg_id));
CREATE TABLE IF NOT EXISTS structure_meta (
  source_file TEXT PRIMARY KEY, captured_at TEXT NOT NULL, sources TEXT NOT NULL, doc_hash TEXT);
```

Rules: **never** touch `PRAGMA user_version` (the conversation store owns it —
the structure store only runs idempotent `CREATE TABLE IF NOT EXISTS` at init);
WAL-compatible defaults, `busy_timeout` ≥ 5 s; `save_structure` replaces the
whole tree for `source_file` in one transaction (delete + insert) so re-capture
is idempotent.

## 5. Capture details

**PDF outline (authoritative for chapter tree when present).**
`PdfDocument.get_toc()` yields `OutlineItem(level, title, page_index)` pairs;
map `page_index` (0-based) → `page_start = page_index + 1` (the same 1-based
axis as docling's `prov.page_no` and payload `page_number` — verified).
Kind: outline level 1 → `chapter` (→ `part` when a level-1 item's descendants
redefine level-1 numbering, e.g. anthology part openers); deeper levels →
`section`/`subsection`. `number` parsed from the title when it opens with a
numbering token ("Chapter 5", "5.2", "I.1"). `node_id` is
`ch{NN}`/`sec{N.M padded}`/`part{slug}` — deterministic so re-capture is
stable.

**docling heading hierarchy (fills sections when outline is absent; always
captured for the merge).** With `heading_hierarchy_options.enabled=True`,
`SectionHeaderItem` carries `level` (bookmark-matched headings are
authoritative; numbering/style fall back). Capture `texts` where
`label == "section_header"` with their levels/pages →
section/subsection nodes under the nearest chapter. The hierarchy stage never
adds/removes/reorders items, so the chunkable text stream is unchanged except
for rare list-item→heading promotions (bounded re-embedding risk, §9).

**Merge.** Outline nodes win where both sources define the same level range
(outline is the PDF's own authority); docling-only sections attach under the
outline chapter that contains their page; docling-only chapters fill when no
outline exists. `page_end`: next node start − 1 at the same-or-shallower
level; last node ends at document page count; same-page openers keep nesting
correct because ranges are derived from the tree order, not heuristics.

**/PageLabels.** `FPDF_GetPageLabel(doc, page_index)` per page; group equal
consecutive labels into `PageLabelRange` rows (printed-page map for display
and printed→physical resolution; never used to filter retrieval).

**Audio.** If the ASR output carries segment timestamps (docling ASR
provenance — probe empirically on the corpus m4a), emit one `segment` node per
ASR segment group and set `t_start`/`t_end` on nodes and chunk payloads; topic
segmentation (LLM on the timestamped transcript, bounded to ≤20 windows,
config flag default on) fills `audio_segments` titles in the parent process
after tree persist. Without timestamps: capture degrades to a single
whole-document segment; ingest must not fail.

**Failure posture.** `capture_structure` catches everything → returns `None`
+ warning log; ingest proceeds; document just has no tree.

## 6. Wiring (exactly one capture point per document)

1. `processor.py` worker: after docling parse (and for PDFs also after
   outline/label reads), call `capture_structure(path, docling_doc,
   file_type)`; attach `structure` to the worker result (workers never open
   SQLite).
2. Each ingest path (`ingestor/_sync.py`, `_async.py`) persists the returned
   tree once per document via the same helper
   (`save_structure` / `save_structure_async`) — one call site per path, one
   shared function, no capture logic duplicated.
3. After chunking, the worker calls `annotate_chunks(chunks, tree)` when a
   tree exists; annotation only adds payload keys (§7).
4. Both ingest paths then call qdrant's `refresh_structural_payload` for the
   document (covers dedup-skipped points, §7).
5. `management` delete removes the stored tree alongside the points.

## 7. Chunk annotation + payload

`annotate_chunks` walks chunks in reading order holding the deepest node whose
range contains the chunk's page (audio: time range): a chunk whose text starts
with a node's own heading anchors to that node; otherwise it inherits the
still-open deepest node. Adds: `node_id`, `heading_path`, `chapter_id`
(top-level ancestor's `number` or `node_id`), `section_id` (immediate
numbered section), `section_label` (that section's title). Text, boundaries,
hashes: untouched.

Hard constraint: **chunk text streams must remain byte-identical** for
unchanged input so `text_hash` dedup keeps every existing point valid — role
and annotation changes are label-only. (Verified feasible: the `body`
downgrade at `chunker.py:134-135` is inside `classify_chunk_role`, which runs
after merging; the merge policy never consults roles.)

`storage/qdrant.py`: add `"chunk_role"` to `_INDEXED_FIELDS` and create the
payload index idempotently in `_ensure_collection`; new
`refresh_structural_payload(source_file)` performs a batched
`retrieve(with_vector=True)` → overwrite payload → `upsert` for that
source_file's points **filtered by `is_empty("node_id")`** so freshly upserted
points (which already carry fields) are never re-read/re-written — only
dedup-skipped legacy points are refreshed. Batch ≈ 256 points (~2 MB vectors)
per round.

## 8. Query path (rag pipeline)

In `_iterative_query`, after source selection and **before** any roster /
pinning work: load the tree for the target document
(`structure_store.load_tree`). If a tree with ≥1 chapter/section node exists:

- Build the chapter map from SQL nodes (ranges = node page ranges; titles +
  numbers from nodes) in the same shape the legacy summarizers consume, so
  `_fallback_mixin`'s bounded-window machinery is reused unchanged.
- Buckets collect via the existing qdrant scroll with `page_number` range
  filters (tree-true ranges replace regex-derived ones). Once annotated
  payloads exist, `chapter_id`/`section_id` exact-match filters may sharpen
  collection, but page ranges remain the source of truth.
- Mark provenance `structure_source="tree"` (logs + optional output note).
- A tree chapter with an empty page range → the existing placeholder note
  (honest, not silent).

Treeless documents, lookup errors, and trees without structural nodes take
the legacy path **unchanged** (anthology detector, agreement gate, all tiers).
The legacy pipeline is never deleted; characterization tests pin its behavior
on treeless fixtures.

## 9. Risks / traps

1. **Role change vs legacy bucket collection:** legacy tiers match section
   markers inside `body` chunks (`get_body_chunks` + `SEC_HEADER_RE`). After
   re-ingest, section headings become `heading` chunks — legacy bucketing for
   *that* document would weaken. Mitigation: re-ingested (annotated, treeful)
   documents always take the tree path; legacy path only serves treeless
   documents, whose stored roles are unchanged.
2. **Heading promotions may shift a few chunk boundaries** (docling hierarchy
   promotes list-items to headings → merge behavior changes) → text hash
   changes → re-embedding of the affected chunks only. Bounded, re-ingest
   time, acceptable.
3. **`PRAGMA user_version`:** conversation store owns it; structure store must
   not touch it.
4. **Worker processes never open SQLite** — capture returns data, parent
   persists; avoids multi-writer contention with `--cores`.
5. **`set_payload` by filter applies a uniform payload** — useless for
   per-chunk fields; use the batched retrieve/overwrite/upsert instead.
6. **`source_file` keying:** the tree key MUST be the exact string stored in
   qdrant payload `source_file` (path as passed to ingest), or lookups miss.
7. **Chapter 6 contamination shape:** tree ranges are derived from real
   boundaries, eliminating the `(5, 5)` + per-page-cap artifact by
   construction; verification must still assert it (§11).
8. **Anthology + gate interplay:** they keep governing the fallback path; a
   stored tree simply never reaches them.

## 10. Backfill

`secondbrain ingest <path> --no-skip-existing`: re-parse (docling), capture +
persist tree, re-chunk (identical text → same hashes), annotate, upsert fresh
points with full payload, refresh `is_empty` legacy points. Embedding
generation is skipped for unchanged hashes (existing dedup). Docs state the
per-document cost: parse + (only changed chunks) embeddings + one batched
payload pass.

## 11. Verification plan

1. Unit/fast: new store, capture, annotate, chunker-role, qdrant-index/refresh
   tests; rag pipeline tree-path tests with synthetic trees; characterization
   tests proving treeless documents keep legacy behavior byte-identically.
2. Gates: `openspec validate add-structure-aware-ingestion --strict`;
   `ruff check . && ruff format --check .`; `mypy` on touched files;
   `pytest -m "not integration and not chaos"`.
3. Live replay (worktree venv against the real Qdrant/SQLite): re-ingest
   `hcd_best_practices_report.pdf` (+ UserManual + pve guide + the m4a), then:
   - `summarize /data/workspace/uploads/hcd_best_practices_report.pdf`
     enumerates chapters 1–21, no placeholder rows, chapter 6 free of section-5
     content;
   - chapter/section-start questions answer from the tree
     (`structure_source=tree` in logs);
   - `secondbrain structure <doc>` prints the stored tree + page labels;
   - a treeless control document still summarizes via the legacy path
     unchanged.
