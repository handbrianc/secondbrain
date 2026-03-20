# Async API Guide

Asynchronous programming with SecondBrain.

## Overview

SecondBrain provides a fully asynchronous API for high-throughput scenarios.

## Async Client

### Basic Usage

```python
import asyncio
from secondbrain.client import SecondBrainClient

async def main():
    client = SecondBrainClient()
    
    # Ingest documents
    await client.ingest("./documents/")
    
    # Search
    results = await client.search("semantic query")
    for result in results:
        print(result)
    
    # Close client
    await client.close()

asyncio.run(main())
```

## Async Storage

### Document Storage

```python
from secondbrain.storage.async_storage import AsyncDocumentStorage

async def ingest_document():
    storage = AsyncDocumentStorage()
    
    await storage.ingest_document(
        doc_id="doc-1",
        content="Document content",
        metadata={"source": "test"}
    )
```

### Async Search

```python
async def search_documents():
    storage = AsyncDocumentStorage()
    
    results = await storage.search(
        query_embedding=[0.1] * 384,
        top_k=10
    )
    
    for result in results:
        print(result)
```

## Batch Processing

### Async Batch Ingestion

```python
async def batch_ingest(documents):
    storage = AsyncDocumentStorage()
    
    # Process in parallel
    tasks = [
        storage.ingest_document(
            doc_id=doc["id"],
            content=doc["content"]
        )
        for doc in documents
    ]
    
    await asyncio.gather(*tasks)
```

## Performance Benefits

### Concurrent Operations

```python
# Sequential (slow)
for doc in documents:
    await storage.ingest_document(doc)

# Concurrent (fast)
await asyncio.gather(*[
    storage.ingest_document(doc)
    for doc in documents
])
```

### Connection Pooling

```python
# Async client with connection pooling
client = SecondBrainClient(
    max_connections=50,
    connection_timeout=30
)
```

## Error Handling

```python
import asyncio
from secondbrain.exceptions import ConnectionError

async def safe_ingest():
    try:
        await client.ingest("./docs/")
    except ConnectionError as e:
        print(f"Connection failed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
```

## Integration Examples

### Flask Integration

```python
from flask import Flask, request, jsonify
import asyncio

app = Flask(__name__)

@app.route("/ingest", methods=["POST"])
async def ingest():
    data = await request.json
    await client.ingest(data["path"])
    return jsonify({"status": "success"})
```

### FastAPI Integration

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class IngestRequest(BaseModel):
    path: str

@app.post("/ingest")
async def ingest(request: IngestRequest):
    await client.ingest(request.path)
    return {"status": "success"}
```

## Best Practices

1. **Always use async** for I/O operations
2. **Use asyncio.gather()** for concurrent operations
3. **Close clients** properly with `await client.close()`
4. **Handle errors** gracefully
5. **Use connection pooling** for high throughput

## Next Steps

- [Async Storage](../api/index.md) - API documentation
- [Examples](../examples/README.md) - Code examples
