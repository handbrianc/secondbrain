# Async API Guide

Patterns and usage for SecondBrain's asynchronous programming interfaces.

## Overview

SecondBrain uses Python's `asyncio` for concurrent operations throughout the stack:

- MongoDB access via Motor (async driver)
- HTTP clients via httpx (async)
- Embedding generation with async batching
- RAG pipeline with async LLM calls

## Async Storage Operations

### Async Search

```python
from secondbrain.storage.async_client import AsyncStorageClient

async with AsyncStorageClient() as client:
    results = await client.search(
        query_vector=embedding,
        top_k=20,
        filter={"source": {"$regex": "^./docs/"}}
    )
```

### Async Batch Store

```python
async with AsyncStorageClient() as client:
    await client.store_batch(chunks=[chunk1, chunk2, chunk3])
```

### Async Document Operations

```python
from secondbrain.storage.async_client import AsyncStorageClient

client = AsyncStorageClient()

# Search
results = await client.search(query_vector=embedding, top_k=10)

# Store
await client.store(chunk_data)

# Delete
deleted = await client.delete(filter={"source": "./old.pdf"})

# Stats
stats = await client.get_stats()

await client.close()
```

## Async Embedding Generation

### Direct Async Call

```python
from secondbrain.embed.generator import EmbeddingGenerator

generator = EmbeddingGenerator()

# Generate single embedding
embedding = await generator.generate_async("Your text here")

# Generate batch
embeddings = await generator.generate_batch_async([
    "First text",
    "Second text",
    "Third text"
])

generator.close()
```

### Generator Pattern

Embedding generators support async iteration:

```python
gen = EmbeddingGenerator()

async for embedding in gen.generate_stream(texts):
    print(f"Got embedding: {len(embedding)} dims")

gen.close()
```

## Async Client Factory

The recommended async client initialization:

```python
from secondbrain.clients import get_async_storage, get_async_embedder

async with get_async_storage() as storage:
    results = await storage.search(query, top_k=20)

async with get_async_embedder() as embedder:
    emb = await embedder.generate_async("text")
```

## RAG Pipeline Async Usage

Full RAG pipeline with async operations:

```python
from secondbrain.rag.pipeline import RAGPipeline

pipeline = RAGPipeline(
    searcher=search_client,
    llm_provider=llm_factory.create_provider(),
    top_k=10
)

async def ask_question(question: str, session: Session):
    async for chunk in pipelineachat_stream(question, session):
        yield chunk

# Stream responses
async for delta in ask_question("What is RAG?", session):
    print(delta, end="", flush=True)
```

## Concurrent Operations

### gather for Parallel Execution

Run multiple coroutines concurrently:

```python
import asyncio
from secondbrain.embed.generator import EmbeddingGenerator

async def process_batch(batch: list[str]) -> list[list[float]]:
    gen = EmbeddingGenerator()
    results = await gen.generate_batch_async(batch)
    gen.close()
    return results

async def main():
    all_texts = [...]  # Your documents
    
    # Process in parallel batches
    tasks = [
        process_batch(all_texts[i:i+100])
        for i in range(0, len(all_texts), 100)
    ]
    
    all_embeddings = await asyncio.gather(*tasks)
    flat_embeddings = [emb for batch in all_embeddings for emb in batch]

asyncio.run(main())
```

### Semaphore for Concurrency Limiting

Prevent overwhelming external services:

```python
semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests

async def limited_call(url: str):
    async with semaphore:
        async with httpx.AsyncClient() as client:
            return await client.get(url)
```

## Error Handling

### Async Try/Except

```python
async def safe_search(query: str):
    try:
        result = await search_client.search(query)
        return result
    except asyncio.TimeoutError:
        logger.error("Search timed out")
        return []
    except Exception as e:
        logger.exception("Search failed")
        raise
```

### Retry with Exponential Backoff

```python
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def resilient_call():
    return await maybe_failing_operation()
```

## Context Managers

Use context managers for proper cleanup:

```python
# Preferred
async with AsyncStorageClient() as client:
    await client.search(...)

# Manual close required otherwise
client = AsyncStorageClient()
try:
    await client.search(...)
finally:
    await client.close()
```

## Performance Considerations

### Connection Pooling

Async clients maintain connection pools internally. Reuse clients across operations:

```python
# Good: reuse client
client = AsyncStorageClient()
for query in queries:
    results = await client.search(query)

# Bad: new client per request
for query in queries:
    async with AsyncStorageClient() as client:
        results = await client.search(query)
```

### Batching Efficiency

Batch operations reduce round trips:

```python
# Better: single batch call
embeddings = await gen.generate_batch_async(texts)

# Worse: individual calls
embeddings = [await gen.generate_async(t) for t in texts]
```

### Streaming vs Collecting

Choose streaming for memory efficiency with large datasets:

```python
# Memory efficient
async for embedding in gen.generate_stream(large_dataset):
    await store_single(embedding)

# Memory heavy - loads all at once
all_embeddings = await gen.generate_batch_async(large_dataset)
```