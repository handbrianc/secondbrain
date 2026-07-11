---
title: Document Summarization
description: Generate chapter and section summaries using SecondBrain's structural RAG pipeline
---

# Document Summarization

Guide to generating focused summaries from ingested documents using SecondBrain's structural enhancement pipeline.

## Overview

The `summarize` command extracts meaningful summaries from your ingested documents at varying levels of granularity—whole chapters or individual sections. Unlike general-purpose search, the summarizer leverages structural metadata (`element_type`) to produce contextually accurate abstracts that respect document hierarchy.

Summarization is useful for:

- Quickly understanding the main points of a lengthy document
- Building a table of contents with abstracts for each section
- Creating executive summaries for reports and papers
- Generating study guides from technical documentation

## Prerequisites

Before using the summarizer, ensure your documents have been ingested with structural enhancement enabled (automatically applied in SecondBrain v2.x):

```bash
# Check document structure metadata
secondbrain ls --source "./document.pdf"
```

Your document should have `element_type` values populated. You can verify this in the database or by running a structural search:

```bash
secondbrain search "." --source "./document.pdf" --top-k 5
```

If all chunks show generic text without heading/caption indicators, either:

- The source document lacks clear heading structure, or
- The document predates the v2.x structural enhancement

In the latter case, consider re-ingesting:

```bash
secondbrain delete --source "./document.pdf"
secondbrain ingest ./document.pdf
```

## Basic Usage

### Summarize Entire Document

Generate a single comprehensive summary:

```bash
secondbrain summarize ./document.pdf
```

Output:

```
=== Summary of: document.pdf ===

This paper presents a comprehensive analysis of distributed caching
strategies in microservice architectures. The authors examine three
primary approaches...

[Full summary text]
```

### Dry Run / Validation

Check what would be summarized without generating output:

```bash
secondbrain summarize ./document.pdf --dry-run
```

### Output Formats

#### Text (Default)

Human-readable format suitable for display or piping:

```bash
secondbrain summarize ./document.pdf --format text
```

#### JSON

Machine-readable format for integration with other tools:

```bash
secondbrain summarize ./document.pdf --format json
```

```json
{
  "source": "./document.pdf",
  "chapters": [
    {
      "chapter": 1,
      "summary": "Introduction to distributed systems...",
      "sections": [...]
    }
  ]
}
```

## Chapter Summaries

Use `--chapter N` to generate a summary for a specific chapter or major division within a document.

### Syntax

```bash
secondbrain summarize ./document.pdf --chapter N
```

Where `N` is the 1-based chapter number.

### Example

Summarize chapter 3 of a research paper:

```bash
secondbrain summarize ./paper.pdf --chapter 3
```

Typical output:

```
=== Chapter 3 Summary: paper.pdf ===

Evaluation Methodology
----------------------

This chapter describes the experimental setup used to evaluate
the proposed caching mechanism. The authors employ a simulated
production environment with 47 microservices...

Key findings:
- 34% latency reduction observed
- Memory overhead acceptable (<8%)
- Compatibility with existing service mesh
```

### Multiple Chapters

Generate summaries for consecutive chapters:

```bash
# Summarize chapters 2 through 5
for i in 2 3 4 5; do
  secondbrain summarize ./paper.pdf --chapter $i
done
```

### Handling Missing Chapters

If a chapter number does not exist:

```
Warning: Chapter 7 not found in document structure.
Available chapters: 1, 2, 3, 4, 5, 6, 8
```

## Section Summaries

Use `--by-section` to generate summaries organized by logical subsections rather than chapters.

### Syntax

```bash
secondbrain summarize ./document.pdf --by-section
```

This iterates over all identified sections and produces a structured output:

```
=== Section Summaries: document.pdf ===

[SECTION 1] Introduction
-------------------------
Summary text here...

[SECTION 2] Related Work
-------------------------
Summary text here...
```

### Specific Section by ID

Target a particular section with `--section-id`:

```bash
secondbrain summarize ./document.pdf --section-id 3.2.1
```

Combined with other options:

```bash
# Limit sections processed
secondbrain summarize ./document.pdf --section-depth 2

# Combine with chapter restriction
secondbrain summarize ./document.pdf --chapter 2 --by-section
```

### Section Depth Control

Restrict to a maximum nesting depth:

```bash
# Only top-level sections (no subsections)
secondbrain summarize ./document.pdf --by-section --max-depth 1

# Allow two levels of subsections
secondbrain summarize ./document.pdf --by-section --max-depth 2
```

## Configuration

Behavior can be tuned via environment variables and command-line options.

### Environment Variables

| Variable | Values | Default | Effect |
|----------|--------|---------|--------|
| `SECONDBRAIN_SUMMARIZER_MODE` | `brief`, `standard`, `detailed` | `standard` | Length and detail level of generated summaries |
| `SECONDBRAIN_SUMMARY_DEPTH` | Integer (1-3) | `2` | Maximum section nesting depth to traverse |
| `SECONDBRAIN_ADAPTIVE_CHUNKING` | `true`, `false` | `true` | Whether to adjust chunk boundaries for optimal context |

