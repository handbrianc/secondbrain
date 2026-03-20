"""
Async Ingestion Example.

This example demonstrates the asynchronous API for document ingestion
and search operations in SecondBrain.

Benefits of async API:
- Non-blocking I/O operations
- Better performance for I/O-bound workloads
- Efficient resource utilization
- Concurrent operations support
"""

import asyncio


async def basic_async_ingestion() -> None:
    """Perform basic async document ingestion."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Basic Async Ingestion")
    print("=" * 60)
    print()

    # Create async storage instance
    storage = AsyncDocumentStorage()

    # Ingest a single document asynchronously
    print("Ingesting document asynchronously...")
    await storage.ingest_document(
        doc_id="async-doc-1",
        content="This is an asynchronously ingested document.",
        metadata={
            "source": "async-example",
            "timestamp": "2024-01-01T00:00:00Z",
            "type": "example",
        },
    )
    print("✓ Document ingested successfully")
    print()


async def concurrent_async_ingestion() -> None:
    """Concurrent async document ingestion."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Concurrent Async Ingestion")
    print("=" * 60)
    print()

    storage = AsyncDocumentStorage()

    # Create multiple ingestion tasks
    tasks = []
    for i in range(5):
        task = storage.ingest_document(
            doc_id=f"async-doc-{i}",
            content=f"Document {i} content for concurrent ingestion demo.",
            metadata={"batch": "concurrent-demo", "index": i},
        )
        tasks.append(task)

    # Execute all tasks concurrently
    print("Ingesting 5 documents concurrently...")
    await asyncio.gather(*tasks)
    print("✓ All documents ingested concurrently")
    print()


async def async_search() -> None:
    """Async search operations."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Async Search")
    print("=" * 60)
    print()

    storage = AsyncDocumentStorage()

    # Generate a dummy embedding (in real usage, use embedding service)
    dummy_embedding = [0.1] * 768

    # Perform async search
    print("Performing async search...")
    results = await storage.search(query_embedding=dummy_embedding, top_k=5)

    print(f"✓ Found {len(results)} results")
    for i, result in enumerate(results[:3]):  # Show first 3
        print(f"  {i + 1}. {result}")
    print()


async def async_ingestion_with_embedding() -> None:
    """Async ingestion with embedding generation."""
    from secondbrain.embedding.async_embedding import AsyncEmbeddingGenerator
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Async Ingestion with Embedding Generation")
    print("=" * 60)
    print()

    # Create async embedding generator
    embedding_gen = AsyncEmbeddingGenerator()

    # Generate embedding asynchronously
    print("Generating embedding asynchronously...")
    embedding = await embedding_gen.generate_embedding("This is a test query")
    print(f"✓ Generated embedding with {len(embedding)} dimensions")

    # Store with embedding
    storage = AsyncDocumentStorage()
    await storage.ingest_document(
        doc_id="embedded-doc-1",
        content="Document with pre-computed embedding",
        metadata={"has_embedding": True},
    )
    print("✓ Document stored with embedding")
    print()


async def batch_async_operations() -> None:
    """Batch async operations."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Batch Async Operations")
    print("=" * 60)
    print()

    storage = AsyncDocumentStorage()

    # Batch ingestion with rate limiting
    documents = [
        {
            "doc_id": f"batch-doc-{i}",
            "content": f"Batch document {i} content",
            "metadata": {"batch": "async-batch", "index": i},
        }
        for i in range(10)
    ]

    print(f"Ingesting {len(documents)} documents in batches...")

    # Process in batches of 3
    batch_size = 3
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        tasks = [
            storage.ingest_document(doc["doc_id"], doc["content"], doc["metadata"])
            for doc in batch
        ]
        await asyncio.gather(*tasks)
        print(f"  ✓ Batch {i // batch_size + 1} completed")

    print("✓ All batches completed")
    print()


async def concurrent_search_and_ingestion() -> None:
    """Demonstrate concurrent search and ingestion."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    print("=" * 60)
    print("Concurrent Search and Ingestion")
    print("=" * 60)
    print()

    AsyncDocumentStorage()

    # Mix of search and ingestion operations
    async def search_operation(op_id: int) -> str:
        print(f"  Search {op_id} starting...")
        await asyncio.sleep(0.01)  # Simulate async work
        print(f"  ✓ Search {op_id} completed")
        return f"search-{op_id}"

    async def ingest_operation(op_id: int) -> str:
        print(f"  Ingest {op_id} starting...")
        await asyncio.sleep(0.01)  # Simulate async work
        print(f"  ✓ Ingest {op_id} completed")
        return f"ingest-{op_id}"

    # Mix operations
    operations = [
        search_operation(1),
        ingest_operation(1),
        search_operation(2),
        ingest_operation(2),
        search_operation(3),
    ]

    print("Executing mixed operations concurrently...")
    results = await asyncio.gather(*operations)
    print(f"✓ All {len(results)} operations completed")
    print()


async def error_handling() -> None:
    """Async error handling patterns."""
    from secondbrain.storage.async_storage import AsyncDocumentStorage

    from secondbrain.utils.circuit_breaker import CircuitBreakerError

    print("=" * 60)
    print("Async Error Handling")
    print("=" * 60)
    print()

    storage = AsyncDocumentStorage()

    # Pattern 1: Try-except with circuit breaker
    print("Pattern 1: Handling CircuitBreakerError")
    try:
        # Simulate circuit breaker being open
        if not storage._circuit_breaker.is_allowed():
            raise CircuitBreakerError("Service unavailable", "mongo")

        await storage.ingest_document("test", "content", {})
    except CircuitBreakerError as e:
        print(f"  ✓ Caught CircuitBreakerError: {e.message}")
        print("  Action: Use fallback or queue for retry")
    print()

    # Pattern 2: Retry with backoff
    print("Pattern 2: Retry with exponential backoff")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Simulate operation that might fail
            print(f"  Attempt {attempt + 1}/{max_retries}")
            # await storage.ingest_document(...)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  ✗ All retries failed: {e}")
            else:
                wait_time = 2**attempt
                print(f"  Retrying in {wait_time}s...")
                await asyncio.sleep(0.1)  # Short wait for demo
    print()


async def main() -> None:
    """Run all async examples."""
    print("\n" + "=" * 60)
    print("SecondBrain Async API Examples")
    print("=" * 60 + "\n")

    try:
        await basic_async_ingestion()
        await concurrent_async_ingestion()
        await async_search()
        await async_ingestion_with_embedding()
        await batch_async_operations()
        await concurrent_search_and_ingestion()
        await error_handling()

        print("=" * 60)
        print("Key Takeaways")
        print("=" * 60)
        print("""
1. Use asyncio.gather() for concurrent operations
2. Always await async methods
3. Handle CircuitBreakerError for resilience
4. Implement retry logic for transient failures
5. Use batch operations for better throughput

For more information, see:
- docs/developer-guide/async-api.md (complete async guide)
- tests/test_concurrency/ (concurrency tests)
- examples/circuit_breaker_usage.py (resilience patterns)
        """)

    except Exception as e:
        print(f"\nError: {e}")
        print("Note: Some examples require MongoDB and sentence-transformers services.")
        print("Start services with: docker-compose up -d")


if __name__ == "__main__":
    asyncio.run(main())
