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
        print(f"Ollama available: {is_available}")
        
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
from secondbrain.exceptions import OllamaUnavailableError

async def ensure_model():
    generator = EmbeddingGenerator(model="embeddinggemma:latest")
    
    try:
        # Check if model is available
        if not await generator.validate_connection_async():
            print("Ollama not available")
            return
        
        # Pull model if needed
        await generator.pull_model_async()
        print("Model ready")
        
    except OllamaUnavailableError as e:
        print(f"Ollama unavailable: {e}")
    finally:
        await generator.aclose()
```

## Async Storage Operations

### Basic Storage

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
    OllamaUnavailableError,
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
            except (OllamaUnavailableError, asyncio.TimeoutError) as e:
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
