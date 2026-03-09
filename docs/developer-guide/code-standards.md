# Code Standards

This document outlines the coding standards and best practices for the SecondBrain project.

## Python Version

- **Minimum**: Python 3.11
- **Recommended**: Python 3.12

## Code Quality Tools

The project uses the following tools:

| Tool | Purpose | Configuration |
|------|---------|------------------|
| ruff | Linting & Formatting | `pyproject.toml` |
| mypy | Type Checking | `pyproject.toml` |
| pytest | Testing | `pyproject.toml` |
| bandit | Security Scanning | `pyproject.toml` |
| safety | Dependency Vulnerabilities | `pyproject.toml` |

## Style Guidelines

### Imports

Order imports alphabetically within groups:

```python
# Standard library first
import os
import sys
from pathlib import Path

# Third-party imports
import click
from pydantic import Field

# Local imports
from secondbrain.config import Config
```

### Type Hints

Always use type hints:

```python
def process_data(users: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    ...
```

### Naming Conventions

| Element | Convention | Example |
|---------|----------|--------|
| Variables | snake_case | `user_name` |
| Functions | snake_case | `get_user_by_id()` |
| Classes | PascalCase | `UserManager` |
| Constants | UPPER_SNAKE | `MAX_RETRIES` |
| Modules | snake_case | `user_service.py` |

### Formatting

- Line length: 88 characters (ruff default)
- Indentation: 4 spaces
- No trailing whitespace
- Blank lines: Two between top-level definitions

## Error Handling

- Use specific exception types
- Never use bare `except`
- Provide context in error messages

```python
# Good
raise ValueError(f"Invalid timeout value '{value}'. Expected positive integer.")

# Avoid
raise Exception("Something went wrong")
```

## Testing

- Use pytest fixtures for setup
- Test behavior, not implementation
- Use `pytest.mark.parametrize` for multiple test cases
- Maintain >= 80% code coverage

## CLI Design (Click)

- Use Click decorators
- Group related commands
- Provide help text for all options

## Security

- No hardcoded secrets
- Use environment variables for sensitive data
- Run security scans regularly

## Git Conventions

Use conventional commits:

```
feat: add user authentication
fix: resolve timeout issue in CLI
docs: update README
refactor: simplify config loading
```

## Related Documentation

- [Development Guide](./development.md) - Development workflow
- [Contributing](./contributing.md) - Contribution guidelines
