# Async Support Guide

SecondBrain provides full asynchronous support for embedding generation and storage operations.

## Overview

All major operations support both synchronous and asynchronous APIs:

- **Embedding Generation**: Async embedding generation with rate limiting
- **Storage**: Async MongoDB operations with connection pooling
- **Search**: Async search with concurrent query processing
- **CLI**: All CLI commands use async internally

## Async Embedding Generation

### Basic Usage

```python
import asyncio
from secondbrain.embedding import EmbeddingGenerator

async def generate_embeddings():
    # Create generator
    generator = EmbeddingGenerator()
    
    try:
        # Generate single embedding
        embedding = await generator.generate_async("Hello, world!")
        print(f"Embedding dimensions: {len(embedding)}")
        
        # Generate batch of embeddings
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = await generator.generate_batch_async(texts)
        print(f"Generated {len(embeddings)} embeddings")
        
    finally:
        # Always close to release resources
        await generator.aclose()

# Run the async function
asyncio.run(generate_embeddings())
```

### Connection Validation

```python
from secondbrain.embedding import EmbeddingGenerator

async def check_availability():
    generator = EmbeddingGenerator()
    
    try:
        # Force fresh check (bypass cache)
        is_available = await generator.validate_connection_async(force=True)
        print(f"sentence-transformers available: {is_available}")
        
        # Get model info
        model_info = await generator.get_model_info_async()
        if model_info:
            print(f"Model: {model_info['name']}")
            print(f"Dimensions: {model_info['embedding_dimensions']}")
    finally:
        await generator.aclose()
```

### Pulling Models Async

```python
from secondbrain.embedding import EmbeddingGenerator
from secondbrain.exceptions import sentence-transformersUnavailableError

async def ensure_model():
    generator = EmbeddingGenerator(model="embeddinggemma:latest")
    
    try:
        # Check if model is available
        if not await generator.validate_connection_async():
            print("sentence-transformers not available")
            return
        
        # Pull model if needed
        await generator.pull_model_async()
        print("Model ready")
        
    except sentence-transformersUnavailableError as e:
        print(f"sentence-transformers unavailable: {e}")
    finally:
        await generator.aclose()
```

## Async Storage Operations

### Basic Storage with VectorStorage (to_thread wrapper)

```python
import asyncio
from secondbrain.storage import VectorStorage

async def store_documents():
    storage = VectorStorage()
    
    try:
        # Wait for connection
        if not await storage.validate_connection_async():
            print("MongoDB not available")
            return
        
        # Store single document
        doc = {
            "chunk_id": "uuid-123",
            "source_file": "document.pdf",
            "page_number": 1,
            "chunk_text": "Sample text",
            "embedding": [0.1, 0.2, 0.3, ...],  # 768 dimensions
            "metadata": {
                "file_type": "pdf",
                "chunk_index": 0
            }
        }
        
        doc_id = await storage.store_async(doc)
        print(f"Stored document: {doc_id}")
        
        # Store batch
        docs = [doc, doc, doc]  # Multiple documents
        count = await storage.store_batch_async(docs)
        print(f"Stored {count} documents")
        
    finally:
        await storage.aclose()

asyncio.run(store_documents())
```

### Native Async Storage with Motor (AsyncVectorStorage)

For better performance with concurrent operations, use `AsyncVectorStorage` which uses Motor, the official async MongoDB driver:

```python
import asyncio
from secondbrain.storage.storage import AsyncVectorStorage

async def store_documents_motor():
    """Store documents using native Motor async operations."""
    storage = AsyncVectorStorage()
    
    try:
        # Validate connection
        if not await storage.validate_connection_async():
            print("MongoDB not available")
            return
        
        # Store single document - native async, no to_thread wrapper
        doc = {
            "chunk_id": "uuid-123",
            "source_file": "document.pdf",
            "page_number": 1,
            "chunk_text": "Sample text",
            "embedding": [0.1, 0.2, 0.3, ...],  # 768 dimensions
        }
        
        doc_id = await storage.store_async(doc)
        print(f"Stored document: {doc_id}")
        
        # Store batch - all operations are native async
        docs = [doc.copy() for _ in range(10)]
        count = await storage.store_batch_async(docs)
        print(f"Stored {count} documents")
        
        # Search with native async
        results = await storage.search_async(
            embedding=[0.1] * 768,
            top_k=5
        )
        print(f"Found {len(results)} results")
        
        # List chunks
        chunks = await storage.list_chunks_async(limit=10)
        print(f"Found {len(chunks)} chunks")
        
        # Delete operations
        deleted = await storage.delete_by_source_async("document.pdf")
        print(f"Deleted {deleted} documents")
        
        # Get stats
        stats = await storage.get_stats_async()
        print(f"Total chunks: {stats['total_chunks']}")
        
    finally:
        await storage.aclose()

asyncio.run(store_documents_motor())
```

