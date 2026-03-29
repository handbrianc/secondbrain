# Semantic Search Guide

Learn how to search documents semantically with SecondBrain.

## Basic Search

### Simple Query

```bash
secondbrain search "machine learning"
```

### Limit Results

```bash
secondbrain search "neural networks" --limit 5
```

### Output Format

```bash
# JSON output
secondbrain search "deep learning" --format json

# CSV output
secondbrain search "AI" --format csv

# Text (default)
secondbrain search "data science" --format text
```

## Advanced Search

### Collection Filter

```bash
# Search specific collection
secondbrain search "python" --collection "programming"
```

### Metadata Filter

```bash
# Filter by author
secondbrain search "machine learning" --filter '{"author": "John Doe"}'
```

### Export Results

```bash
# Export to file
secondbrain search "research" --output results.json --format json
```

## Search Tips

### Effective Queries

- **Be specific**: "neural network architectures" vs "AI"
- **Use natural language**: "How does backpropagation work?"
- **Include context**: "machine learning for computer vision"

### Result Ranking

Results are ranked by:
1. Semantic similarity to query
2. Relevance score
3. Metadata matches

### Iterative Search

```bash
# Broad search
secondbrain search "machine learning"

# Narrow down
secondbrain search "transformer models in machine learning"

# Specific question
secondbrain search "attention mechanism in transformers"
```

## Performance

### Fast Search

```bash
# Limit results
secondbrain search "query" --limit 5

# Use cached embeddings
secondbrain search "query" --use-cache
```

### Batch Search

```bash
# Multiple queries
secondbrain search --file queries.txt --output results.json
```

## Troubleshooting

### No Results

**Solutions**:
1. Try broader query
2. Check documents are ingested
3. Verify embedding model

### Irrelevant Results

**Solutions**:
1. Refine query
2. Adjust result limit
3. Use metadata filters

### Slow Search

**Solutions**:
1. Reduce result limit
2. Check MongoDB performance
3. Verify vector index

## See Also

- [Document Ingestion](document-ingestion.md)
- [Document Management](document-management.md)
- [CLI Reference](cli-reference.md)
