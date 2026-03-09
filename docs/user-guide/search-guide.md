# Search Guide

Learn how to perform semantic search with SecondBrain.

## Basic Search

### Simple Query

```bash
secondbrain search "what is this about?"
```

Returns the top 5 most relevant results by default.

### Get More Results

```bash
secondbrain search "machine learning" --top-k 10
```

### Verbose Output

```bash
secondbrain search "data pipelines" --verbose
```

Shows similarity scores and metadata.

## Search Syntax

### Natural Language

SecondBrain understands natural language queries:

```bash
# Questions
secondbrain search "how do I configure MongoDB?"

# Topics
secondbrain search "neural network architectures"

# Concepts
secondbrain search "best practices for error handling"
```

### Keyword Search

While semantic, keywords still work:

```bash
secondbrain search "Python async await"
```

## Understanding Results

### Result Format

Each result includes:
- **Document ID** - Unique identifier
- **Source File** - Original file path
- **Page/Chunk** - Location in document
- **Content** - Text chunk
- **Score** - Similarity score (0-1)

### Example Output

```
1. [Score: 0.89] document.pdf (page 3)
   "To configure MongoDB, update the SECONDBRAIN_MONGO_URI..."

2. [Score: 0.76] config.md (chunk 2)
   "The MongoDB connection string should start with..."
```

## Search Tips

### Be Specific

```bash
# Good
secondbrain search "how to configure MongoDB connection string"

# Less effective
secondbrain search "database setup"
```

### Use Context

```bash
# Include context
secondbrain search "configuration options for MongoDB in production"
```

### Iterate

Start broad, then refine:
```bash
# First
secondbrain search "configuration"

# Then narrow
secondbrain search "MongoDB configuration production"
```

## Advanced Search

### Filter by Document Type

Currently, filtering is done by post-processing results. Future versions will support:
```bash
secondbrain search "reports" --file-type pdf
```

### Search Specific Collections

```bash
# Future feature
secondbrain search "query" --collection research-papers
```

## Programmatic Search

### Synchronous API

```python
from secondbrain.client import SecondBrainClient

client = SecondBrainClient()

results = client.search("semantic query", top_k=10)

for result in results:
    print(f"Score: {result.score}")
    print(f"Content: {result.content}")
```

### Asynchronous API

```python
import asyncio
from secondbrain.client import SecondBrainClient

async def search_docs():
    client = SecondBrainClient()
    
    results = await client.search("query", top_k=10)
    
    for result in results:
        print(result)
    
    await client.close()

asyncio.run(search_docs())
```

See [Async API Guide](../developer-guide/async-api.md) for more details.

## Similarity Scoring

### How Scoring Works

- Uses cosine similarity
- Scores range from 0 (no similarity) to 1 (exact match)
- Higher scores = more relevant

### Score Thresholds

| Score | Relevance |
|-------|-----------|
| 0.8+ | Highly relevant |
| 0.6-0.8 | Relevant |
| 0.4-0.6 | Somewhat relevant |
| < 0.4 | Low relevance |

## Troubleshooting

### No Results

**Problem:** Search returns no results

**Solutions:**
1. Check if documents are ingested: `secondbrain list`
2. Try broader query
3. Verify embeddings exist: `secondbrain status`

### Low Relevance

**Problem:** Results don't seem relevant

**Solutions:**
1. Refine query to be more specific
2. Adjust `--top-k` to see more results
3. Check document quality and chunking

### Slow Search

**Problem:** Search takes too long

**Solutions:**
1. Reduce `--top-k` value
2. Check MongoDB performance
3. Verify network connection

## Related Documentation

- [Quick Start](../getting-started/quick-start.md) - Basic usage
- [Document Ingestion](./document-ingestion.md) - Add documents
- [CLI Reference](./cli-reference.md) - All commands