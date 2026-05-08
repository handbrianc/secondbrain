# Dependency Installation Guide

This guide explains all dependency requirements for SecondBrain, organized by use case. Choose the installation profile that matches your needs.

## Overview

SecondBrain has different dependency requirements based on your use case:

| Profile | Command | When to Use |
|---------|---------|-------------|
| **Runtime** | `pip install -e "."` | You just want to use SecondBrain |
| **Development** | `pip install -e ".[dev]"` | You want to develop/contribute to SecondBrain |
| **Qualitative Testing** | `pip install -e ".[qualitative]"` | You want to run safety/accuracy tests |
| **Observability** | `pip install -e ".[opentelemetry]"` | You want distributed tracing |

**Most users**: Start with **Runtime** or **Development** profile.

---

## Runtime Dependencies (Required)

These 19 core packages are needed to **run** SecondBrain. Install with:

```bash
pip install -e "."
```

### Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `click` | CLI framework | >=8.1.0 |
| `docling` | Multi-format document parsing (PDF, DOCX, PPTX, XLSX) | >=2.81.0 |
| `docling-core` | Core types for docling | >=2.48.4 |
| `pymongo` | MongoDB driver (sync) | >=4.6.0 |
| `motor` | MongoDB driver (async) | >=3.0.0 |
| `httpx` | HTTP client for API calls | >=0.28.1 |
| `pydantic` | Data validation and settings | >=2.0.0 |
| `pydantic-settings` | Settings management | >=2.0.0 |
| `rich` | Terminal output formatting | >=14.0.0 |
| `python-dotenv` | Environment variable loading | >=1.2.2 |
| `sentence-transformers` | Embedding model generation | >=5.0.0 |
| `numpy` | Numerical computing for embeddings | >=2.0.0 |
| `torch` | PyTorch for deep learning models | >=2.0.0 |
| `opentelemetry-api` | Observability API | >=1.20.0 |
| `opentelemetry-sdk` | Observability SDK | >=1.20.0 |
| `ollama` | Ollama local LLM client | >=0.1.0 |
| `openai` | OpenAI LLM client | >=1.0.0 |
| `typing_extensions` | Extended typing features | >=4.0.0 |

**Total size**: ~2-3 GB (mostly PyTorch and sentence-transformers models)

---

## Development Dependencies

These 30+ tools are needed to **develop, test, and maintain** SecondBrain. Install with:

```bash
pip install -e ".[dev]"
```

### Development Tool Categories

#### Linting & Formatting
| Package | Purpose |
|---------|---------|
| `ruff` | Fast Python linter and formatter |
| `mypy` | Static type checking |

#### Testing
| Package | Purpose |
|---------|---------|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `pytest-cov` | Code coverage reporting |
| `pytest-xdist` | Parallel test execution |
| `pytest-timeout` | Test timeout enforcement |
| `hypothesis` | Property-based testing |
| `mongomock` | MongoDB mocking for unit tests |

#### Security Scanning
| Package | Purpose |
|---------|---------|
| `bandit` | Security vulnerability scanner |
| `safety` | Dependency vulnerability scanner |
| `pip-audit` | pip dependency audit |
| `cyclonedx-bom` | Software Bill of Materials generation |

#### Quality Analysis
| Package | Purpose |
|---------|---------|
| `vulture` | Find unused code |
| `pipdeptree` | Visualize dependency tree |

#### Documentation
| Package | Purpose |
|---------|---------|
| `mkdocs` | Documentation generator |
| `mkdocstrings` | Auto-generated API docs |
| `mkdocstrings-python` | Python docstring rendering |
| `mkdocs-material` | Material theme for MkDocs |

#### Packaging & Distribution
| Package | Purpose |
|---------|---------|
| `pyinstaller` | Create standalone binaries |
| `wheel` | Build wheel packages |

#### Development Utilities
| Package | Purpose |
|---------|---------|
| `pre-commit` | Git hooks framework |
| `fastapi` | REST API examples |
| `uvicorn` | ASGI server for examples |
| `flask` | Flask integration examples |

#### Document Processing Examples
| Package | Purpose |
|---------|---------|
| `fpdf2` | PDF generation for examples |
| `reportlab` | PDF creation for tests |
| `python-docx` | DOCX document handling |

#### Security-Upgraded Transitive Dependencies
These are upgraded versions of dependencies pulled in by other packages:
- `jinja2>=3.1.6` (XSS fixes)
- `urllib3>=2.6.0` (DoS fixes)
- `setuptools>=78.1.1` (path traversal fix)
- `cryptography>=46.0.0` (TLS fixes)
- `pillow>=11.3.0` (buffer overflow fix)
- `paramiko>=3.5.0` (SSH attack fix)
- And others...

**Total size**: ~4-5 GB (includes all runtime + dev tools)

---

## Optional Dependency Groups

### Qualitative Testing

For safety, factual accuracy, and robustness testing:

```bash
pip install -e ".[qualitative]"
```

