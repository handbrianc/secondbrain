# Code Standards

Coding standards and conventions for SecondBrain development.

## Python Style Guide

### Imports

```python
# Standard library first
import os
import sys
from pathlib import Path

# Third-party
import click
import pymongo
from typing import List, Optional

# Local imports
from secondbrain.document import Document
from secondbrain.storage import MongoDBStorage
```

### Naming Conventions

```python
# Variables: snake_case
document_count = 0
user_name = "John"

# Functions: snake_case
def get_document_by_id(doc_id: str) -> Optional[Document]:
    ...

# Classes: PascalCase
class DocumentProcessor:
    ...

# Constants: UPPER_SNAKE_CASE
MAX_CHUNK_SIZE = 500
DEFAULT_TIMEOUT = 30

# Private: leading underscore
def _internal_helper():
    ...
```

### Function Design

```python
# Clear parameter names
def process_document(
    document: Document,
    chunk_size: int = 500,
    include_metadata: bool = True
) -> List[Chunk]:
    """Process document into chunks.
    
    Args:
        document: Document to process
        chunk_size: Target chunk size in tokens
        include_metadata: Include document metadata in chunks
    
    Returns:
        List of document chunks
    """
    ...
```

## Error Handling

### Specific Exceptions

```python
# Good
try:
    doc = storage.get_document(doc_id)
except DocumentNotFoundError:
    logger.warning(f"Document {doc_id} not found")
except StorageError as e:
    logger.error(f"Storage error: {e}")
    raise

# Avoid
try:
    doc = storage.get_document(doc_id)
except Exception:
    pass
```

### Custom Exceptions

```python
class SecondBrainError(Exception):
    """Base exception for SecondBrain."""
    pass

class DocumentNotFoundError(SecondBrainError):
    """Raised when document is not found."""
    pass

class StorageError(SecondBrainError):
    """Raised when storage operation fails."""
    pass
```

## Type Annotations

### Complete Type Hints

```python
from typing import List, Dict, Optional, Any, Union

def process_data(
    items: List[Dict[str, Any]],
    threshold: Optional[float] = None
) -> Dict[str, List[Any]]:
    ...
```

### Type Aliases

```python
# Complex types
UserDict = Dict[str, Dict[str, Any]]
DocumentList = List[Document]
Embedding = List[float]

# Use type aliases
def embed_documents(
    docs: DocumentList
) -> List[Embedding]:
    ...
```

## Async/Await

### Async Functions

```python
import asyncio
from motor.motor_asyncio import AsyncMongoCollection

async def fetch_documents(
    collection: AsyncMongoCollection,
    limit: int = 10
) -> List[Document]:
    """Fetch documents asynchronously."""
    cursor = collection.find().limit(limit)
    return await cursor.to_list(length=limit)
```

### Parallel Async Operations

```python
async def process_batch(documents: List[Document]) -> List[Result]:
    """Process documents in parallel."""
    tasks = [process_document(doc) for doc in documents]
    return await asyncio.gather(*tasks)
```

## Logging

### Log Levels

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")      # Detailed debugging
logger.info("Info message")         # General info
logger.warning("Warning message")   # Warning
logger.error("Error message")       # Error
logger.critical("Critical message") # Critical
```

### Contextual Logging

```python
# Good
logger.info(f"Processed document {doc_id} with {len(chunks)} chunks")

# Avoid
logger.info("Processed document")
```

## Performance

### Efficient Data Structures

```python
# Use set for membership testing
document_ids = set(doc.id for doc in documents)
if doc_id in document_ids:  # O(1) lookup
    ...

# Use generator for large datasets
def stream_documents():
    for doc in large_collection:
        yield doc
```

### Batch Operations

```python
# Good: Batch insert
collection.insert_many(documents, ordered=False)

# Avoid: Individual inserts
for doc in documents:
    collection.insert_one(doc)
```

## Testing

### Test Organization

```python
import pytest
from secondbrain.document import Document

class TestDocument:
    """Test Document class."""
    
    def test_creation(self):
        """Test document creation."""
        doc = Document(id="1", title="Test", content="Content")
        assert doc.id == "1"
    
    def test_metadata(self):
        """Test metadata handling."""
        doc = Document(
            id="1",
            title="Test",
            content="Content",
            metadata={"author": "John"}
        )
        assert doc.metadata["author"] == "John"
```

## Documentation

### Docstrings

```python
def search(
    query: str,
    limit: int = 10
) -> List[Document]:
    """Search documents by semantic similarity.
    
    Args:
        query: Search query text
        limit: Maximum number of results
    
    Returns:
        List of matching documents sorted by similarity
    
    Raises:
        ValueError: If query is empty
        SearchError: If search fails
    """
    ...
```

## Security

### Input Validation

```python
from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
```

### No Hardcoded Secrets

```python
# Good
from dotenv import load_dotenv
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")

# Avoid
MONGODB_URI = "mongodb://user:password@localhost:27017"
```

## See Also

- [Development Setup](development.md)
- [Contributing Guide](contributing.md)
- [Testing Guide](TESTING.md)
