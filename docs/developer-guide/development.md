# Development Setup

Complete guide to setting up and working with the SecondBrain codebase.

## Prerequisites

- **Python 3.11+**
- **Git**
- **MongoDB 8.0+** (via Docker or local)
- **sentence-transformers** (via Docker or local)

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Install Dependencies

```bash
# Install with dev dependencies
pip install -e ".[dev]"
```

### 4. Install Pre-commit Hooks

```bash
pre-commit install
```

### 5. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your settings
nano .env
```

## Development Workflow

### Running the Application

```bash
# Development mode with auto-reload
python -m secondbrain --help

# Or use the CLI directly
secondbrain --help
```

### Running Tests

```bash
# Fast profile (default)
pytest

# With coverage
pytest --cov=secondbrain --cov-report=term-missing

# Integration tests
pytest -m integration

# Specific test file
pytest tests/test_document.py
```

### Code Quality

```bash
# Linting
ruff check .

# Formatting
ruff format .

# Type checking
mypy .

# All checks
ruff check . && ruff format . && mypy .
```

### Pre-commit Hooks

```bash
# Run all hooks manually
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

## Project Structure

```
secondbrain/
├── src/
│   └── secondbrain/
│       ├── __init__.py
│       ├── cli/           # CLI commands
│       ├── core/          # Core logic
│       ├── storage/       # Database operations
│       ├── embedding/     # Embedding generation
│       ├── utils/         # Utilities
│       └── config.py      # Configuration
├── tests/
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── conftest.py       # Test fixtures
├── docs/                 # Documentation
├── pyproject.toml        # Project configuration
└── requirements*.txt     # Dependencies
```

## Debugging

### Using pdb

```python
import pdb; pdb.set_trace()
```

### Using VS Code

1. Set breakpoints in code
2. Run "Python: Debug Current File"
3. Use debug console for inspection

### Logging

```bash
# Enable debug logging
SECONDBRAIN_LOG_LEVEL=DEBUG secondbrain ingest ./docs/
```

## Common Tasks

### Adding a New Command

1. Create command in `src/secondbrain/cli/commands.py`
2. Add Click decorator
3. Add to CLI group
4. Write tests
5. Update documentation

### Modifying Configuration

1. Update `src/secondbrain/config.py`
2. Add to `.env.example`
3. Update [Configuration Guide](configuration.md)
4. Add validation tests

### Database Changes

1. Update models in `src/secondbrain/storage/models.py`
2. Write migration if needed
3. Update [Schema Reference](../architecture/SCHEMA.md)
4. Test with integration tests

## Performance Testing

```bash
# Run benchmarks
pytest --benchmark-only

# Profile code
python -m cProfile -o profile.out -m secondbrain ingest ./docs/
```

## Contributing

See [Contributing Guide](contributing.md) for detailed contribution guidelines.

## Troubleshooting

### Import Errors

```bash
# Reinstall in development mode
pip install -e ".[dev]" --force-reinstall
```

### Test Failures

```bash
# Run with verbose output
pytest -v

# Show captured output
pytest -s
```

### Dependency Issues

```bash
# Clean and reinstall
pip uninstall secondbrain
pip install -e ".[dev]"
```

## Next Steps

- [Docker Setup](docker.md) - Containerized development
- [Testing Guide](TESTING.md) - Comprehensive testing
- [Code Standards](code-standards.md) - Coding guidelines
