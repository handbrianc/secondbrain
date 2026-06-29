# Integration Examples

Using SecondBrain programmatically via Python APIs with popular web frameworks.

## Flask Integration

### Setup

```bash
pip install flask secondbrain
```

### Basic Flask App

```python
"""Flask app exposing SecondBrain search via HTTP API."""

from flask import Flask, request, jsonify
from secondbrain.config import config
from secondbrain.document import DocumentIngestor
from secondbrain.search import Searcher
from secondbrain.embed.generator import EmbeddingGenerator
import tempfile
import os

app = Flask(__name__)

cfg = config()


@app.route("/ingest", methods=["POST"])
def ingest_document():
    """Upload and ingest a document.

    Expects multipart/form-data with file upload.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    # Save to temp file (DocumentIngestor works with paths)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        # Ingest the document
        ingestor = DocumentIngestor(
            chunk_size=cfg.chunk_size,
            chunk_overlap=cfg.chunk_overlap,
        )
        results = ingestor.ingest(tmp_path)

        return jsonify({
            "success": results["success"],
            "failed": results["failed"],
            "message": f"Ingested {results['success']} files"
        })
    finally:
        os.unlink(tmp_path)


@app.route("/search", methods=["GET"])
def search_documents():
    """Search ingested documents.

    Query params:
        q: Search query (required)
        top_k: Number of results (optional, default from config)
    """
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Missing query param 'q'"}), 400

    top_k = request.args.get("top_k", cfg.default_top_k, type=int)

    # Generate query embedding
    gen = EmbeddingGenerator()
    query_vec = gen.generate(query)
    gen.close()

    # Search
    with Searcher() as searcher:
        results = searcher.search(
            query=query,
            top_k=top_k,
        )

    return jsonify({
        "query": query,
        "count": len(results),
        "results": [
            {
                "score": r.get("score"),
                "source": r.get("source"),
                "page": r.get("page"),
                "text": r.get("text", "")[:200],
            }
            for r in results
        ]
    })


@app.route("/status", methods=["GET"])
def status():
    """Return database statistics."""
    from secondbrain.management import StatusChecker

    with StatusChecker() as checker:
        stats = checker.get_status()

    return jsonify(stats)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### Run the Flask App

```bash
export SECONDBRAIN_MONGO_URI="mongodb://localhost:27017"
export SECONDBRAIN_OPENAI_API_KEY="..."

python app.py
```

### Test the API

```bash
# Upload document
curl -F "file=@document.pdf" http://localhost:5000/ingest

# Search
curl "http://localhost:5000/search?q=machine%20learning&top_k=5"

# Status
curl http://localhost:5000/status
```

## FastAPI Integration

### Setup

```bash
pip install fastapi uvicorn secondbrain
```

### Basic FastAPI App

```python
"""FastAPI app with async SecondBrain integration."""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from secondbrain.config import config
from secondbrain.document import DocumentIngestor
from secondbrain.search import Searcher
from secondbrain.embed.generator import EmbeddingGenerator
import tempfile
import os

app = FastAPI(title="SecondBrain API")
cfg = config()


class SearchResult(BaseModel):
    score: float
    source: str
    page: int
    text: str


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchResult]


class IngestResponse(BaseModel):
    success: int
    failed: int
    message: str


@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(file: UploadFile = File(...)):
    """Upload and ingest a document (async)."""
    # Save uploaded file
    suffix = os.path.splitext(file.filename)[1] if file.filename else ".tmp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        ingestor = DocumentIngestor(
            chunk_size=cfg.chunk_size,
            chunk_overlap=cfg.chunk_overlap,
        )
        results = ingestor.ingest(tmp_path)
        return IngestResponse(
            success=results["success"],
            failed=results["failed"],
            message=f"Ingested {results['success']} files"
        )
    finally:
        os.unlink(tmp_path)


