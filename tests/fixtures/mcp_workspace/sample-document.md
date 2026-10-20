# Sample Document

Secondbrain is a local document intelligence CLI for semantic search.

## Vector search

Secondbrain stores document chunks as embedding vectors in Qdrant and ranks
them by cosine similarity at query time.

## Ingestion

Ingestion splits a document into chunks, embeds each chunk with the
configured embedding model, and upserts the vectors into the configured
collection.

---

This file is a deterministic fixture for MCP ingest and search assertions:
its content is committed, stable, and intentionally tiny. Extend this
directory only with equally stable content — the test stack mounts it
read-only.
