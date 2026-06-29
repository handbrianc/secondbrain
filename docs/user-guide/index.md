# User Guide

The SecondBrain User Guide covers all aspects of operating SecondBrain in production environments.

## Table of Contents

1. **[CLI Reference](cli-reference.md)** — Complete command documentation
2. **[Document Ingestion](document-ingestion.md)** — Adding documents to the vector store
3. **[Search Guide](search-guide.md)** — Performing semantic searches
4. **[Document Management](document-management.md)** — Listing and deleting documents

## Core Concepts

### Vector Search Fundamentals

SecondBrain stores document chunks as embedded vectors in MongoDB. When you search, your query is converted to a vector and compared against stored vectors using similarity metrics.

### Chunking Strategy

Documents are split into overlapping chunks to enable granular retrieval. Key settings:

- **`chunk_size`**: Target size of each chunk (default: 4096 characters)
- **`chunk_overlap`**: Characters overlapped between consecutive chunks (default: 50)

### Session-Based Chat

The `chat` command maintains conversation history per session, enabling multi-turn dialogues with your documents using RAG (Retrieval-Augmented Generation).

## Common Operations

### Daily Workflow Example

```bash
#!/bin/bash
# Morning routine - check status
secondbrain status
secondbrain health

# Ingest new documents
secondbrain ingest ~/Documents/research --recursive --cores 4

# Answer questions
secondbrain chat "Summarize the key findings from recent papers"
secondbrain chat "Compare approaches documented in the literature"
```

### Weekly Maintenance

```bash
#!/bin/bash
# Weekly cleanup
secondbrain ls --all > inventory.txt
# Review inventory and delete stale sources
secondbrain delete --source "./old-document.pdf" --yes

# Reset metrics for fresh monitoring
secondbrain metrics --reset
```

## Configuration Recommendations

### Development Environment

```bash
SECONDBRAIN_LOG_LEVEL=DEBUG
SECONDBRAIN_RATE_LIMIT_ENABLED=false
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=false
```

### Production Environment

```bash
SECONDBRAIN_LOG_LEVEL=INFO
SECONDBRAIN_LOG_FORMAT=json
SECONDBRAIN_RATE_LIMIT_ENABLED=true
SECONDBRAIN_CIRCUIT_BREAKER_ENABLED=true
SECONDBRAIN_STORAGE_COMPRESSION_ENABLED=true
```

## Tips and Tricks

### Efficient Batch Ingestion

```bash
# For large document collections
secondbrain ingest ./corpus --recursive --cores $(nproc) --batch-size 20
```

### Precision Searching

```bash
# High-precision search
secondbrain search "specific phrase" --min-score 0.7 --top-k 5

# Broad exploratory search
secondbrain search "concept overview" --min-score 0.3 --top-k 50
```

### Session Management

```bash
# Named session for project-specific chats
secondbrain chat --session "project-alpha" "What decisions were made?"

# View session history
secondbrain chat --history --session "project-alpha"

# Switch contexts entirely
secondbrain chat --session "project-beta" "Different research questions"
```