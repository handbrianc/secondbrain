#!/usr/bin/env python3
"""FastAPI async integration example.

Provides an async REST API with Pydantic models.

Run:
    uvicorn fastapi_endpoint:app --reload --port 8000
"""

import argparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from secondbrain.document import DocumentIngestor
from secondbrain.logging import setup_logging
from secondbrain.search import Searcher
from secondbrain.storage import VectorStorage

setup_logging(verbose=False)

app = FastAPI(title="SecondBrain API", version="1.0.0")


class IngestRequest(BaseModel):
    path: str
    recursive: bool = True
    batch_size: int = 5


class IngestResponse(BaseModel):
    status: str
    files_processed: int
    successful: int
    chunks_created: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filter_source: str | None = None
    filter_type: str | None = None


class SearchResult(BaseModel):
    score: float
    source: str
    page: int | None
    text: str


class SearchResponse(BaseModel):
    status: str
    query: str
    results: list[SearchResult]


class DocumentList(BaseModel):
    source: str
    page: int | None
    size: int


class DocumentsResponse(BaseModel):
    status: str
    total: int
    documents: list[DocumentList]


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "service": "secondbrain"}


@app.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """Ingest documents from a directory."""
    try:
        ingestor = DocumentIngestor()
        results = ingestor.ingest_directory(
            request.path, recursive=request.recursive, batch_size=request.batch_size
        )

        success = sum(1 for r in results if not r.error)
        chunks = sum(r.created_chunks for r in results)

        return IngestResponse(
            status="success",
            files_processed=len(results),
            successful=success,
            chunks_created=chunks,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Search documents semantically."""
    try:
        searcher = Searcher()
        results = searcher.search(
            query=request.query,
            top_k=request.top_k,
            source_filter=request.filter_source,
            file_type_filter=request.filter_type,
        )

        return SearchResponse(
            status="success",
            query=request.query,
            results=[
                SearchResult(
                    score=r.score,
                    source=r.source_file,
                    page=r.page_number,
                    text=r.chunk_text[:200],
                )
                for r in results
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/documents", response_model=DocumentsResponse)
async def list_documents(limit: int = 10, offset: int = 0):
    """List ingested documents."""
    try:
        storage = VectorStorage()
        chunks = storage.list_chunks(limit=limit, offset=offset)

        return DocumentsResponse(
            status="success",
            total=len(chunks),
            documents=[
                DocumentList(
                    source=c.source_file, page=c.page_number, size=len(c.chunk_text)
                )
                for c in chunks
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
