# Examples

Code examples and tutorials for SecondBrain.

## Quick Examples

### Basic Usage

```python
from secondbrain import SecondBrain

# Initialize
sb = SecondBrain()

# Ingest document
sb.ingest("document.pdf")

# Search
results = sb.search("machine learning")

for doc in results:
    print(doc.title, doc.score)
```

### Async Usage

```python
import asyncio
from secondbrain import AsyncSecondBrain

async def main():
    sb = AsyncSecondBrain()
    
    # Batch ingest
    await sb.ingest_batch(["doc1.pdf", "doc2.pdf"])
    
    # Parallel search
    results = await asyncio.gather(
        sb.search("query 1"),
        sb.search("query 2")
    )

asyncio.run(main())
```

## Example Categories

### Basic Usage
- [Ingest Documents](basic_usage/ingest_documents.py)
- [Semantic Search](basic_usage/semantic_search.py)
- [List Documents](basic_usage/list_documents.py)

### Advanced
- [Custom Chunking](advanced/custom_chunking.py)
- [Batch Ingestion](advanced/batch_ingestion.py)
- [Async Workflow](advanced/async_workflow.py)

### Integrations
- [FastAPI Endpoint](integrations/fastapi_endpoint.py)
- [Flask API](integrations/flask_api.py)

### Scripts
- [Export to JSON](scripts/export_to_json.py)
- [Ingest Directory](scripts/ingest_entire_directory.sh)

## Tutorials

### Getting Started Tutorial

1. Install SecondBrain
2. Configure MongoDB
3. Ingest your first document
4. Perform semantic search
5. Explore results

### Advanced Tutorial

1. Custom embedding models
2. Batch processing
3. Performance optimization
4. Integration with LLMs

## See Also

- [User Guide](../user-guide/index.md)
- [Getting Started](../getting-started/index.md)
- [API Reference](../api/index.md)
