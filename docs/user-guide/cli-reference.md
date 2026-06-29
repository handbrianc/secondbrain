# CLI Reference

Complete reference for all SecondBrain command-line interface commands.

## Global Options

| Option | Description |
|--------|-------------|
| `--help, -h` | Show help message and exit |
| `--version, -v` | Show version number |

## Commands Overview

| Command | Description |
|---------|-------------|
| [`ingest`](#ingest) | Ingest documents into the vector database |
| [`search`](#search) | Search the vector database with semantic query |
| [`ls`](#ls) | List ingested documents and chunks |
| [`delete`](#delete) | Delete documents from the vector database |
| [`status`](#status) | Show statistics about the vector database |
| [`health`](#health) | Check health status of all services |
| [`metrics`](#metrics) | Show performance metrics and statistics |
| [`chat`](#chat) | Conversational Q&A with your documents |
| [`start`](#start) | Start the production Docker Compose stack |
| [`stop`](#stop) | Stop the production Docker Compose stack |

---

## ingest

Ingest documents into the vector database.

### Synopsis

```
secondbrain ingest PATH [--recursive] [--cores INT] [--batch-size INT] [--chunk-size INT] [--chunk-overlap INT]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `PATH` | Path to file or directory to ingest |

### Options

| Option | Description |
|--------|-------------|
| `--recursive, -r` | Recursively process directories |
| `--cores, -c INT` | Number of CPU cores for parallel processing (default: auto-detect) |
| `--batch-size, -b INT` | Batch size for ThreadPoolExecutor when cores=1 (default: 10) |
| `--chunk-size INT` | Override default chunk size |
| `--chunk-overlap INT` | Override default chunk overlap |

### Examples

```bash
# Ingest single file
secondbrain ingest ./document.pdf

# Ingest directory recursively
secondbrain ingest ./documents/ --recursive

# Ingest with 4 CPU cores
secondbrain ingest ./papers/ --recursive --cores 4

# Custom chunking parameters
secondbrain ingest ./notes/ --chunk-size 2048 --chunk-overlap 100
```

---

## search

Search the vector database with semantic query.

### Synopsis

```
secondbrain search QUERY [--top-k INT] [--source STR] [--file-type STR] [--format table|json] [--min-score FLOAT]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `QUERY` | Search query text |

### Options

| Option | Description |
|--------|-------------|
| `--top-k INT` | Number of results to return |
| `--source STR` | Filter results by source file path |
| `--file-type STR` | Filter results by file type (e.g., 'pdf', 'docx') |
| `--format` | Output format: `table` (default) or `json` |
| `--min-score FLOAT` | Minimum similarity score threshold (0.0-1.0, default: 0.46) |

### Examples

```bash
# Basic search
secondbrain search "machine learning optimization techniques"

# Top 10 results in JSON format
secondbrain search "neural network architectures" --top-k 10 --format json

# Filter by file type
secondbrain search "performance benchmarks" --file-type pdf

# High-relevance only
secondbrain search "installation steps" --min-score 0.7

# Combine filters
secondbrain search "authentication" --source "./docs/" --file-type md
```

---

## ls

List ingested documents and chunks.

### Synopsis

```
secondbrain ls [--source STR] [--chunk-id STR] [--limit INT] [--offset INT] [--all]
```

### Options

| Option | Description |
|--------|-------------|
| `--source STR` | Filter by source file |
| `--chunk-id STR` | Filter by specific chunk ID |
| `--limit INT` | Maximum number of results (default: 100, max: 10000) |
| `--offset INT` | Offset for pagination |
| `--all, -a` | List all documents (ignores limit) |

### Examples

```bash
# List first 100 documents
secondbrain ls

# List all documents
secondbrain ls --all

# Paginated results
secondbrain ls --limit 50 --offset 100

# Filter by source
secondbrain ls --source "./report.pdf"

# Specific chunk
secondbrain ls --chunk-id abc123
```

---

## delete

Delete documents from the vector database.

### Synopsis

```
secondbrain delete [--source STR] [--chunk-id STR] [--all] [--yes]
```

### Options

| Option | Description |
|--------|-------------|
| `--source STR` | Filter by source file |
| `--chunk-id STR` | Filter by specific chunk ID |
| `--all, -a` | Delete all documents |
| `--yes, -y` | Skip confirmation prompt |

### Examples

```bash
# Delete by source
secondbrain delete --source "./report.pdf"

# Delete specific chunk
secondbrain delete --chunk-id abc123

# Delete all (requires confirmation)
secondbrain delete --all

# Delete all without prompting
secondbrain delete --all --yes
```

### Warnings

- Deletion is permanent and cannot be undone
- Confirm before using `--all` without `--yes`

---

## status

Show statistics about the vector database.

### Synopsis

```
secondbrain status
```

### Examples

```bash
secondbrain status
```

Displays MongoDB collection statistics including total documents, storage size, and index information.

---

## health

Check health status of all services.

### Synopsis

```
secondbrain health [--output text|json]
```

### Options

| Option | Description |
|--------|-------------|
| `--output` | Output format: `text` (default) or `json` |

### Examples

```bash
# Text output
secondbrain health

# JSON for scripting
secondbrain health --output json
```

---

## metrics

Show performance metrics and statistics.

### Synopsis

```
secondbrain metrics [--reset]
```

### Options

| Option | Description |
|--------|-------------|
| `--reset, -r` | Reset all metrics |

### Examples

```bash
# View all metrics
secondbrain metrics

# Reset metrics
secondbrain metrics --reset
```

Available metrics:

| Metric | Description |
|--------|-------------|
| `embedding_generate` | Sync embedding generation |
| `embedding_generate_async` | Async embedding generation |
| `embedding_generate_batch` | Batch sync embedding |
| `embedding_generate_batch_async` | Batch async embedding |
| `storage_store` | Sync storage writes |
| `storage_store_async` | Async storage writes |
| `storage_store_batch` | Batch sync writes |
| `storage_store_batch_async` | Batch async writes |
| `storage_search` | Sync search queries |
| `storage_search_async` | Async search queries |

Each metric reports: Count, Total, Average, Min, and Max times.

---

## chat

Conversational Q&A with your documents using local LLM.

### Synopsis

```
secondbrain chat [QUERY] [--session STR] [--top-k INT] [--temperature FLOAT] [--model STR]
                 [--show-sources] [--list-sessions] [--history] [--delete-session STR]
                 [--create] [--check-llm]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `QUERY` | Initial query (optional - enters interactive mode if omitted) |

### Options

| Option | Description |
|--------|-------------|
| `--session, -s STR` | Session ID to use/create |
| `--top-k, -k INT` | Number of chunks to retrieve (default: 20) |
| `--temperature, -t FLOAT` | LLM temperature (default: 0.1) |
| `--model, -m STR` | LLM model name |
| `--show-sources` | Show retrieved sources |
| `--list-sessions` | List all conversation sessions |
| `--history` | Show session history |
| `--delete-session, -d STR` | Delete a session |
| `--create, -c` | Create new session with UUID |
| `--check-llm` | Check if LLM provider is available |

### Interactive Mode Commands

Inside the interactive REPL:

| Command | Description |
|---------|-------------|
| `/quit, /exit` | Exit chat |
| `/clear` | Clear conversation history |
| `/help` | Show help |

### Examples

```bash
# Single query
secondbrain chat "What is the main topic?"

# Interactive REPL
secondbrain chat

# Named session
secondbrain chat --session my-project

# Show sources in response
secondbrain chat "Explain the methodology" --show-sources

# List all sessions
secondbrain chat --list-sessions

# View session history
secondbrain chat --history --session my-project

# Delete session
secondbrain chat --delete-session old-session

# Check LLM availability
secondbrain chat --check-llm
```

---

## start

Start the production Docker Compose stack.

### Synopsis

```
secondbrain start [--compose-file FILE] [--project-name NAME] [--wait]
```

### Options

| Option | Description |
|--------|-------------|
| `--compose-file, -f FILE` | Path to docker-compose.yml (default: auto-detect) |
| `--project-name, -p NAME` | Docker Compose project name (default: secondbrain) |
| `--wait, -w` | Wait for services to be fully ready |

### Examples

```bash
# Start with auto-detected compose file
secondbrain start

# Wait for full readiness
secondbrain start --wait

# Use specific compose file
secondbrain start -f docker-compose.prod.yml
```

---

## stop

Stop the production Docker Compose stack.

### Synopsis

```
secondbrain stop [--compose-file FILE] [--project-name NAME] [--remove-volumes] [--force]
```

### Options

| Option | Description |
|--------|-------------|
| `--compose-file, -f FILE` | Path to docker-compose.yml (default: auto-detect) |
| `--project-name, -p NAME` | Docker Compose project name (default: secondbrain) |
| `--remove-volumes, -v` | Remove named volumes |
| `--force, -y` | Skip confirmation prompt |

### Examples

```bash
# Stop containers
secondbrain stop

# Stop and remove volumes
secondbrain stop --remove-volumes

# Force stop without confirmation
secondbrain stop --force
```