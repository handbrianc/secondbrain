# Semantic Search Guide

Learn how to perform semantic search queries with SecondBrain.

## Basic Search

### Simple Query

```bash
secondbrain search "what is machine learning?"
```

SecondBrain will:
1. Convert your query to an embedding
2. Find similar embeddings in the database
3. Return the most relevant document chunks

### Results Format

```
[Score: 0.89] From: report.pdf (chunk 3)
Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience without being explicitly programmed.

[Score: 0.82] From: notes.md (chunk 1)
Key concepts in ML: supervised learning, unsupervised learning, reinforcement learning...
```

## Search Options

### Limit Results

```bash
# Get top 10 results
secondbrain search "python best practices" --top-k 10
```

### Confidence Threshold

```bash
# Only high-confidence matches (0.0 - 1.0)
secondbrain search "data pipeline" --threshold 0.75
```

Results below the threshold are filtered out.

### Custom Fields

```bash
# Include metadata in results
secondbrain search "report" --fields content,metadata,filename
```

### Verbose Mode

```bash
# Show timing and statistics
secondbrain search "query" --verbose
```

Output:
```
Query embedding: 45ms
Vector search: 12ms
Result ranking: 3ms
Total: 60ms

Found 15 matching chunks
Returning top 5
```

## Query Optimization

### Natural Language

Use natural language queries:

```bash
# Good: Natural language
secondbrain search "How do I configure MongoDB?"

# Also good: Question format
secondbrain search "What are the best practices for chunking?"
```

### Keywords vs. Semantics

SecondBrain understands semantics, not just keywords:

```bash
# These will find similar results:
secondbrain search "car"
secondbrain search "automobile"
secondbrain search "vehicle transportation"
```

### Context-Rich Queries

```bash
# More context = better results
secondbrain search "How to handle errors in async Python code?"

# Rather than:
secondbrain search "async error"
```

## Advanced Search Patterns

### Multi-Concept Search

Search for documents covering multiple concepts:

```bash
# Find docs about both topics
secondbrain search "machine learning AND data preprocessing"
```

### Exclusion Queries

SecondBrain doesn't support explicit negation yet, but you can:

```bash
# Be specific about what you want
secondbrain search "python async without threading"
```

### Search by Metadata

```bash
# Search within specific file types
secondbrain search "configuration"  # Then filter results manually

# Or search and check metadata
secondbrain search "database" --fields content,metadata
```

## Understanding Scores

### Similarity Score

- **Range**: 0.0 to 1.0
- **Interpretation**:
  - 0.8-1.0: Very high relevance
  - 0.6-0.8: High relevance
  - 0.4-0.6: Moderate relevance
  - < 0.4: Low relevance

### Score Adjustment

```bash
# Strict matching
secondbrain search "exact term" --threshold 0.85

# Broad matching
secondbrain search "general concept" --threshold 0.3
```

## Search Strategies

### Iterative Refinement

```bash
# Start broad
secondbrain search "python"

# Narrow down based on results
secondbrain search "python async programming"

# Even more specific
secondbrain search "python asyncio best practices"
```

### Exploratory Search

```bash
# Discover related topics
secondbrain search "database optimization" --top-k 20

# Review results to find patterns
# Then refine query based on common themes
```

### Comparative Search

```bash
# Compare different approaches
secondbrain search "approach A versus approach B"
secondbrain search "benefits of approach A"
secondbrain search "benefits of approach B"
```

## Performance Tips

### Fast Search

```bash
# Limit results
secondbrain search "query" --top-k 5

# Use appropriate threshold
secondbrain search "specific term" --threshold 0.6
```

### Comprehensive Search

```bash
# Get more results
secondbrain search "broad topic" --top-k 50 --threshold 0.3

# Include all metadata
secondbrain search "query" --fields content,metadata,filename,source
```

## Common Use Cases

### Code Search

```bash
# Find code examples
secondbrain search "how to implement singleton pattern"

# Search for specific functionality
secondbrain search "error handling async python"
```

### Documentation Lookup

```bash
# Find configuration examples
secondbrain search "MongoDB connection string example"

# Troubleshooting help
secondbrain search "connection timeout error solution"
```

### Research Assistance

```bash
# Summarize topic coverage
secondbrain search "neural network architectures" --top-k 20

# Find specific concepts
secondbrain search "backpropagation algorithm explanation"
```

## Troubleshooting

### No Results Found

**Causes**:
- No documents in database
- Query is too specific
- Threshold too high

**Solutions**:
```bash
# Check if documents exist
secondbrain list

# Lower threshold
secondbrain search "query" --threshold 0.2

# Broaden query
secondbrain search "general topic"
```

### Irrelevant Results

**Causes**:
- Query too broad
- Chunk size inappropriate
- Wrong embedding model

**Solutions**:
```bash
# Be more specific
secondbrain search "specific aspect of topic"

# Re-ingest with different chunk size
secondbrain ingest ./docs/ --chunk-size 1024 --force
```

### Slow Search

**Solutions**:
```bash
# Reduce result count
secondbrain search "query" --top-k 5

# Check database size
secondbrain status
```

## Next Steps

- [Document Management](document-management.md) - Manage your database
- [CLI Reference](cli-reference.md) - Complete command reference
- [Async Guide](../developer-guide/async-api.md) - Programmatic search
