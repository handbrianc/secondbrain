# SecondBrain Examples

This directory contains practical examples demonstrating how to use the SecondBrain document intelligence CLI tool.

## Directory Structure

```
examples/
├── basic_usage/          # Simple CLI-style examples
│   ├── ingest_documents.py
│   ├── semantic_search.py
│   └── list_documents.py
├── advanced/             # Advanced workflows
│   ├── custom_chunking.py
│   ├── batch_ingestion.py
│   └── async_workflow.py
├── integrations/         # API integrations
│   ├── flask_api.py
│   └── fastapi_endpoint.py
└── scripts/              # Utility scripts
    ├── ingest_entire_directory.sh
    └── export_to_json.py
```

## Quick Start

### Prerequisites

```bash
# Install SecondBrain with dependencies
pip install -e ".[dev]"

# Start MongoDB (if using Docker)
docker-compose up -d

# Ensure Ollama is running
ollama serve
```

### Running Examples

```bash
# Basic usage examples
python examples/basic_usage/ingest_documents.py /path/to/documents

# Advanced examples
python examples/advanced/batch_ingestion.py --batch-size 10 /path/to/docs

# Integration examples
python examples/integrations/flask_api.py --port 8000
```

## Examples Overview

### Basic Usage

- **ingest_documents.py**: Simple document ingestion with progress reporting
- **semantic_search.py**: Perform semantic searches with filters
- **list_documents.py**: List and inspect ingested documents

### Advanced

- **custom_chunking.py**: Configure custom chunk sizes and overlap
- **batch_ingestion.py**: Parallel ingestion of large directories
- **async_workflow.py**: Full async workflow for high-throughput scenarios

### Integrations

- **flask_api.py**: Flask REST API wrapper
- **fastapi_endpoint.py**: FastAPI async API with Pydantic models

### Scripts

- **ingest_entire_directory.sh**: Bash script for bulk ingestion
- **export_to_json.py**: Export documents to JSON format

## Tips

- Use `--help` flag on each example to see available options
- Examples use the same `.env` configuration as the CLI
- Set `SECONDBRAIN_VERBOSE=1` for detailed logging
