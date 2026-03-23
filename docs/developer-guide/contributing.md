# Contributing Guide

How to contribute to SecondBrain.

## Getting Started

### Prerequisites

- Python 3.11+
- Git
- MongoDB 8.0+ (via Docker or local)
- sentence-transformers (via Docker or local)

### Setup

```bash
# Fork the repository
git clone https://github.com/your-username/secondbrain.git
cd secondbrain

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

## Development Workflow

### 1. Create Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow [Code Standards](code-standards.md)
- Write tests for new functionality
- Update documentation

### 3. Run Tests

```bash
# Fast tests
pytest

# All tests
pytest

# With coverage
pytest --cov=secondbrain
```

### 4. Run Linting

```bash
ruff check .
ruff format .
mypy .
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: add your feature"
```

### Commit Message Format

Use conventional commits:

```
feat: Add new feature
fix: Fix bug
docs: Update documentation
refactor: Refactor code
test: Add tests
chore: Maintenance
```

### 6. Push & Create PR

```bash
git push origin feature/your-feature-name
```

Create a pull request on GitHub.

## Code Review

### PR Checklist

- [ ] Code follows style guidelines
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No linting errors
- [ ] All tests pass
- [ ] Descriptive PR title

### Review Process

1. Automated checks run
2. Maintainer reviews code
3. Address feedback
4. Merge when approved

## Reporting Issues

### Bug Reports

Include:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details
- Logs/error messages

### Feature Requests

Include:
- Problem statement
- Proposed solution
- Use cases
- Alternatives considered

## Code Guidelines

### Style

- Follow [Code Standards](code-standards.md)
- Use type hints
- Write docstrings
- Keep functions small

### Testing

- Write unit tests
- Test edge cases
- Use fixtures
- Aim for >85% coverage

### Documentation

- Update README if needed
- Add docstrings
- Update CLI help text
- Add examples

## Areas of Contribution

### Good First Issues

- Documentation improvements
- Bug fixes
- Test additions
- CLI enhancements

### Advanced Topics

- Performance optimization
- New document parsers
- Storage backends
- Integration features

## Questions?

- [GitHub Discussions](https://github.com/your-username/secondbrain/discussions)
- [Open an Issue](https://github.com/your-username/secondbrain/issues)

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Accept constructive criticism
- Focus on what's best for the community

## Recognition

Contributors are recognized in:
- GitHub contributor list
- Release notes
- Documentation credits

Thank you for contributing to SecondBrain!
