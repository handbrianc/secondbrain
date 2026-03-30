# Contributing to SecondBrain

Thank you for your interest in contributing to SecondBrain! This document provides guidelines and instructions for contributing.

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md) to maintain a welcoming and inclusive community.

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check the issue tracker to avoid duplicates. When creating a bug report, include:

- **Clear title and description**
- **Steps to reproduce** the behavior
- **Expected vs actual behavior**
- **Environment details** (OS, Python version, MongoDB version)
- **Logs or error messages** if applicable

### Suggesting Enhancements

Feature suggestions are welcome! Please provide:

- **Clear description** of the feature
- **Use case** - why is this needed?
- **Proposed solution** (if you have one)
- **Alternatives considered**

### Pull Requests

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the code style guidelines
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Run the full test suite** and ensure all checks pass
6. **Submit a pull request** with a clear description

## Development Setup

### Prerequisites

- Python 3.11+
- MongoDB 6.0+
- Git

### Quick Start

```bash
# Clone your fork
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=secondbrain --cov-report=html

# Run specific test file
pytest tests/test_document.py

# Run tests with verbose output
pytest -v
```

### Code Style

We use the following tools for code quality:

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

### Dependency Management

When adding or updating dependencies:

1. **Add to pyproject.toml**: Add dependencies to the appropriate section (`dependencies` or `dev`)
2. **Pin versions**: Use version constraints (e.g., `>=1.0.0,<2.0.0`)
3. **Run security scan**: Check for vulnerabilities
   ```bash
   ./scripts/audit_dependencies.sh
   ```
4. **Validate**: Run dependency validation
   ```bash
   ./scripts/validate_dependencies.sh
   ```
5. **Document**: If adding a new dependency, explain why in the PR description

For detailed dependency management procedures, see the [Dependency Management Guide](docs/developer-guide/dependency-management.md).

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new document export functionality
fix: resolve memory leak in batch ingestion
docs: update installation instructions
refactor: simplify chunking logic
test: add unit tests for semantic search
chore: update dependencies
```

## Development Guidelines

### Type Safety

- Always use type annotations
- No `Any` without justification
- Run `mypy` before committing

### Error Handling

- Use specific exception types
- Provide contextual error messages
- Never use bare `except` clauses

### Testing

- Write tests for new functionality
- Aim for high test coverage
- Use fixtures for test setup
- Test both success and failure cases

### Documentation

- Update README.md for user-facing changes
- Add docstrings for public APIs
- Update relevant documentation files

## Project Structure

```
secondbrain/
├── src/
│   ├── secondbrain/          # Core library
│   ├── secondbrain_cli/      # CLI implementation
│   └── secondbrain_mcp/      # MCP server
├── docs/                     # Documentation
├── tests/                    # Test suite
└── pyproject.toml            # Project configuration
```

## Getting Help

- 📖 Check the [documentation](docs/)
- 🐛 Open an issue for bugs
- 💬 Ask questions in GitHub Discussions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Acknowledgments

We appreciate all contributors! See our [contributors](https://github.com/your-org/secondbrain/graphs/contributors) page for a list of people who have helped make SecondBrain better.
