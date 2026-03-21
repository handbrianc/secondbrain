# SecondBrain - Local Document Intelligence CLI

A local document intelligence CLI tool that ingests documents, generates embeddings using sentence-transformers, and stores vectors in MongoDB for semantic search.

## Documentation

- **[Full Documentation](docs/index.md)** - Complete documentation index
- **[Quick Start](#quick-start)** - Get started in 5 minutes
- **[Getting Started](docs/getting-started/index.md)** - Installation and setup
- **[User Guide](docs/user-guide/index.md)** - Complete usage guide
- **[Developer Guide](docs/developer-guide/index.md)** - Development setup and workflow
- **[Configuration](docs/getting-started/configuration.md)** - Configuration reference
- **[Async Guide](docs/developer-guide/async-api.md)** - Asynchronous API usage
- **[Docker Setup](docs/developer-guide/docker.md)** - Containerized deployment
- **[Building](docs/developer-guide/building.md)** - Create distributable binaries
- **[SBOM & Security](docs/architecture/SBOM_ANALYSIS.md)** - Dependency analysis and license compliance

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 8.0+ (via Docker or local)
- sentence-transformers (via Docker or local)

### Installation

```bash
# Start services (Docker)
docker-compose up -d  # MongoDB
sentence-transformers serve          # sentence-transformers (macOS/Linux)

# Install SecondBrain
pip install -e ".[dev]"

# Verify
secondbrain --help
```

### Basic Usage

```bash
# Ingest documents
secondbrain ingest /path/to/documents/

# Search semantically
secondbrain search "what is this about?"

# List documents
secondbrain ls

# Check health
secondbrain health
```

## Features

- **Multi-format ingestion**: PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, audio
- **Semantic search**: Natural language queries with cosine similarity
- **Async support**: Full async API for embedding generation and storage
- **Multicore processing**: Parallel document ingestion with configurable CPU core count
- **Rate limiting**: Protects sentence-transformers API from overload
- **Circuit breaker**: Automatic service failure handling with automatic recovery
- **Structured logging**: JSON logs with OpenTelemetry tracing support
- **Security scanning**: Integrated vulnerability detection and SBOM generation
- **12-factor app**: Environment-driven configuration

## CLI Reference

| Command | Description |
|---------|-------------|
| `ingest` | Add documents to the vector database |
| `search` | Perform semantic search queries |
| `ls` | List ingested documents/chunks |
| `delete` | Remove documents |
| `status` | Display database statistics |
| `health` | Check service health |

```bash
# See all options
secondbrain --help
secondbrain ingest --help
secondbrain search --help

# Ingest with multicore support (4 CPU cores)
secondbrain ingest /path/to/documents --cores 4

# Use config default (set SECONDBRAIN_MAX_WORKERS=4 in .env)
secondbrain ingest /path/to/documents
```

## Configuration

Key environment variables (see [Full Config](docs/getting-started/configuration.md)):

```bash
# .env file
SECONDBRAIN_MONGO_URI=mongodb://localhost:27017
SECONDBRAIN_CHUNK_SIZE=4096
```

## Development

### Quality Checks

```bash
# Linting and formatting
ruff check . && ruff format .

# Type checking
mypy .

# Tests (fast profile - default, 4 workers, no coverage)
pytest -m "not integration"

# Tests with coverage (slower, for CI/release)
pytest --cov=secondbrain --cov-report=term-missing

# More parallelism (8 workers)
pytest -n 8

# Full test suite (requires MongoDB + sentence-transformers)
pytest

# All checks
ruff check . && ruff format --check . && mypy . && pytest -m "not integration"
```

### Test Performance

**Default configuration** uses 4 parallel workers without coverage for fast local feedback (~5s for unit tests).

**Shell aliases** (add to `~/.bashrc` or `~/.zshrc`):
```bash
alias pytest-fast="pytest -m 'not integration' -n 4 --no-cov"
alias pytest-full="pytest --cov=secondbrain --cov-report=term-missing"
alias pytest-ci="pytest -m 'not integration' -n 8 --cov=secondbrain --cov-report=xml"
```

### Test Profiles

The test suite supports different execution profiles:

| Profile | Command | Duration | Use Case |
|---------|---------|----------|----------|
| **Fast** | `pytest -m "not integration"` | ~5s | Pre-commit, quick feedback |
| **Integration** | `pytest -m integration` | ~15s | Nightly builds, service testing |
| **Slow (E2E)** | `pytest -m slow` | ~16s | Release validation |
| **Full** | `pytest` | ~25s | Complete validation |

See [TESTING.md](docs/developer-guide/TESTING.md) and [TESTING_OPTIMIZATION.md](tests/TESTING_OPTIMIZATION.md) for detailed testing documentation.

### Coverage Cleanup

To manually cleanup coverage files after test runs:

```bash
./scripts/cleanup_coverage.sh
```

### Performance Tips

- Use `--batch-size` for parallel processing
- Adjust `chunk_size` for your document types
- Enable verbose mode for timing info: `--verbose`
- Use `-n auto` for parallel test execution (pytest-xdist)
- Tests timeout after 60s to catch hangs (`--timeout=60`)
- Mark slow tests with `@pytest.mark.slow` to exclude from fast profile

## Architecture

See the [Architecture Documentation](docs/architecture/index.md) for:
- High-level system architecture
- Component details and responsibilities
- Data flow diagrams
- Processing pipelines
- Performance considerations
- Error handling strategies
- Circuit breaker pattern implementation
- **SBOM Analysis** - Complete dependency inventory and risk assessment
- **License Compliance** - License risk classification and approval status

And [Schema Reference](docs/architecture/SCHEMA.md) for database structure.

## Examples

Check out the [docs/examples/](docs/examples/README.md) directory for usage examples:

- **[Circuit Breaker Usage](docs/examples/README.md)** - See examples overview
- **[Async Ingestion](docs/developer-guide/async-api.md)** - Async API usage guide
- **[Tracing Example](docs/developer-guide/development.md)** - Development setup with tracing

## Security

Run security scans before commits (automatically cleans old reports):

```bash
# Full security scan
./scripts/security_scan.sh all

# Individual checks
./scripts/security_scan.sh audit    # pip-audit dependency scan
./scripts/security_scan.sh safety   # Safety vulnerability check
./scripts/security_scan.sh bandit   # Code security scan
./scripts/security_scan.sh sbom     # Generate SBOM

# Manual report cleanup
./scripts/cleanup_reports.sh
```

All security and SBOM reports are automatically cleaned before generating new ones. See [docs/developer-guide/security.md](docs/developer-guide/security.md) for detailed security guidelines.

See [docs/migration.md](docs/migration.md) for upgrade notes and [docs/getting-started/troubleshooting.md](docs/getting-started/troubleshooting.md) for common issues.

## License

This project is licensed under the MIT License. See [LICENSE](docs/LICENSE.md) for details.

## Shell Completion

SecondBrain supports shell completion for bash, zsh, and fish shells. Click provides this functionality automatically.

To enable completion, add the following to your shell configuration file (`~/.bashrc`, `~/.zshrc`, `~/.bash_profile`):

### Bash
```bash
eval "$(_SECONDBRAIN_COMPLETE=bash_source secondbrain)"
```

### Zsh
```bash
eval "$(_SECONDBRAIN_COMPLETE=zsh_source secondbrain)"
```

### Fish
```fish
_secondbrain_complete=fish_source secondbrain | source
```

After adding the configuration, restart your shell or run `source ~/.your_shellrc` to apply the changes.

