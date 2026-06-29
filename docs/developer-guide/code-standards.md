# Code Standards

Development standards, style guidelines, and conventions for SecondBrain contributions.

## Python Version

Minimum Python version: **3.11**

New language features may be used freely at this version or above.

## Type Annotations

Strict type checking is enforced via MyPy:

```toml
[tool.mypy]
python_version = "3.11"
strict = true
```

### Function Signatures

All functions must have type annotations:

```python
# Correct
def process_document(path: str, options: dict[str, Any]) -> list[Chunk]:
    ...

# Incorrect - missing types
def process_document(path, options):
    ...
```

### Generic Types

Use concrete generic types rather than bare generics:

```python
# Preferred
def fetch_items() -> list[Item]:
    ...

# Acceptable for heterogeneous lists
def fetch_mixed() -> list[Any]:
    ...

# Discouraged
def fetch_items() -> list:
    ...
```

## Linting

Powered by Ruff with strict rules:

```toml
[tool.ruff]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "PTH", "RUF", "D"]
ignore = ["E501"]  # Line length handled separately
```

### Imports

Organize with isort conventions:

```python
# Standard library
import os
import sys
from typing import Any

# Third-party
import click
from pydantic import Field

# Local application
from secondbrain.config import config
from secondbrain.storage import ChunkInfo
```

Never use wildcard imports:

```python
# Forbidden
from secondbrain.config import *
```

## Docstrings

Follow numpy convention with Sphinx processing for MkDocs:

```python
def calculate_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        vector_a: First vector for comparison.
        vector_b: Second vector for comparison.

    Returns:
        Cosine similarity score ranging from -1.0 (opposite) to 1.0 (identical).

    Raises:
        ValueError: If vectors have unequal lengths.

    Examples:
        >>> calculate_similarity([1.0, 0.0], [1.0, 0.0])
        1.0
        >>> calculate_similarity([1.0, 0.0], [-1.0, 0.0])
        -1.0
    """
```

## File Organization

### Imports in __init__

Keep `__init__.py` exports minimal:

```python
# secondbrain/config/__init__.py
"""Configuration module."""

from secondbrain.config.settings import Settings

__all__ = ["Settings", "get_settings"]
```

Avoid importing implementation details in `__init__.py`.

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Modules | snake_case | `async_client.py` |
| Classes | PascalCase | `AsyncStorageClient` |
| Functions | snake_case | `get_connection()` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES` |
| Variables | snake_case | `connection_pool` |
| Type aliases | PascalCase | `ChunkMap` |
| Private methods | _prefix | `_internal_state()` |

## Testing Standards

### Test Organization

Tests mirror source structure in `tests/`:

```
tests/
├── secondbrain/
│   ├── config/
│   │   └── test_settings.py
│   ├── storage/
│   │   └── test_async_client.py
│   └── test_main.py
```

### Test Naming

Pattern: `test_<functionality>_<scenario>`

```python
def test_search_returns_empty_when_no_matches():
    ...

def test_search_filters_by_source_with_regex():
    ...
```

### Fixtures

Use pytest fixtures from `conftest.py`:

```python
@pytest.fixture
def sample_chunks() -> list[Chunk]:
    return [Chunk(content="Test", metadata={})]
```

## Error Handling

### Custom Exceptions

Define in `exceptions.py`:

```python
class ValidationError(Exception):
    """Raised when input validation fails."""
    pass
```

### Specific Except Clauses

Catch specific exceptions, not bare `Exception`:

```python
# Preferred
except ValueError as e:
    logger.warning("Invalid input: %s", e)

# Discouraged
except Exception as e:
    logger.error("Something went wrong: %s", e)
```

## Logging

Use module-level loggers:

```python
logger = logging.getLogger(__name__)
```

Don't use `logging.basicConfig()` — rely on the application's configured logging.

## Commit Messages

Follow conventional commits:

```
feat: add async embedding batch support
fix: resolve race condition in chunk storage
docs: update CLI reference for search command
test: add integration tests for RAG pipeline
refactor: extract vector similarity calculation
```

## Pull Request Guidelines

1. **Scope**: One feature or fix per PR
2. **Description**: Explain motivation and approach
3. **Tests**: Include tests for new functionality
4. **Documentation**: Update docs for user-facing changes
5. **CI**: All checks must pass before merge

## Pre-commit Checklist

Before pushing:

```bash
# Format code
ruff format src/

# Lint
ruff check src/

# Type check
mypy src/secondbrain/

# Test
pytest

# Security scan
bandit -r src/
```