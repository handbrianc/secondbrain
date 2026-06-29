# Basic Usage Examples

Common command-line workflows with SecondBrain.

## Document Ingestion

### Single File Ingestion

```bash
# Basic single file
secondbrain ingest ./document.pdf

# With custom chunking
secondbrain ingest ./article.pdf --chunk-size 2048 --chunk-overlap 100
```

### Directory Ingestion

```bash
# Non-recursive - current directory only
secondbrain ingest ./papers/

# Recursive - all subdirectories
secondbrain ingest ./papers/ --recursive

# Specify CPU cores for parallelism
secondbrain ingest ./corpus/ --recursive --cores 4
```

### Batch Processing Configuration

```bash
# Adjust batch size for memory constraints
secondbrain ingest ./docs/ --batch-size 5

# Combined options
secondbrain ingest ./large_dataset/ \
  --recursive \
  --cores 8 \
  --batch-size 20 \
  --chunk-size 4096
```

## Semantic Search

### Basic Search

```bash
# Simple query
secondbrain search "machine learning algorithms"

# Limit results
secondbrain search "python best practices" --top-k 5

# Different output formats
secondbrain search "data structures" --format json
```

### Filtered Search

```bash
# PDF documents only
secondbrain search "optimization techniques" --file-type pdf

# Specific source file
secondbrain search "introduction" --source "./chapter1.pdf"

# High relevance threshold
secondbrain search "installation" --min-score 0.7

# Combined filters
secondbrain search "configuration" \
  --source "./docs/" \
  --file-type md \
  --min-score 0.5
```

## Document Listing

### Basic Listing

```bash
# Default - first 100 documents
secondbrain ls

# List all
secondbrain ls --all

# With pagination
secondbrain ls --limit 50 --offset 0
```

### Filtered Listing

```bash
# By source file
secondbrain ls --source "./report.pdf"

# By chunk ID
secondbrain ls --chunk-id "abc123-uuid"

# Combined with all
secondbrain ls --source "./papers/" --all
```

## Document Deletion

### Selective Deletion

```bash
# By source file (prompts for confirmation)
secondbrain delete --source "./old_document.pdf"

# Skip confirmation
secondbrain delete --source "./old_document.pdf" --yes

# By chunk ID
secondbrain delete --chunk-id "specific-chunk-id"
```

### Bulk Deletion

```bash
# All documents (prompts for confirmation)
secondbrain delete --all

# Immediate deletion
secondbrain delete --all --yes
```

## Status and Diagnostics

### Database Status

```bash
secondbrain status
```

Shows: total chunks, unique sources, storage size, index status.

### Health Check

```bash
# Text output
secondbrain health

# JSON for scripting
secondbrain health --output json
```

### Performance Metrics

```bash
# View metrics
secondbrain metrics

# Reset and start fresh
secondbrain metrics --reset
```

## Conversational Chat

### Interactive Mode

```bash
# Start interactive REPL
secondbrain chat

# With named session
secondbrain chat --session my-project

# Inside REPL, use commands:
# /help - Show available commands
# /clear - Clear conversation history
# /quit - Exit chat
```

### Single Query Mode

```bash
# One-off question
secondbrain chat "What is the main topic?"

# With sources shown
secondbrain chat "Explain the methodology" --show-sources

# Custom model parameters
secondbrain chat "Summarize findings" --temperature 0.2 --top-k 10
```

### Session Management

```bash
# List all sessions
secondbrain chat --list-sessions

# View session history
secondbrain chat --history --session my-project

# Delete a session
secondbrain chat --delete-session old-session
```

## Service Management

### Start/Stop Docker Stack

```bash
# Start MongoDB
secondbrain start
secondbrain start --wait  # Block until ready

# With custom compose file
secondbrain start --compose-file ./docker-compose.prod.yml

# Stop (prompts for confirmation)
secondbrain stop

# Stop with volume removal
secondbrain stop --remove-volumes

# Immediate stop
secondbrain stop --force
```

## Combined Workflows

### Research Paper Analysis

```bash
#!/bin/bash
# Ingest all PDFs from research directory
secondbrain ingest ~/Research/ \
  --recursive \
  --file-type pdf \
  --cores 4

# Find papers mentioning specific topic
secondbrain search "attention mechanisms" --file-type pdf --top-k 10

# Summarize relevant content
secondbrain chat \
  --session attention-research \
  "What attention mechanisms are described in these papers?" \
  --show-sources
```

### Documentation Query System

```bash
#!/bin/bash
# Index documentation
secondbrain ingest ./docs/ --recursive

# Quick answers
secondbrain chat --session docs "How do I configure authentication?"

# Find relevant sections
secondbrain search "authentication configuration" --min-score 0.6

# Export relevant docs
secondbrain ls --source "./docs/auth.md" > auth-sections.txt
```

### Content Deduplication

```bash
#!/bin/bash
# Compare document inventories
secondbrain ls --all > current_inventory.txt

# After re-ingestion
secondbrain ls --all > updated_inventory.txt

# Find differences
diff current_inventory.txt updated_inventory.txt
```