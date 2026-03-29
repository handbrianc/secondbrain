# Developer Guide

Welcome to the SecondBrain developer guide. This section contains everything you need to contribute to the project.

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 6.0+
- Git

### Setup

```bash
# Clone repository
git clone https://github.com/your-org/secondbrain.git
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Documentation Index

### Getting Started
- [Development Setup](development.md) - Environment configuration
- [Contributing](contributing.md) - Contribution guidelines
- [Code Standards](code-standards.md) - Coding conventions

### Advanced Topics
- [Async API](async-api.md) - Asynchronous programming
- [Configuration](configuration.md) - Advanced configuration
- [Testing](TESTING.md) - Testing strategies
- [Security](security.md) - Security best practices
- [Docker](docker.md) - Container deployment
- [Building](building.md) - Build process
- [Migrations](migrations.md) - Database migrations

### Performance
- [Best Practices](python-cli-best-practices-checklist.md) - CLI optimization
- [Performance Testing](TEST_PERFORMANCE_OPTIMIZATION.md) - Benchmarking

### Reference
- [Changelog](changelog.md) - Version history

## Development Workflow

1. **Fork the repository**
2. **Create a branch** for your feature
3. **Make changes** following code standards
4. **Write tests** for new functionality
5. **Run pre-commit hooks**
6. **Submit a pull request**

## Code Quality

### Linting

```bash
# Run linter
ruff check .

# Auto-fix issues
ruff check . --fix
```

### Formatting

```bash
# Format code
ruff format .
```

### Type Checking

```bash
# Run mypy
mypy .
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=secondbrain --cov-report=html
```

## Getting Help

- 📖 Read the documentation
- 🐛 Open an issue for bugs
- 💬 Ask questions in GitHub Discussions
- 🤝 Join the contributor community

## See Also

- [Main Documentation](../index.md)
- [Contributing Guide](../CONTRIBUTING.md)
- [API Reference](../api/index.md)
