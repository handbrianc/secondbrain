# Document

Document parsing, chunking, and ingestion. The `DocumentIngestor` (sync) and
`AsyncDocumentIngestor` pipelines extract text via Docling, split it into
chunks, and hand them to the embedding + storage layers.

::: secondbrain.document