#### Summarizer Modes

**`brief`** — Concise, high-level summaries (2-3 sentences per section)

```bash
export SECONDBRAIN_SUMMARIZER_MODE=brief
```

**`standard`** — Balanced summaries (1 paragraph per section)

```bash
export SECONDBRAIN_SUMMARIZER_MODE=standard
```

**`detailed`** — Extended summaries with supporting details (multiple paragraphs, key statistics preserved)

```bash
export SECONDBRAIN_SUMMARIZER_MODE=detailed
```

#### Adaptive Chunking

When enabled, the summarizer dynamically adjusts content boundaries to ensure coherent context windows:

```bash
export SECONDBRAIN_ADAPTIVE_CHUNKING=true
```

Disable for reproducible, fixed-boundary behavior:

```bash
export SECONDBRAIN_ADAPTIVE_CHUNKING=false
```

### Command-Line Overrides

Command-line options take precedence over environment variables:

```bash
# Override SECONDBRAIN_SUMMARIZER_MODE for this run
secondbrain summarize ./doc.pdf --mode detailed

# Explicitly restore environment variable behavior
secondbrain summarize ./doc.pdf --mode standard
```

## How It Works

Understanding the underlying pipeline helps optimize usage.

### ScopedRetriever

First, the `ScopedRetriever` identifies content belonging to the requested scope:

1. If `--chapter N` specified: collects all chunks where `chunk_index` falls within chapter N's range
2. If `--by-section` specified: traverses document hierarchy via `element_type` relationships
3. Uses `element_type = "heading"` markers to infer section boundaries

The retriever applies a fallback strategy:

- Primary path uses `element_type` classifications
- If unavailable, falls back to analyzing `chunk_role` (backwards compat)
- If neither available, clusters by proximity heuristics

### Summarizer Stage

Collected chunks are passed to the summarization model:

1. **Context assembly**: Chunks ordered by `chunk_index`, with surrounding heading context included
2. **Prompt construction**: Prompt adapts to `--mode` and `SECONDBRAIN_SUMMARIZER_MODE`
3. **Generation**: Model produces summary constrained to appropriate length
4. **Post-processing**: Strips redundant phrases, validates coherence

### Dual-Read Backwards Compatibility

Queries read both `element_type` and `chunk_role`:

```python
# Pseudocode for dual-read
if chunk.element_type:
    role = chunk.element_type
else:
    role = map_legacy(chunk.chunk_role)
```

This ensures documents ingested under v1.x remain queryable without re-ingestion.

## Troubleshooting

Common issues and resolutions.

### "No chapter structure detected"

**Cause**: The source document lacks heading markup visible to the parser, or headings weren't properly classified during ingestion.

**Solutions**:

1. Inspect the raw chunk types:

   ```bash
   secondbrain search ". " --source "./doc.pdf" --format json | jq '.[].metadata'
   ```

2. Try opening the source in a different application that preserves heading styles

3. Manually add structure via preprocessing before ingestion

### "Empty summary returned"

**Cause**: All chunks in the requested scope may be navigation/furniture elements (headers, footers, page numbers).

**Solution**: Request a different chapter or wider scope:

```bash
# Try broader chapter + filter out navigation
secondbrain summarize ./doc.pdf --chapter 1 --exclude-types navigation
```

### "Summary seems incomplete"

**Cause**: `element_type` may be partially populated due to mixed formatting in the source document.

**Solutions**:

1. Increase context window with adaptive chunking disabled:

   ```bash
   export SECONDBRAIN_ADAPTIVE_CHUNKING=false
   secondbrain summarize ./doc.pdf --chapter 3
   ```

2. Switch to detailed mode for fuller output:

   ```bash
   secondbrain summarize ./doc.pdf --mode detailed
   ```

### "Unicode/special character rendering issues"

**Cause**: Terminal encoding settings may not handle document-specific characters.

**Workaround**: Redirect output to file:

```bash
secondbrain summarize ./doc.pdf --format text > summary.txt
```

Then open in a Unicode-capable editor.

### Slow performance on large documents

**Cause**: Large contexts require more processing time and token usage.

**Optimizations**:

1. Target specific chapters/sections rather than full document

2. Reduce `SECONDBRAIN_SUMMARY_DEPTH` to limit subsection traversal

3. Pre-filter to exclude irrelevant sections:

   ```bash
   secondbrain summarize ./book.pdf --chapter 4 --exclude-types navigation,toc_entry
   ```

## See Also

- [`cli-reference.md`](cli-reference.md) — Full CLI option reference for `summarize`
- [`document-ingestion.md`](document-ingestion.md) — How structural metadata is assigned during ingestion
- [`search-guide.md`](search-guide.md) — General search patterns complementary to summarization