### Async Context Manager with Motor

```python
import asyncio
from secondbrain.storage.storage import AsyncVectorStorage

async def with_context_manager():
    # Async context manager for automatic cleanup
    async with AsyncVectorStorage() as storage:
        # All operations within this block
        docs = await storage.list_chunks_async(limit=10)
        print(f"Found {len(docs)} chunks")
        
        # Store and search
        doc = {
            "chunk_id": "test-123",
            "embedding": [0.1] * 768,
            "chunk_text": "Test content"
        }
        await storage.store_async(doc)
        
        results = await storage.search_async(embedding=[0.1] * 768)
        print(f"Search returned {len(results)} results")
    # Automatically closed
```

### Async Search

```python
import asyncio
from secondbrain.storage import VectorStorage

async def search_documents(embedding):
    storage = VectorStorage()
    
    try:
        # Search with filters
        results = await storage.search_async(
            embedding=embedding,
            top_k=10,
            source_filter="document.pdf",
            file_type_filter="pdf"
        )
        
        for result in results:
            print(f"Score: {result['score']:.4f}")
            print(f"Text: {result['chunk_text'][:100]}...")
            
    finally:
        await storage.aclose()
```

### Async Operations with Context Manager

```python
import asyncio
from secondbrain.storage import VectorStorage

async def with_context_manager():
    async with VectorStorage() as storage:
        # All operations within this block
        docs = await storage.list_chunks_async(limit=10)
        print(f"Found {len(docs)} chunks")
    # Automatically closed
```

## Async Searcher

### Basic Search

```python
import asyncio
from secondbrain.search import Searcher

async def semantic_search():
    async with Searcher() as searcher:
        # Generate embedding and search in one call
        results = await searcher.search_async(
            query="What is machine learning?",
            top_k=5
        )
        
        for i, result in enumerate(results, 1):
            print(f"{i}. Score: {result['score']:.4f}")
            print(f"   {result['chunk_text'][:150]}...")
```

### Concurrent Searches

```python
import asyncio
from secondbrain.search import Searcher

async def concurrent_searches():
    queries = [
        "machine learning basics",
        "deep learning applications",
        "neural networks explained"
    ]
    
    async with Searcher() as searcher:
        # Run searches concurrently
        tasks = [
            searcher.search_async(query, top_k=3)
            for query in queries
        ]
        results = await asyncio.gather(*tasks)
        
        for query, query_results in zip(queries, results):
            print(f"\nQuery: {query}")
            for result in query_results:
                print(f"  - {result['chunk_text'][:80]}...")
```

## Async Document Ingestion

### Processing Files Async

```python
import asyncio
from pathlib import Path
from secondbrain.document import DocumentIngestor

async def ingest_documents():
    ingestor = DocumentIngestor(chunk_size=2048, chunk_overlap=100)
    
    # Process files concurrently
    files = [
        Path("doc1.pdf"),
        Path("doc2.pdf"),
        Path("doc3.pdf")
    ]
    
    async def process_file(file_path):
        # Note: ingest() is sync, use asyncio.to_thread for CPU-bound work
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: ingestor.ingest(str(file_path), recursive=False, batch_size=1)
        )
        return file_path, result
    
    # Process all files concurrently
    tasks = [process_file(f) for f in files]
    results = await asyncio.gather(*tasks)
    
    for file_path, result in results:
        print(f"{file_path}: {result['success']} successful, {result['failed']} failed")
```

## Performance Comparison: Motor vs to_thread

### When to Use Each

**AsyncVectorStorage (Motor)** - Use for:
- High-concurrency workloads (many simultaneous operations)
- Production deployments with multiple concurrent users
- Operations that need true non-blocking I/O
- Better performance under load

**VectorStorage with async methods (to_thread)** - Use for:
- Simple async integration without adding Motor dependency
- Lower concurrency requirements
- Backward compatibility with existing sync code
- Simpler testing setup

### Performance Benefits

Motor provides better performance for concurrent operations because:

1. **No thread blocking**: Native async/await vs. thread pool
2. **Better connection pooling**: Motor's async connection pool
3. **Lower overhead**: No context switching between threads
4. **True concurrency**: Multiple operations can run simultaneously

