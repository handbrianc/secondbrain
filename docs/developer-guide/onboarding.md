# Developer Onboarding Guide

Welcome to SecondBrain! This guide will help you get set up and contributing quickly.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Environment](#development-environment)
- [First Steps](#first-steps)
- [Contributing](#contributing)
- [Common Issues](#common-issues)

---

## Quick Start

### Option 1: Dev Container (Recommended)

The easiest way to get started is using a dev container:

```bash
# In VS Code, press Cmd/Ctrl+Shift+P
# Select "Dev Containers: Reopen in Container"
```

The dev container comes with everything pre-configured:
- Python 3.11
- MongoDB
- All dependencies
- VS Code extensions

### Option 2: Local Setup

```bash
# Clone the repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Run the setup script
./scripts/dev-setup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Set up pre-commit hooks
- Start MongoDB (if not running)
- Create a `.env` file

---

## Development Environment

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Runtime |
| MongoDB | 6.0+ | Vector database |
| Git | 2.x | Version control |
| Node.js | 18+ | (Optional) For docs |

### Project Structure

```
secondbrain/
├── src/secondbrain/          # Main package
│   ├── cli/                  # CLI commands
│   ├── config/               # Configuration
│   ├── document/             # Document processing
│   ├── embedding/            # Embedding generation
│   ├── rag/                  # RAG pipeline
│   ├── search/               # Search functionality
│   ├── storage/              # Database operations
│   └── utils/                # Utilities
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   ├── integration/          # Integration tests
│   └── conftest.py           # Test fixtures
├── docs/                     # Documentation
├── scripts/                  # Utility scripts
├── .devcontainer/            # Dev container config
└── pyproject.toml            # Project config
```

### Environment Variables

Create a `.env` file in the project root:

```bash
# MongoDB connection
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=secondbrain

# Embedding model (optional)
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=text

# Optional: Ollama for RAG
OLLAMA_BASE_URL=http://localhost:11434
```

### IDE Setup

#### VS Code (Recommended)

Install these extensions:
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)
- Docker (ms-azuretools.vscode-docker)

Settings are pre-configured in `.vscode/settings.json`.

#### Other IDEs

Configure:
- **Formatter**: Ruff
- **Linter**: Ruff + Mypy
- **Test Runner**: pytest
- **Python Version**: 3.11+

---

## First Steps

### 1. Verify Installation

```bash
# Run the test suite
pytest

# Run linting
ruff check .
ruff format .

# Type checking
mypy .
```

### 2. Try the CLI

```bash
# Show help
python -m secondbrain --help

# Ingest a document
python -m secondbrain ingest /path/to/document.pdf

# Search
python -m secondbrain search "your query"

# List documents
python -m secondbrain list
```

### 3. Run a Simple Test

```bash
# Run a specific test
pytest tests/unit/test_ingestor.py::test_ingest_text_file -v

# Run with coverage
pytest --cov=secondbrain --cov-report=html
```

### 4. Make Your First Change

1. Create a branch: `git checkout -b feature/your-feature`
2. Make changes
3. Run tests: `pytest`
4. Run linting: `ruff check . && ruff format .`
5. Commit: `git commit -m "feat: your feature"`
6. Push: `git push origin feature/your-feature`
7. Open a PR

---

## Contributing

### Development Workflow

```bash
# Create a feature branch
git checkout -b feature/my-feature

# Make changes
# ... edit files ...

# Run tests
pytest

# Run linting
ruff check .
ruff format .

# Type check
mypy .

# Commit (pre-commit hooks will run)
git commit -m "feat: add new feature"

# Push and create PR
git push origin feature/my-feature
```

### Code Style

- **Formatting**: Ruff (88 char line length, double quotes)
- **Imports**: Sorted alphabetically, grouped by type
- **Type Hints**: Required for all function signatures
- **Docstrings**: NumPy style for all public functions
- **Testing**: pytest with async support

### Commit Messages

Use conventional commits:

```
feat: add new feature
fix: resolve bug issue
docs: update documentation
refactor: code restructuring
test: add tests
chore: maintenance tasks
```

### Pull Request Process

1. **Title**: Use conventional commit format
2. **Description**: Include:
   - What changes were made
   - Why the changes were made
   - How to test the changes
   - Screenshots (if UI changes)
3. **Checks**: All CI checks must pass
4. **Review**: At least one approval required

### First Time Contributors

Look for issues labeled:
- `good first issue` - Simple tasks
- `help wanted` - Need external help
- `documentation` - Documentation improvements

---

## Common Issues

### MongoDB Connection Failed

**Symptoms**: `Connection refused` error

**Solutions**:
```bash
# Check if MongoDB is running
pgrep -x mongod

# Start MongoDB
mongod --fork --logpath /tmp/mongodb.log

# Or using Docker
docker run -d -p 27017:27017 mongo:6
```

### Virtual Environment Issues

**Symptoms**: Import errors, package not found

**Solutions**:
```bash
# Recreate virtual environment
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Pre-commit Hooks Failing

**Symptoms**: Commit rejected by pre-commit

**Solutions**:
```bash
# Run pre-commit manually
pre-commit run --all-files

# Fix formatting issues
ruff format .

# Fix linting issues
ruff check . --fix

# Skip hooks (not recommended)
git commit --no-verify -m "message"
```

### Test Failures

**Symptoms**: Tests failing locally

**Solutions**:
```bash
# Run tests with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_xyz.py -v

# Clear pytest cache
pytest --cache-clear

# Run with coverage to see what's tested
pytest --cov=secondbrain --cov-report=term-missing
```

### GPU Memory Issues

**Symptoms**: CUDA out of memory

**Solutions**:
```bash
# Use CPU instead
export EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# Or reduce batch size in code
embeddings = model.encode(texts, batch_size=16)  # Lower from 32

# Clear GPU cache
python -c "import torch; torch.cuda.empty_cache()"
```

### Slow Ingestion

**Symptoms**: Documents taking too long to ingest

**Solutions**:
```bash
# Enable batch processing
python -m secondbrain ingest /path/to/docs/ --batch-size 10

# Use GPU if available
# Check: python -c "import torch; print(torch.cuda.is_available())"

# Increase worker count
export INGEST_WORKERS=4
```

---

## Getting Help

- **Documentation**: [docs/](../docs/)
- **Issues**: [GitHub Issues](https://github.com/your-org/secondbrain/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/secondbrain/discussions)
- **Code Review**: Ask in PR comments

---

## Next Steps

1. ✅ Complete setup (this guide)
2. 📖 Read [Developer Guide](../docs/developer-guide/index.md)
3. 📖 Read [Architecture Guide](../docs/architecture/index.md)
4. 🐛 Pick a `good first issue`
5. 💡 Make your first contribution!

---

**Happy coding! 🚀**
