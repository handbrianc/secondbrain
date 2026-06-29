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
|---------|---------|----------|
| click | CLI framework | Yes |
| pymongo, motor | MongoDB drivers | Yes |
| docling | Document parsing | Yes |
| httpx | HTTP client | Yes |
| pydantic, pydantic-settings | Configuration | Yes |
| rich | Terminal output | Yes |
| openai | Embedding provider | Yes |

## MongoDB Setup

SecondBrain requires MongoDB for vector storage. Choose one approach:

### Option A: Docker (Recommended)

Start MongoDB using the built-in Docker management:

```bash
secondbrain start --wait
```

This starts a MongoDB container with default settings.

### Option B: Local MongoDB

If you have MongoDB installed locally, ensure it's running:

```bash
mongod --dbpath /data/db
```

### Option C: MongoDB Atlas (Cloud)

For cloud deployments, configure the connection via environment variable:

```bash
export SECONDBRAIN_MONGO_URI="mongodb+srv://username:password@cluster.mongodb.net"
```

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

Expected output confirms MongoDB connectivity and service status.

## Uninstalling

To uninstall SecondBrain:

```bash
pip uninstall secondbrain
```

This removes the package but leaves configuration files and data intact.