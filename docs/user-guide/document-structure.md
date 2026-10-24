# Document Structure Guide

Inspecting the per-document structure trees that structure-aware ingestion
captures, and backfilling them for documents ingested before the feature.

## What Gets Captured

At ingest time SecondBrain reads the document's authoritative structure
sources and persists one tree per document in the local SQLite store:

| Source | Documents | Captured |
| ---------- | ------------- | -------------- |
| PDF outline / bookmarks | PDFs | Chapters, sections, subsections with 1-based physical page ranges |
| `/PageLabels` | PDFs | Printed page labels (e.g. roman-numeral front matter) grouped into runs |
| docling heading hierarchy | PDFs, office docs | Heading levels that fill the tree when no outline exists |
| ASR timestamps | Audio | Time-bounded segments (`mm:ss` ranges) |

The tree is keyed by the exact `source_file` path the document was ingested
with, so structure lookups resolve against the same key the vector store
uses. Query time then becomes a lookup: chapter/section questions over
treeful documents enumerate ranges from the stored tree instead of
reconstructing them from chunk text, and every chunk payload carries its
`node_id`, `heading_path`, `chapter_id`/`section_id` and `section_label`.

## Inspecting a Document

```bash
secondbrain structure "./report.pdf"
```

Prints the stored tree (indented by level, with each node's kind, number,
title, physical page range as `pp. 7-12` and printed page label when known),
then the `/PageLabels` table, then the audio segments.

JSON for scripting:

```bash
secondbrain structure "./report.pdf" --json
```

`--json` dumps the raw stored structure (nodes, page label ranges, audio
segments, capture sources and timestamp).

### Resolving the Document

The argument may be the path or source key exactly as it was ingested. When
the spelling differs, the command reconciles it:

1. The argument verbatim (the common case).
2. Normalized/absolute spellings of the argument (relative-vs-absolute
   mismatch, when the working directory matches the ingest-time one).
3. A basename or path-tail match over the ingested sources — only when it is
   unambiguous; ambiguous matches fail with the candidate list.

Pass the path exactly as you ingested it to avoid ambiguity.

## Documents Without a Stored Tree

Documents ingested before structure-aware ingestion (or whose structure
could not be captured) have no stored tree. The command says so and prints
the re-ingest command instead of failing:

```text
No stored structure tree for ./report.pdf
Re-ingest it to capture the structure tree:
  secondbrain ingest ./report.pdf
```

## Backfilling Structure

`secondbrain ingest <path>` (with default hash skipping enabled) is the backfill mechanism —
there is no separate migration command. Re-ingesting an already-stored
document:

1. Re-parses it and captures + persists the structure tree.
2. Re-chunks it; unchanged text produces identical chunk hashes.
3. Annotates the chunks with the structural fields and embeds/stores only
   chunks whose hashes are not already stored.
4. Refreshes the structural payload fields on already-stored points that
   were previously dedup-skipped.

Embedding generation is skipped for unchanged hashes, so the per-document
cost is one parse, embeddings for changed chunks only, and one batched
payload pass. Documents whose text did not change are re-annotated without
re-embedding.

## Deleting Documents

`secondbrain delete --source <path>`, `--file-type <type>` and `--all` also
remove the stored structure trees of the documents they delete, so no
orphaned trees survive their points. Deleting a single chunk
(`--chunk-id`) leaves the document and its tree intact. A failure while
cleaning up structure trees is logged as a warning and never fails the
delete itself.