**Packages**:
| Package | Purpose |
|---------|---------|
| `llama-cpp-python` | Local LLM inference for evaluation |
| `transformers` | Hugging Face transformers for LLM judge |
| `accelerate` | Accelerate library for model loading |

**Use case**: Running `pytest -m "qualitative"` for advanced evaluation

**Total size**: ~6-8 GB additional (LLM models)

---

### OpenTelemetry Tracing

For distributed tracing and observability:

```bash
pip install -e ".[opentelemetry]"
```

**Packages**:
| Package | Purpose |
|---------|---------|
| `opentelemetry-exporter-otlp` | OTLP exporter for tracing |
| `opentelemetry-instrumentation-pymongo` | MongoDB automatic instrumentation |

**Use case**: Production monitoring with OpenTelemetry collectors

**Total size**: ~50 MB additional

---

## External Service Dependencies

These are **not** pip packages but required services.

### MongoDB 8.0+ (Required)

**Purpose**: Vector storage for embeddings

**Installation Options**:

#### Option 1: Docker (Recommended for Development)
```bash
docker-compose up -d
```

#### Option 2: Homebrew (macOS)
```bash
brew install mongodb-community
brew services start mongodb-community
```

#### Option 3: Official Packages
- **Linux**: Follow [MongoDB Manual](https://www.mongodb.com/docs/manual/administration/install-community/)
- **Windows**: Download from [MongoDB Download Center](https://www.mongodb.com/try/download/community)

**Configuration**: Set `SECONDBRAIN_MONGO_URI` in `.env`

---

### Ollama (Optional - for Local LLM)

**Purpose**: Local large language model provider for conversational Q&A

**Installation**:

#### macOS/Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2  # Or your preferred model
```

#### Docker
```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 ollama/ollama
```

**Configuration**: Set `SECONDBRAIN_LLM_PROVIDER=ollama` and `SECONDBRAIN_OLLAMA_HOST=http://localhost:11434`

---

### Sentence-Transformers Service (Optional - if not using local models)

**Purpose**: Embedding generation service (alternative to local sentence-transformers)

**Installation**:

#### Docker (Recommended)
```bash
docker-compose up -d  # Includes sentence-transformers service
```

#### Local Installation

```bash
# Install the service
pip install sentence-transformers

# Start the service (note: requires sentence-transformers CLI)
# Alternative: Use Docker (recommended)
docker-compose up -d sentence-transformers
```

> **Note**: The `sentence-transformers serve` command requires the sentence-transformers CLI tool. For most users, using Docker Compose is the recommended approach as it includes all necessary dependencies.

**Configuration**: Set `SECONDBRAIN_SENTENCE_TRANSFORMERS_URL=http://localhost:11434`

---

## Installation Profiles

### Profile 1: "I Just Want to Use SecondBrain"

**Goal**: Run SecondBrain for semantic search and document ingestion

**Prerequisites**:
- Python 3.11+
- MongoDB 8.0+ (via Docker or local)
- Sentence-transformers service (via Docker or local)

**Installation**:
```bash
# Clone repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Install runtime dependencies only
# Note: -e (editable) mode is convenient for testing; for production deployment use: pip install .
pip install -e "."

# Start external services
docker-compose up -d  # MongoDB + sentence-transformers

# Verify installation
secondbrain --help
secondbrain health
```

**What You Get**:
- ✅ Full SecondBrain functionality
- ✅ Semantic search
- ✅ Document ingestion
- ✅ Conversational Q&A (with Ollama)
- ❌ No development tools (linting, testing, etc.)

**Disk Space**: ~3 GB

> **Production Note**: The `-e` (editable) flag is convenient for development and testing. For production deployments where you don't need to modify the source code, use `pip install .` instead.

---

### Profile 2: "I Want to Develop SecondBrain"

**Goal**: Contribute to SecondBrain development

**Prerequisites**:
- Python 3.11+
- Git
- MongoDB 8.0+ (via Docker or local)
- Sentence-transformers service (via Docker or local)

**Installation**:
```bash
# Clone repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows

# Install with all development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Start external services
docker-compose up -d  # MongoDB + sentence-transformers

# Verify installation
secondbrain --help
pytest -m "not integration"  # Run fast tests
```

**What You Get**:
- ✅ Everything in Runtime profile
- ✅ Linting and formatting (ruff, mypy)
- ✅ Testing framework (pytest, hypothesis)
- ✅ Security scanning (bandit, safety)
- ✅ Documentation tools (mkdocs)
- ✅ Packaging tools (pyinstaller)
- ✅ Pre-commit hooks

**Disk Space**: ~5 GB

---

### Profile 3: "I Want to Run Qualitative Tests"

**Goal**: Evaluate safety, factual accuracy, and robustness

**Prerequisites**:
- All Profile 2 prerequisites
- Sufficient RAM (16GB+ recommended for LLM models)

**Installation**:
```bash
# Start with dev installation
pip install -e ".[dev]"

# Add qualitative testing dependencies
pip install -e ".[qualitative]"

# Pull LLM model for evaluation
ollama pull llama3.2

# Run qualitative tests
pytest tests/test_qualitative/ -v
```

**What You Get**:
- ✅ Everything in Development profile
- ✅ LLM-based evaluation (llama-cpp-python)
- ✅ Transformers for model inference
- ✅ Accelerate for efficient loading

**Disk Space**: ~8-10 GB additional (LLM models)

---

### Profile 4: "I Want Full Observability"

**Goal**: Production monitoring with distributed tracing

**Prerequisites**:
- Profile 1 or 2
- OpenTelemetry collector (optional)

**Installation**:
```bash
# Install with OpenTelemetry support
pip install -e ".[opentelemetry]"

# Configure tracing in .env
export OTEL_TRACING_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Start OpenTelemetry collector (optional)
docker run -d -p 4317:4317 otel/opentelemetry-collector:latest
```

**What You Get**:
- ✅ OpenTelemetry exporters
- ✅ Automatic MongoDB instrumentation
- ✅ Distributed tracing support

**Disk Space**: ~50 MB additional

---

## Troubleshooting

### Common Issues

#### Python Version Conflicts

**Symptom**: `requires Python >=3.11` error

**Solution**:
```bash
# Check Python version
python --version

# Install Python 3.11+ if needed
brew install python@3.11  # macOS
# Or download from python.org

# Verify
python3.11 --version
```

#### PyTorch CUDA Compatibility

**Symptom**: CUDA errors or slow performance

**Solution**:
```bash
# Check PyTorch installation
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"

# For CPU-only installation (smaller, no GPU)
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# For CUDA 12.x (GPU acceleration)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

#### MongoDB Connection Issues

**Symptom**: `Cannot connect to MongoDB` error

**Solution**:
```bash
# Check if MongoDB is running
docker ps | grep mongo  # Docker
brew services list | grep mongodb  # macOS Homebrew

# Start MongoDB
docker-compose up -d  # Docker
brew services start mongodb-community  # macOS

# Check connection
secondbrain health
```

#### Sentence-Transformers Service Unavailable

**Symptom**: `Connection refused` when generating embeddings

**Solution**:
```bash
# Check service status
curl http://localhost:11434/api/tags  # Docker/local service

# Start service
docker-compose up -d  # Docker
sentence-transformers serve  # Local (requires CLI)

# Pull model if needed
sentence-transformers pull all-MiniLM-L6-v2
```

#### Dependency Conflicts

**Symptom**: `ResolutionImpossible` or version conflicts

**Solution**:
```bash
# Create fresh virtual environment
python -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install with fresh environment
pip install -e ".[dev]"

# Debug conflicts
pip install pipdeptree
pipdeptree  # Show dependency tree
```

#### Installation Fails on Specific Package

**Symptom**: Build errors for specific packages (e.g., `torch`, `docling`)

**Solution**:
```bash
# Install system dependencies first
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y build-essential libgl1 libglib2.0-0

# macOS
xcode-select --install

# Try installing problematic package separately
pip install torch  # Or the specific package

# Then install SecondBrain
pip install -e ".[dev]"
```

#### Virtual Environment Issues

**Symptom**: Packages not found after installation

**Solution**:
```bash
# Ensure virtual environment is activated
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate  # Windows

# Verify activation
which python  # Should show venv path

# Reinstall if needed
pip install -e ".[dev]" --force-reinstall
```

---

### Additional Troubleshooting Resources

For other issues, consult:
- [General Troubleshooting Guide](troubleshooting.md) - Connection issues, configuration problems
- [Dependency Troubleshooting](#troubleshooting) - Package installation conflicts (this page)
- [GitHub Issues](https://github.com/your-username/secondbrain/issues) - Bug reports and known issues

---

## Quick Reference

### Installation Commands Summary

| Use Case | Command | External Services |
|----------|---------|-------------------|
| **Runtime only** | `pip install -e "."` | MongoDB, sentence-transformers |
| **Development** | `pip install -e ".[dev]"` | MongoDB, sentence-transformers |
| **Qualitative tests** | `pip install -e ".[dev]"` + `pip install -e ".[qualitative]"` | MongoDB, sentence-transformers, Ollama |
| **Observability** | `pip install -e ".[opentelemetry]"` | MongoDB, sentence-transformers, OTEL collector |

### External Services Quick Start

```bash
# Start all services with Docker Compose
docker-compose up -d

# Start only MongoDB
docker-compose up -d mongo

# Start only sentence-transformers
docker-compose up -d sentence-transformers

# Stop all services
docker-compose down
```

---

## Next Steps

- [Installation Guide](installation.md) - Step-by-step installation
- [Quick Start](quick-start.md) - Get running in 5 minutes
- [Configuration Guide](configuration.md) - Configure your environment
- [Developer Guide](../developer-guide/development.md) - Development setup

## Need Help?

- [Troubleshooting Guide](troubleshooting.md) - Common issues
- [GitHub Issues](https://github.com/your-username/secondbrain/issues) - Bug reports
- [GitHub Discussions](https://github.com/your-username/secondbrain/discussions) - Questions
