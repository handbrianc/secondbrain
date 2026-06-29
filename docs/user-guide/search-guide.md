# Search Guide

Guide to performing effective semantic searches with SecondBrain.

## Overview

The `search` command performs vector similarity search against your ingested document corpus. Queries are converted to embeddings and compared against stored document vectors.

## Basic Search Syntax

```bash
secondbrain search "your search query"
```

Results display as a formatted table showing:

- **Score**: Relevance score (0.0 to 1.0, higher = more relevant)
- **Source**: Origin file
- **Page**: Page number or section marker
- **Text Preview**: Snippet of matched content

## Filtering Options

### Source Filter

Filter results to a specific file or directory:

```bash
secondbrain search "optimization" --source "./research/"
secondbrain search "methodology" --source "./thesis.pdf"
```

### File Type Filter

Restrict to particular formats:

```bash
secondbrain search "benchmarks" --file-type pdf
secondbrain search "api reference" --file-type md
secondbrain search "pricing" --file-type xlsx
```

### Combining Filters

Filters can be combined:

```bash
secondbrain search "authentication flow" \
  --source "./docs/" \
  --file-type md \
  --min-score 0.5
```

## Result Quantity Control

### Top-K Parameter

Control how many results to return:

```bash
# Return only top result
secondbrain search "key finding" --top-k 1

# Return more context
secondbrain search "overview" --top-k 20
```

Default: 20 results

### Minimum Score Threshold

Exclude low-relevance results:

```bash
# High precision (fewer, more relevant results)
secondbrain search "critical bug" --min-score 0.8

# Higher recall (more potential matches)
secondbrain search "related topic" --min-score 0.3
```

Default minimum score: 0.46

## Output Formatting

### Table Format (Default)

Human-readable output with columns:

```
╭───────────────────────────────────────────────────────────────╮
│ Search Results                                               │
├───────────────────────────────────────────────────────────────╮
│  Score │ Source              │ Page │ Text Preview            │
├────────┼─────────────────────┼──────┼─────────────────────────┤
│  0.89  │ paper.pdf           │ 3    │ The optimization techn… │
│  0.76  │ notes.md            │ 1    │ Various approaches inc… │
╰───────────────────────────────────────────────────────────────╯
```

### JSON Format

Machine-readable output for scripting:

```bash
secondbrain search "requirements" --format json
```

```json
[
  {
    "score": 0.89,
    "source": "paper.pdf",
    "page": 3,
    "text": "The optimization techniques include..."
  }
]
```

## Search Strategies

### Precision Search

When you need exact answers:

```bash
# High threshold, few results
secondbrain search "\"specific phrase\"" --min-score 0.75 --top-k 5
```

### Exploratory Search

When discovering topics:

```bash
# Low threshold, many results
secondbrain search "overview of techniques" --min-score 0.3 --top-k 50
```

Then iterate by increasing score threshold on promising results.

### Targeted Retrieval

Specific document sections:

```bash
# Filter to specific source
secondbrain search "implementation details" \
  --source "./specific_doc.pdf" \
  --top-k 10
```

## Understanding Scores

Similarity scores represent cosine similarity between query and document vectors:

| Score Range | Interpretation |
|-------------|----------------|
| 0.8 - 1.0 | Very high relevance, near-exact match |
| 0.6 - 0.8 | Strong relevance |
| 0.4 - 0.6 | Moderate relevance |
| 0.2 - 0.4 | Weak relevance |
| 0.0 - 0.2 | Minimal similarity |

Factors affecting scores:

- Query specificity
- Document chunk boundaries
- Embedding model used
- Chunk size selection at ingestion

## Improving Search Quality

### Optimal Chunk Sizes at Ingestion

| Content Type | Recommended chunk_size |
|--------------|------------------------|
| Q&A pairs | 512-1024 |
| Technical docs | 1024-2048 |
| Long articles | 2048-4096 |
| Books/narratives | 4096-8192 |

### Query Formulation Tips

**Good queries:**

```bash
secondbrain search "how does the caching mechanism work"
secondbrain search "compare SQL and NoSQL databases"
secondbrain search "steps to configure authentication"
```

**Poor queries:**

```bash
secondbrain search "it"              # Too vague
secondbrain search "the thing"        # Ambiguous
secondbrain search ""                 # Empty
```

### Semantic vs Keyword

SecondBrain uses semantic search, so natural language works better than boolean:

```bash
# Semantic (recommended)
secondbrain search "ways to speed up database queries"

# Less effective
secondbrain search "database AND (speed OR fast)"
```

## Cross-Document Search

Search across entire corpus efficiently:

```bash
# Topic overview from all sources
secondbrain search "microservices architecture patterns" --top-k 30

# Synthesize common themes from results
secondbrain search "deployment strategies" --source "./company-docs/"
```

## Handling No Results

If search returns nothing:

1. Lower the score threshold:

```bash
secondbrain search "your query" --min-score 0.2
```

2. Broaden the query:

```bash
# Instead of exact phrase
secondbrain search "performance optimization techniques"

# More general
secondbrain search "optimization"
```

3. Check if documents exist:

```bash
secondbrain ls --source "./relevant-file.pdf"
```

4. Re-ingest with adjusted chunking:

Documents might need different chunk sizes to match your query granularity.

## Integration with Other Commands

### Pipeline Example

```bash
# Find relevant documents
secondbrain search "machine learning model evaluation" \
  --format json > matches.json

# List all from same source
jq -r '.[].source' matches.json | sort -u | while read src; do
  secondbrain ls --source "$src"
done
```

### Scripting Integration

```bash
#!/bin/bash
# Get all sources mentioning a topic
RESULTS=$(secondbrain search "$1" --format json --top-k 50)

echo "$RESULTS" | jq -r '.[].source' | sort -u
```