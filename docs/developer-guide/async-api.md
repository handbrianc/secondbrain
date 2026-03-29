# Async API Guide

Complete guide to SecondBrain's asynchronous API.

## Overview

SecondBrain provides full async/await support for high-performance applications.

## Async Components

### Async Storage

```python
import asyncio
from secondbrain.storage import MongoDBStorage

async def main():
    storage = MongoDBStorage(
        uri="mongodb://localhost:27017",
        database="secondbrain"
    )
    
    await storage.initialize()
    
    # Async operations
    doc_id = await storage.store_document(doc)
    doc = await storage.get_document(doc_id)
    results = await storage.search("query", limit=10)
    
    await storage.cleanup()

asyncio.run(main())
```

### Async Ingestor

```python
from secondbrain.ingestor import AsyncDocumentIngestor

async def ingest_documents():
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    ingestor = AsyncDocumentIngestor(storage=storage)
    
    # Ingest single file
    doc_ids = await ingestor.ingest_file("document.pdf")
    
    # Ingest directory
    doc_ids = await ingestor.ingest_directory("documents/", recursive=True)
    
    # Batch ingest
    doc_ids = await ingestor.ingest_batch(["doc1.pdf", "doc2.pdf"])
```

### Parallel Processing

```python
async def process_multiple_queries(queries: List[str]):
    """Process multiple queries in parallel."""
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    
    # Create tasks
    tasks = [
        storage.search(query, limit=10)
        for query in queries
    ]
    
    # Execute in parallel
    results = await asyncio.gather(*tasks)
    
    return results
```

## Performance Benefits

### Concurrent Operations

```python
# Sequential (slow)
async def sequential_search(queries):
    results = []
    for query in queries:
        result = await storage.search(query)
        results.append(result)
    return results

# Parallel (fast)
async def parallel_search(queries):
    tasks = [storage.search(query) for query in queries]
    return await asyncio.gather(*tasks)
```

### Connection Pooling

```python
from motor.motor_asyncio import AsyncMongoClient

client = AsyncMongoClient(
    "mongodb://localhost:27017",
    maxPoolSize=50,      # Max connections
    minPoolSize=10,      # Min connections
    maxIdleTimeMS=300000 # Close idle after 5min
)
```

## Best Practices

### Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_storage():
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    await storage.initialize()
    try:
        yield storage
    finally:
        await storage.cleanup()

async def main():
    async with get_storage() as storage:
        results = await storage.search("query")
```

### Error Handling

```python
import asyncio
from secondbrain.exceptions import StorageError

async def safe_search(storage, query):
    try:
        results = await storage.search(query, limit=10)
        return results
    except StorageError as e:
        logger.error(f"Search failed: {e}")
        return []
    except asyncio.TimeoutError:
        logger.warning("Search timed out")
        return []
```

### Timeouts

```python
async def search_with_timeout(storage, query, timeout=30):
    try:
        return await asyncio.wait_for(
            storage.search(query, limit=10),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        raise SearchTimeoutError("Search timed out after {}s".format(timeout))
```

## Concurrency Patterns

### Worker Pool

```python
async def worker(queue, storage, results):
    """Worker that processes queue items."""
    while True:
        try:
            query = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            break
        
        result = await storage.search(query)
        results.append(result)
        queue.task_done()

async def process_with_workers(queries, num_workers=4):
    queue = asyncio.Queue()
    results = []
    
    # Fill queue
    for query in queries:
        await queue.put(query)
    
    # Create workers
    workers = [
        asyncio.create_task(worker(queue, storage, results))
        for _ in range(num_workers)
    ]
    
    # Wait for completion
    await asyncio.gather(*workers)
    return results
```

### Rate Limiting

```python
from aiolimiter import AsyncLimiter

async def rate_limited_search(storage, queries, rate=10):
    """Search with rate limiting."""
    limiter = AsyncLimiter(rate, 1)  # rate per second
    
    async def search_with_limit(query):
        async with limiter:
            return await storage.search(query)
    
    tasks = [search_with_limit(q) for q in queries]
    return await asyncio.gather(*tasks)
```

## Migration from Sync

### Sync to Async

```python
# Before (sync)
def search_documents(query):
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    return storage.search(query)

# After (async)
async def search_documents(query):
    storage = MongoDBStorage(uri="mongodb://localhost:27017")
    await storage.initialize()
    try:
        return await storage.search(query)
    finally:
        await storage.cleanup()
```

## See Also

- [API Reference](../api/index.md)
- [Data Flow](../architecture/DATA_FLOW.md)
- [Testing](TESTING.md)
