# Installation Guide

This guide covers installing SecondBrain and all required dependencies.

## Standard Installation

### 1. Install from Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
pip install -e .
```

### 2. Verify Installation

Confirm SecondBrain is installed correctly:

```bash
secondbrain --version
```

Expected output: `secondbrain, version 0.4.0`

## Dependency Overview

SecondBrain depends on several key packages:

| Package | Purpose | Required |
| --------- | --------- | ---------- |
| click | CLI framework | Yes |
| qdrant-client | Qdrant vector database client | Yes |
| aiosqlite / sqlite | SQLite conversation storage | Yes |
| docling | Document parsing | Yes |
| httpx | HTTP client | Yes |
| pydantic, pydantic-settings | Configuration | Yes |
| rich | Terminal output | Yes |
| openai | Embedding provider | Yes |

## Qdrant Setup

SecondBrain uses Qdrant for vector storage and SQLite for conversations/sessions. To get started, run the built-in
Docker management to start the Qdrant service:

```bash
secondbrain start --wait
```

This starts the `secondbrain-qdrant` container with default settings (collection `embeddings`).

If you have Qdrant running elsewhere, point to it via the `SECONDBRAIN_QDRANT_URL` environment variable (for
example `http://localhost:6333`). Conversations and sessions are stored locally in the SQLite database at
`~/.secondbrain/secondbrain.db` — no additional setup is required.

## API Key Configuration

For embedding generation, configure your API key:

```bash
export SECONDBRAIN_OPENAI_API_KEY="your-api-key-here"
```

Alternatively, for OpenAI-compatible providers (Ollama, LM Studio, vLLM):

```bash
export SECONDBRAIN_OPENAI_API_KEY="not-required"
export SECONDBRAIN_OPENAI_BASE_URL="http://localhost:11434/v1"
```

## Verifying Your Setup

Run the health check to verify all services are operational:

```bash
secondbrain health
```

Expected output confirms Qdrant connectivity and service status.

## Uninstalling

To uninstall SecondBrain:

```bash
pip uninstall secondbrain
```

This removes the package but leaves configuration files and data intact.