```python
import asyncio
import time
from secondbrain.storage import VectorStorage
from secondbrain.storage.storage import AsyncVectorStorage

async def benchmark_storage():
    """Compare performance of to_thread vs Motor."""
    
    # Simulate concurrent document storage
    docs = [
        {
            "chunk_id": f"chunk-{i}",
            "embedding": [0.1] * 768,
            "chunk_text": f"Document {i}"
        }
        for i in range(100)
    ]
    
    # Benchmark to_thread version
    storage_sync = VectorStorage()
    start = time.time()
    
    tasks = [storage_sync.store_async(doc) for doc in docs[:10]]
    await asyncio.gather(*tasks)
    
    to_thread_time = time.time() - start
    await storage_sync.aclose()
    
    # Benchmark Motor version
    storage_motor = AsyncVectorStorage()
    start = time.time()
    
    tasks = [storage_motor.store_async(doc) for doc in docs[:10]]
    await asyncio.gather(*tasks)
    
    motor_time = time.time() - start
    await storage_motor.aclose()
    
    print(f"to_thread version: {to_thread_time:.3f}s")
    print(f"Motor version: {motor_time:.3f}s")
    print(f"Speedup: {to_thread_time / motor_time:.2f}x")

asyncio.run(benchmark_storage())
```

## Best Practices

### Resource Management

Always close resources properly:

```python
# ✅ Good: Use async context manager
async with EmbeddingGenerator() as gen:
    embedding = await gen.generate_async("text")

# ✅ Good: Explicit close in finally block
gen = EmbeddingGenerator()
try:
    embedding = await gen.generate_async("text")
finally:
    await gen.aclose()

# ❌ Bad: Never close resources
gen = EmbeddingGenerator()
embedding = await gen.generate_async("text")  # Resource leak!
```

### Error Handling

Handle async-specific errors:

```python
from secondbrain.exceptions import (
    sentence-transformersUnavailableError,
    EmbeddingGenerationError,
    StorageConnectionError
)
import asyncio

async def robust_embedding(text):
    generator = EmbeddingGenerator()
    
    try:
        # Retry logic for transient failures
        for attempt in range(3):
            try:
                return await generator.generate_async(text)
            except (sentence-transformersUnavailableError, asyncio.TimeoutError) as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
    finally:
        await generator.aclose()
```

### Batch Operations

Use batch operations for efficiency:

```python
async def efficient_batch(texts):
    generator = EmbeddingGenerator()
    
    try:
        # Single batch call (more efficient than individual calls)
        embeddings = await generator.generate_batch_async(texts)
        return embeddings
        
    finally:
        await generator.aclose()

# For very large batches, process in chunks
async def large_batch(texts, chunk_size=100):
    all_embeddings = []
    
    for i in range(0, len(texts), chunk_size):
        chunk = texts[i:i + chunk_size]
        embeddings = await efficient_batch(chunk)
        all_embeddings.extend(embeddings)
    
    return all_embeddings
```

### Connection Pooling

MongoDB connection pooling is automatic:

```python
# Connection pool is shared across async operations
storage1 = VectorStorage()
storage2 = VectorStorage()

# Both use the same connection pool
# No need to manually manage connections
```

## Performance Tips

### Parallel Embeddings

```python
async def parallel_embeddings(texts):
    """Generate embeddings in parallel using rate limiting."""
    generator = EmbeddingGenerator()
    
    try:
        # Rate limiter handles concurrency automatically
        tasks = [generator.generate_async(text) for text in texts]
        return await asyncio.gather(*tasks)
        
    finally:
        await generator.aclose()
```

### Streaming Large Datasets

```python
async def stream_search_results(query, batch_size=100):
    """Stream search results in batches."""
    storage = VectorStorage()
    offset = 0
    
    try:
        while True:
            results = await storage.list_chunks_async(
                limit=batch_size,
                offset=offset
            )
            
            if not results:
                break
                
            for result in results:
                yield result
                
            offset += batch_size
            
    finally:
        await storage.aclose()

# Usage
async def process_results():
    async for result in stream_search_results("query"):
        # Process each result as it arrives
        await process_async(result)
```

## Migration from Sync to Async

### Before (Sync)

```python
from secondbrain.embedding import EmbeddingGenerator

gen = EmbeddingGenerator()
embedding = gen.generate("text")
gen.close()
```

### After (Async)

```python
from secondbrain.embedding import EmbeddingGenerator

async with EmbeddingGenerator() as gen:
    embedding = await gen.generate_async("text")
```

### CLI Integration

CLI commands automatically use async internally:

```bash
# No changes needed - async is handled internally
secondbrain search "query" --verbose
```

## Next Steps

- [Development Guide](./development.md) - Full development workflow
- [Performance Optimization](./development.md#performance-optimization) - Tuning async operations
- [Testing Async Code](./development.md#testing) - Async test patterns

## Related Documentation

- [Development Guide](./development.md) - Full development workflow
- [Performance Optimization](./development.md#performance-optimization) - Tuning async operations
