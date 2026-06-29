# Development Setup

Setting up a local development environment for SecondBrain.

## Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Runtime |
| Git | Latest | Version control |
| MongoDB | 4.4+ | Vector storage |
| Docker | Latest | Service containers |

## Clone Repository

```bash
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
```

## Virtual Environment

Create an isolated Python environment:

```bash
# Create environment
python -m venv .venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Verify activation
which python  # Should show .venv/bin/python
```

## Install Dependencies

### Core Dependencies

```bash
pip install -e .
```

### Development Dependencies

Includes linting, testing, and documentation tools:

```bash
pip install -e ".[dev]"
```

Or install subsets:

```bash
# Linting only
pip install -e ".[lint]"

# Testing only
pip install -e ".[test]"

# Documentation only
pip install -e ".[docs]"
```

### Optional Dependencies

Additional functionality groups:

```bash
# Mutation testing
pip install -e ".[mutation]"

# Web frameworks
pip install -e ".[web]"

# RAG with local models
pip install -e ".[rag]"

# OpenTelemetry instrumentation
pip install -e ".[opentelemetry]"
```

## Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```bash
# Required for embedding generation
SECONDBRAIN_OPENAI_API_KEY=your-api-key

# Point to local or Docker MongoDB
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017

# Development settings
SECONDBRAIN_LOG_LEVEL=DEBUG
```

## Start MongoDB

### Option A: Docker

```bash
docker run -d \
  --name secondbrain-mongo \
  -p 27017:27017 \
  mongo:latest
```

### Option B: Local MongoDB

Ensure the mongod service is running:

```bash
mongod --dbpath /data/db
```

### Option C: Docker Compose

```bash
secondbrain start --wait
```

## Verify Installation

Test that SecondBrain is correctly installed:

```bash
# Check version
secondbrain --version

# Run health check
secondbrain health

# Run status check
secondbrain status
```

## Run Tests

### All Tests

```bash
pytest
```

### Specific Test Categories

```bash
# Unit tests only
pytest -m unit

# Integration tests
pytest -m integration

# Fast tests (<50ms)
pytest -m fast

# Slow tests (>1s)
pytest -m slow
```

### With Coverage

```bash
pytest --cov=secondbrain --cov-report=html
open htmlcov/index.html
```

### Parallel Execution

```bash
pytest -n auto
```

Uses pytest-xdist to distribute tests across CPU cores.

## Lint and Type Check

Before submitting changes:

```bash
# Ruff linting
ruff check src/

# MyPy type checking
mypy src/secondbrain/
```

## Pre-commit Hooks

Install pre-commit hooks:

```bash
pre-commit install
```

Hooks run automatically before each commit:

- Ruff formatting and linting
- MyPy type checking
- Import sorting
- Trailing whitespace removal

## IDE Setup

### VS Code

Recommended settings in `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.typeChecking.mode": "strict",
  "python.analysis.autoImportCompletions": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.codeActionsOnSave": {
      "source.fixAll": "explicit",
      "source.organizeImports": "explicit"
    }
  }
}
```

### PyCharm

1. Set Project Interpreter to `.venv/bin/python`
2. Enable ruff plugin
3. Configure mypy plugin for type checking

## Troubleshooting

### Import Errors

```bash
# Reinstall in editable mode
pip install -e .
```

### MongoDB Connection Issues

```bash
# Check MongoDB is running
docker ps | grep mongo

# Test connection
mongosh --eval "db.adminCommand('ping')"
```

### Test Discovery Failures

```bash
# Clear pytest cache
rm -rf .pytest_cache __pycache__
pytest --collect-only
```