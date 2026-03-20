# Code Standards

Coding standards and best practices for SecondBrain.

## Code Style

### Formatting

- **Line Length**: 88 characters (ruff default)
- **Indentation**: 4 spaces
- **No trailing whitespace**
- **Two blank lines** between top-level definitions
- **One blank line** between methods

### Imports

```python
# Standard library first
import os
import sys
from pathlib import Path

# Third-party
import click
from typing_extensions import Protocol

# Local imports last
from . import utils
from .core import BaseClass
```

### Type Annotations

```python
from typing import Any, Dict, List, Optional

def process_data(
    users: List[Dict[str, str]],
    max_count: Optional[int] = None
) -> Dict[str, Any]:
    ...
```

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Variables | snake_case | `user_name`, `max_count` |
| Functions | snake_case | `get_user_by_id()` |
| Classes | PascalCase | `UserManager`, `ConfigLoader` |
| Constants | UPPER_SNAKE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Modules | snake_case | `user_service.py` |

## Error Handling

### Use Specific Exceptions

```python
# Good
raise ValueError("Invalid email format")
raise FileNotFoundError(f"Config not found: {path}")

# Avoid
raise Exception("Something went wrong")
```

### Handle Exceptions Explicitly

```python
try:
    result = process()
except ProcessingError as e:
    logger.warning(f"Processing failed: {e}")
    raise
```

### Never Use Bare Except

```python
# Good
except (ValueError, TypeError) as e:
    logger.error(f"Invalid input: {e}")

# Avoid
except:
    pass
```

## Documentation

### Docstrings

```python
def process_document(
    path: Path,
    chunk_size: int = 4096
) -> List[Document]:
    """Process a document into chunks.

    Args:
        path: Path to document file
        chunk_size: Size of each chunk in characters

    Returns:
        List of document chunks

    Raises:
        FileNotFoundError: If document doesn't exist
        ValueError: If chunk_size is invalid
    """
```

### Type Hints

Always use type hints for function signatures.

## Testing

### Test Structure

```python
def test_document_ingestion(tmp_path):
    """Test that documents are ingested correctly."""
    # Arrange
    doc_path = tmp_path / "test.pdf"
    doc_path.write_bytes(sample_pdf)
    
    # Act
    result = ingest_document(doc_path)
    
    # Assert
    assert result is not None
    assert len(result.chunks) > 0
```

### Test Naming

```python
# Good
def test_ingest_returns_correct_chunk_count()
def test_search_with_invalid_query_raises_error()

# Avoid
def test_stuff()
def test_1()
```

## Performance

### Use Async for I/O

```python
# Good
async def ingest_async(path: Path):
    await storage.ingest(path)

# Avoid (blocking I/O in async context)
def ingest_sync(path: Path):
    storage.ingest(path)  # Blocks event loop
```

### Batch Operations

```python
# Good
for batch in chunked(documents, 10):
    await storage.insert_many(batch)

# Avoid
for doc in documents:
    await storage.insert(doc)
```

## Security

### Input Validation

```python
from pydantic import BaseModel, Field

class IngestRequest(BaseModel):
    path: str = Field(..., min_length=1)
    chunk_size: int = Field(default=4096, ge=512, le=8192)
```

### Never Trust User Input

```python
# Good
safe_path = Path(user_input).resolve()
if not safe_path.is_relative_to(base_dir):
    raise ValueError("Invalid path")

# Avoid
path = Path(user_input)  # Vulnerable to path traversal
```

## Tools

### Linting

```bash
ruff check .
```

### Formatting

```bash
ruff format .
```

### Type Checking

```bash
mypy .
```

### Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

## Code Review Checklist

- [ ] Code follows style guidelines
- [ ] Type hints are complete
- [ ] Docstrings are present for public APIs
- [ ] Tests are included
- [ ] No security vulnerabilities
- [ ] Performance is acceptable
- [ ] Error handling is appropriate

## Next Steps

- [Development Setup](development.md) - Get started
- [Testing Guide](TESTING.md) - Write tests
- [Contributing](contributing.md) - Contribute code
