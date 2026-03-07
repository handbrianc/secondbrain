# Contributing to SecondBrain

Thank you for your interest in contributing to SecondBrain! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment for everyone.

## How Can I CONTRIBUTE?

### Reporting Bugs

Before creating a bug report, please check if the issue has already been reported. When filing a bug report, include:

1. A clear, descriptive title
2. Steps to reproduce the issue
3. Expected behavior
4. Actual behavior
5. Environment details (Python version, OS, dependencies)
6. Relevant logs or error messages

### Suggesting Features

Feature requests should include:

1. A clear description of the proposed feature
2. The problem it solves
3.Any alternative solutions considered
4. Potential implementation approach (if known)

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes following the code standards below
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Ensure code quality checks pass: `ruff check . && ruff format --check . && mypy .`
7. Commit using conventional commits: `git commit -m "feat: add amazing feature"`
8. Push your branch: `git push origin feature/amazing-feature`
9. Open a pull request using the PR template (automatically populated)

## PR Template

When creating a pull request, use the provided template in `.github/PULL_REQUEST_TEMPLATE.md`. Include:

- Summary of changes
- Related issue (if any)
- Testing details
- Checklist completion

- **One feature/fix per PR** - Keep PRs focused
- **Update documentation** - Include examples for new features
- **Add tests** - New functionality needs test coverage
- **Update CHANGELOG** - Highlight breaking changes and new features
- **Self-review** - Review your own code before submitting
- **Address feedback** - Make requested changes promptly

## PR Checklist

Before merging, ensure:

- [ ] Tests pass
- [ ] Linting passes (`ruff check .`)
- [ ] Formatting check passes (`ruff format --check .`)
- [ ] Type checking passes (`mypy .`)
- [ ] Documentation updated
- [ ] CHANGELOG updated (if significant change)
- [ ] PR description is clear and complete

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for local development with MongoDB and Ollama)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS

# Install dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=secondbrain --cov-report=html

# Run specific test file
pytest tests/test_cli/test_cli.py
```

### Code Quality

```bash
# Run linting
ruff check .

# Run formatting
ruff format .

# Run type checking
mypy .

# Run all checks
ruff check . && ruff format --check . && mypy .
```

## Coding Standards

### Python Conventions

- Use type hints for all function signatures
- Follow PEP 8 style guide
- Use 88 character line width (ruff default)
- Import order: standard library, third-party, local
- Use docstrings for all public functions and classes

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Variables | snake_case | `user_name` |
| Functions | snake_case | `get_user()` |
| Classes | PascalCase | `DocumentProcessor` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |

### Commit Conventions

Use conventional commits format:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

Examples:
```
feat: add document classification feature
fix: resolve memory leak in embedding generation
docs: update API documentation
refactor: simplify document ingestion pipeline
```

## Architecture

SecondBrain follows a modular architecture:

```
src/secondbrain/
├── cli/          # CLI commands and interface
├── config/       # Configuration management
├── document/     # Document ingestion and processing
├── embedding/    # Embedding generation via Ollama
├── storage/      # MongoDB vector storage
├── search/       # Semantic search functionality
├── management/   # List, delete, and status operations
└── logging/      # Logging configuration
```

## Security Considerations

- Never commit secrets or credentials
- Use environment variables for sensitive data
- Run `bandit -r secondbrain/` before committing
- Run `safety check` for dependency vulnerabilities

## Questions?

For questions about contributing, please open an issue with the "question" label.
