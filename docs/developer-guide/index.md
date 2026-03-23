# Developer Guide

Welcome to the SecondBrain developer documentation. This guide covers everything you need to contribute to the project.

## Overview

SecondBrain is a local document intelligence CLI built with:

- **Python 3.11+** with async support
- **Click** for CLI interface
- **Pydantic** for configuration validation
- **MongoDB** for vector storage
- **sentence-transformers** for embedding generation
- **Docling** for document parsing

## Getting Started

### Quick Setup

```bash
# Clone and setup
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

### Development Environment

- [Environment Setup](development.md) - Prerequisites and installation
- [Docker Setup](docker.md) - Containerized development
- [Testing](TESTING.md) - Running and writing tests
- [Code Standards](code-standards.md) - Coding guidelines

## Documentation Navigation

### Setup & Configuration
- [Development Setup](development.md) - Full development workflow
- [Docker Setup](docker.md) - Containerized development and deployment
- [Configuration](configuration.md) - Environment variables and settings
- [Building & Distribution](building.md) - Create distributable binaries

### Development Practices
- [Code Standards](code-standards.md) - Coding guidelines and best practices
- [Async API Guide](async-api.md) - Asynchronous programming patterns
- [Testing Guide](TESTING.md) - Test structure and coverage
- [Test Performance](TEST_PERFORMANCE_OPTIMIZATION.md) - Optimizing test execution
- [CLI Best Practices](python-cli-best-practices-checklist.md) - Python CLI guidelines
- [Contributing](contributing.md) - How to contribute to the project

### Architecture & Design
- [Architecture Overview](../architecture/index.md) - System design and data flow
- [Schema Reference](../architecture/SCHEMA.md) - Database schema
- [Data Flow](../architecture/DATA_FLOW.md) - Component interactions
- [Migrations](migrations.md) - Schema migration strategies

### Maintenance & Operations
- [Security Guide](security.md) - Security guidelines and practices
- [Changelog](changelog.md) - Version history and changes

## Examples

For practical usage examples, see the [examples directory](../examples/README.md):

- **Basic Usage**: Simple CLI-style examples
- **Advanced**: Custom chunking, batch processing, async workflows
- **Integrations**: Flask and FastAPI REST APIs

## API Documentation

- [API Reference](../api/index.md) - Auto-generated API documentation
- [CLI Reference](../user-guide/cli-reference.md) - Command-line interface
- [Types](../api/index.md) - Type definitions and data models

## Quick Developer Tasks

### Running Tests

```bash
# Fast tests (default)
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

### Running the Application

```bash
# Development mode
python -m secondbrain --help

# With debug logging
SECONDBRAIN_LOG_LEVEL=DEBUG secondbrain ingest ./docs/
```

### Common Development Tasks

**Adding a New Command:**
1. Create command in `src/secondbrain/cli/commands.py`
2. Add Click decorator
3. Add to CLI group
4. Write tests
5. Update documentation

**Modifying Configuration:**
1. Update `src/secondbrain/config.py`
2. Add to `.env.example`
3. Update [Configuration Guide](configuration.md)
4. Add validation tests

**Database Changes:**
1. Update models in `src/secondbrain/storage/models.py`
2. Write migration if needed
3. Update [Schema Reference](../architecture/SCHEMA.md)
4. Test with integration tests

## Contributing

Interested in contributing? Read our [Contributing Guide](contributing.md) to get started.

### Quick Contribution Ideas

- Fix bugs or typos
- Improve documentation
- Add tests for edge cases
- Enhance CLI commands

## Support

- [Open an Issue](https://github.com/your-username/secondbrain/issues) - Bug reports and feature requests
- [Discussions](https://github.com/your-username/secondbrain/discussions) - Community discussions
