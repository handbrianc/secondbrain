# Quick Start Guide

Get SecondBrain running in under 5 minutes with this streamlined guide.

## Step 1: Install SecondBrain

```bash
pip install -e .
```

## Step 2: Configure Environment

Set required environment variables:

```bash
export SECONDBRAIN_MONGO_URI="mongodb://localhost:27017"
export SECONDBRAIN_OPENAI_API_KEY="your-api-key"
```

Optionally, set a custom chunk size for your documents:

```bash
export SECONDBRAIN_CHUNK_SIZE=4096
export SECONDBRAIN_CHUNK_OVERLAP=50
```

## Step 3: Start MongoDB

Launch the Docker Compose stack with the `--wait` flag to ensure readiness:

```bash
secondbrain start --wait
```

You should see:

```
Starting Docker Compose stack from: /path/to/docker-compose.yml
Starting MongoDB...
Waiting for services to be ready...
✓ Docker Compose stack is fully ready
```

## Step 4: Ingest Your First Documents

Process a file or directory:

```bash
# Single file
secondbrain ingest ./document.pdf

# Entire directory (recursive)
secondbrain ingest ./documents/ --recursive
```

Progress indicators show ingestion status:

```
Ingesting: ./documents/
✓ Successfully ingested 10 files
```

## Step 5: Perform Semantic Search

Query your document corpus:

```bash
secondbrain search "what is the main topic discussed?"
```

Results display with relevance scores:

```
╭───────────────────────────────────────────────────────────────╮
│ Search Results                                               │
├───────────────────────────────────────────────────────────────╮
│  Score │ Source              │ Page │ Text Preview            │
├────────┼─────────────────────┼──────┼─────────────────────────┤
│  0.89  │ document.pdf        │ 3    │ The main topic of this… │
│  0.76  │ report.docx         │ 1    │ According to the docum… │
╰───────────────────────────────────────────────────────────────╯
```

## Step 6: List Indexed Documents

View all ingested documents:

```bash
secondbrain ls
```

Or list with filters:

```bash
# Specific source
secondbrain ls --source "./document.pdf"

# Show all documents
secondbrain ls --all
```

## Common Workflows

### Basic Document Intelligence Pipeline

```bash
#!/bin/bash
# Ingest documents with multicore processing
secondbrain ingest /path/to/docs --recursive --cores 4

# Search with high relevance threshold
secondbrain search "installation instructions" --min-score 0.5

# Check status
secondbrain status
```

### Multi-Source Research

```bash
# Ingest from multiple sources
secondbrain ingest ~/projects/research/papers/ --recursive
secondbrain ingest ~/Dropbox/notes/ --recursive

# Search across all sources
secondbrain search "machine learning optimization techniques"
```

## Next Steps

- **[CLI Reference](../user-guide/cli-reference.md)** — Learn all available commands and options
- **[Configuration](configuration.md)** — Fine-tune SecondBrain for your use case
- **[Document Ingestion](../user-guide/document-ingestion.md)** — Understand processing options
- **[Search Guide](../user-guide/search-guide.md)** — Master advanced search techniques