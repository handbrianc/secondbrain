# Contributing to SecondBrain

Thank you for considering contributing to SecondBrain! This document outlines the guidelines for contributing.

## Development Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/secondbrain.git
   cd secondbrain
   ```

2. **Set up a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install with dev dependencies**

   ```bash
   pip install -e ".[dev]"
   pip install -e ".[test]"
   ```

4. **Install pre-commit hooks**

   ```bash
   pre-commit install
   ```

## Code Quality

Before submitting changes, run:

```bash
# Linting
ruff check . && ruff format --check .

# Type checking
mypy src/

# Tests
pytest -m "not integration"
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Run the full test suite before submitting
4. Update documentation if needed
5. Submit a PR with a clear description of changes

## Coding Standards

- Follow PEP 8 style guidelines
- Use NumPy-style docstrings for all public functions and classes
- Add type annotations to all function signatures
- Keep functions focused and single-purpose
- Write tests for new functionality

## Testing Guidelines

- Unit tests should not require external services (use mocks)
- Integration tests go in `tests/integration/`
- Use pytest markers to categorize tests
- Aim for 80%+ test coverage on new code