@app.get("/search", response_model=SearchResponse)
async def search_documents(
    q: str = Query(..., description="Search query"),
    top_k: Optional[int] = Query(None, description="Max results")
):
    """Search ingested documents."""
    if top_k is None:
        top_k = cfg.default_top_k

    # Generate embedding
    gen = EmbeddingGenerator()
    try:
        # Async embedding generation
        import asyncio
        query_vec = await asyncio.to_thread(gen.generate, q)
    finally:
        gen.close()

    # Execute search
    with Searcher() as searcher:
        hits = searcher.search(query=q, top_k=top_k)

    results = [
        SearchResult(
            score=r.get("score", 0.0),
            source=r.get("source", ""),
            page=r.get("page", 0),
            text=(r.get("text", "") or "")[:200],
        )
        for r in hits
    ]

    return SearchResponse(query=q, count=len(results), results=results)


@app.get("/health")
async def health_check():
    """Simple health check."""
    return {"status": "healthy"}
```

### Run the FastAPI App

```bash
export SECONDBRAIN_MONGO_URI="mongodb://localhost:27017"
export SECONDBRAIN_OPENAI_API_KEY="..."

uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### API Documentation

FastAPI automatically generates OpenAPI docs:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Test with curl

```bash
# Upload
curl -X POST "http://localhost:8000/ingest" \
  -F "file=@doc.pdf"

# Search
curl "http://localhost:8000/search?q=data%20science&top_k=3"

# Health
curl http://localhost:8000/health
```

## Programmatic Usage Pattern

Regardless of web framework, the core pattern is:

```python
from secondbrain.config import config
from secondbrain.document import DocumentIngestor
from secondbrain.search import Searcher
from secondbrain.embed.generator import EmbeddingGenerator
from secondbrain.management import StatusChecker, Lister

def setup_environment():
    """Initialize from environment or .env file."""
    return config()

def ingest_path(path: str, cfg) -> dict:
    """Ingest documents from path."""
    ingestor = DocumentIngestor(
        chunk_size=cfg.chunk_size,
        chunk_overlap=cfg.chunk_overlap,
    )
    return ingestor.ingest(path)

def search_query(query: str, cfg, top_k: int = None) -> list:
    """Search for query."""
    if top_k is None:
        top_k = cfg.default_top_k

    with Searcher() as searcher:
        return searcher.search(query=query, top_k=top_k)

def get_status() -> dict:
    """Get database statistics."""
    with StatusChecker() as checker:
        return checker.get_status()
```

## Error Handling

Wrap API calls in try/except blocks:

```python
from secondbrain.exceptions import (
    SecondBrainError,
    StorageConnectionError,
    ServiceUnavailableError,
    CLIValidationError,
)

@app.exception_handler(SecondBrainError)
async def handle_secondbrain_error(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "type": type(exc).__name__}
    )
```

## Async Considerations

SecondBrain's Motor-based async storage can improve throughput:

```python
from secondbrain.storage.async_client import AsyncStorageClient

async def async_search(query: str, top_k: int):
    """True async search operation."""
    async with AsyncStorageClient() as client:
        gen = EmbeddingGenerator()
        query_vec = await gen.generate_async(query)
        results = await client.search(query_vec, top_k=top_k)
        return results
```

## Deployment Notes

### Environment Variables

Ensure environment variables are set in production:

```bash
# Containerized deployment
SECONDBRAIN_MONGO_URI=mongodb://mongo:27017
SECONDBRAIN_OPENAI_API_KEY=${OPENAI_API_KEY}
SECONDBRAIN_LOG_LEVEL=INFO
```

### WSGI Servers

Production Flask (use Gunicorn):

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

Production FastAPI (use Uvicorn workers):

```bash
uvicorn app:app --workers 4 --host 0.0.0.0 --port 8000
```

### Health Endpoint

Always expose a health endpoint for container orchestration:

```python
@ app.get("/health")
def health():
    from secondbrain.logging import get_health_status
    return get_health_status()
```