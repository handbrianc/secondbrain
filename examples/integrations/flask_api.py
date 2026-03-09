#!/usr/bin/env python3
"""Flask REST API integration example.

Provides a REST API wrapper around SecondBrain functionality.

Run:
    python flask_api.py --port 8000
"""

import argparse

from flask import Flask, jsonify, request

from secondbrain.document import DocumentIngestor
from secondbrain.logging import setup_logging
from secondbrain.search import Searcher
from secondbrain.storage import VectorStorage

app = Flask(__name__)
setup_logging(verbose=False)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "secondbrain"})


@app.route("/ingest", methods=["POST"])
def ingest():
    """Ingest documents from a directory."""
    data = request.get_json()
    path = data.get("path")

    if not path:
        return jsonify({"error": "path required"}), 400

    try:
        ingestor = DocumentIngestor()
        results = ingestor.ingest_directory(path, recursive=True, batch_size=5)

        success = sum(1 for r in results if not r.error)
        chunks = sum(r.created_chunks for r in results)

        return jsonify(
            {
                "status": "success",
                "files_processed": len(results),
                "successful": success,
                "chunks_created": chunks,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/search", methods=["POST"])
def search():
    """Search documents semantically."""
    data = request.get_json()
    query = data.get("query")
    top_k = data.get("top_k", 5)

    if not query:
        return jsonify({"error": "query required"}), 400

    try:
        searcher = Searcher()
        results = searcher.search(query, top_k=top_k)

        return jsonify(
            {
                "status": "success",
                "query": query,
                "results": [
                    {
                        "score": r.score,
                        "source": r.source_file,
                        "page": r.page_number,
                        "text": r.chunk_text[:200],
                    }
                    for r in results
                ],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/documents", methods=["GET"])
def list_documents():
    """List ingested documents."""
    limit = request.args.get("limit", 10, type=int)
    offset = request.args.get("offset", 0, type=int)

    try:
        storage = VectorStorage()
        chunks = storage.list_chunks(limit=limit, offset=offset)

        return jsonify(
            {
                "status": "success",
                "total": len(chunks),
                "documents": [
                    {
                        "source": c.source_file,
                        "page": c.page_number,
                        "size": len(c.chunk_text),
                    }
                    for c in chunks
                ],
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=True)


if __name__ == "__main__":
    main()
