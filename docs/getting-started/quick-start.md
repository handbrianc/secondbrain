# Quick Start

Get started with SecondBrain in 5 minutes.

## Prerequisites

- Python 3.11+
- MongoDB running locally or remote

## Step 1: Install

```bash
pip install secondbrain
```

## Step 2: Configure

Create a `.env` file:

```bash
echo "MONGODB_URI=mongodb://localhost:27017" > .env
```

## Step 3: Ingest a Document

```bash
# Ingest a PDF
secondbrain ingest path/to/document.pdf

# Or a text file
secondbrain ingest path/to/document.txt

# Or entire directory
secondbrain ingest path/to/documents/ --recursive
```

## Step 4: Search

```bash
# Basic search
secondbrain search "machine learning"

# Limit results
secondbrain search "machine learning" --limit 5

# Export to JSON
secondbrain search "data science" --format json --output results.json
```

## Step 5: List Documents

```bash
# List all documents
secondbrain list

# Detailed view
secondbrain list --verbose
```

## Example Workflow

```bash
# 1. Install
pip install secondbrain

# 2. Configure
echo "MONGODB_URI=mongodb://localhost:27017" > .env

# 3. Ingest research papers
secondbrain ingest ./research-papers/ --recursive

# 4. Search for specific topics
secondbrain search "neural networks in computer vision"

# 5. Export results
secondbrain search "deep learning" --limit 10 --format json --output papers.json
```

## Next Steps

- Read the [User Guide](../user-guide/index.md)
- Explore [Advanced Features](../examples/README.md)
- Check [Configuration Options](configuration.md)

## Troubleshooting

See [Troubleshooting Guide](troubleshooting.md) for common issues.
