# Examples

Practical examples demonstrating SecondBrain usage patterns.

## Examples Index

| Section | Description |
|---------|-------------|
| [Basic Usage](basic-usage.md) | Common CLI workflows: ingest, search, list |
| [Integrations](integrations.md) | Using SecondBrain programmatically with Flask, FastAPI |

## Quick Examples

### Ingest and Search

```bash
# Install and configure
pip install -e .
export SECONDBRAIN_OPENAI_API_KEY="..."

# Start MongoDB
secondbrain start --wait

# Ingest documents
secondbrain ingest ./my_documents/ --recursive --cores 4

# Search
secondbrain search "what topics are covered?"
```

### Interactive Chat with Documents

```bash
# Ask questions interactively
secondbrain chat --session research

# Or single query
secondbrain chat "Summarize the key findings" --show-sources
```

## Use Cases

### Research Assistant

```bash
# Ingest research papers
secondbrain ingest ~/Papers/ --recursive --file-type pdf

# Explore topics
secondbrain search "reinforcement learning techniques"
secondbrain search "natural language processing trends"

# Chat about findings
secondbrain chat --session rl-research "What methodologies are used?"
```

### Knowledge Base Query

```bash
# Index documentation
secondbrain ingest ./docs/ --recursive --file-type md

# Search with high precision
secondbrain search "API authentication" --min-score 0.7

# Get detailed answer
secondbrain chat "How do I authenticate to the API?"
```

### Content Analysis

```bash
# Index mixed content
secondbrain ingest ./content/ --recursive

# Aggregate insights
secondbrain ls --all > inventory.txt
secondbrain search "performance optimization" --top-k 20
secondbrain status
```