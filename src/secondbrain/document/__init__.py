from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from docling.document_converter import DocumentConverter

logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".asciidoc",
    ".adoc",
    ".tex",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".wav",
    ".mp3",
    ".vtt",
    ".xml",
    ".json",
}


def is_supported(file_path):
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path):
    ext = file_path.suffix.lower()
    type_map = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".pptx": "pptx",
        ".xlsx": "xlsx",
        ".html": "html",
        ".htm": "html",
        ".md": "markdown",
        ".txt": "text",
        ".asciidoc": "asciidoc",
        ".adoc": "asciidoc",
        ".tex": "latex",
        ".csv": "csv",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".tiff": "image",
        ".tif": "image",
        ".bmp": "image",
        ".webp": "image",
        ".wav": "audio",
        ".mp3": "audio",
        ".vtt": "webvtt",
        ".xml": "xml",
        ".json": "docling-json",
    }
    return type_map.get(ext, "unknown")


class TextSegment:
    def __init__(self, text, page):
        self.text = text
        self.page = page

    def __repr__(self):
        return f"TextSegment(text='{self.text[:50]}...', page={self.page})"


class DocumentIngestor:
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ):
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.verbose = verbose

        self.converter = DocumentConverter()

    def ingest(
        self,
        path: str,
        recursive: bool = False,
        batch_size: int = 10,
    ):
        from secondbrain.embedding import EmbeddingGenerator
        from secondbrain.storage import VectorStorage

        path_obj = Path(path)

        if path_obj.is_file():
            files = [path_obj]
        elif path_obj.is_dir():
            files = list(path_obj.rglob("*")) if recursive else list(path_obj.glob("*"))
            files = [f for f in files if f.is_file() and is_supported(f)]
        else:
            raise ValueError(f"Invalid path: {path}")

        if not files:
            return {"success": 0, "failed": 0}

        embedding_gen = EmbeddingGenerator()
        storage = VectorStorage()

        file_data = []
        for file_path in files:
            try:
                segments = self._extract_text(file_path)
                chunks = [TextSegment(s["text"], s["page"]) for s in segments]
                file_data.append((file_path, chunks, [s["text"] for s in segments]))
            except Exception:
                logger.error(f"Failed to extract text from {file_path}")

        all_chunks = []
        seen_hashes = set()

        for file_path, chunks, texts in file_data:
            for i, (chunk, text) in enumerate(zip(chunks, texts)):
                cleaned = text.strip()
                if not cleaned:
                    continue
                normalized = " ".join(cleaned.lower().split())
                text_hash = hash(normalized)
                if text_hash not in seen_hashes:
                    seen_hashes.add(text_hash)
                    all_chunks.append(
                        {
                            "file_path": file_path,
                            "original_index": i,
                            "text": cleaned,
                            "page": chunk.page,
                            "text_hash": text_hash,
                            "chunk": chunk,
                        }
                    )

        from concurrent.futures import ThreadPoolExecutor, as_completed

        chunk_to_embedding = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(embedding_gen.generate, c["text"]): c
                for c in all_chunks
            }

            for future in as_completed(futures):
                chunk = futures[future]
                try:
                    embedding = future.result()
                    chunk_to_embedding[chunk["text_hash"]] = embedding
                except Exception:
                    logger.error("Failed to generate embedding for chunk")

        all_docs = []
        seen_doc_keys = set()

        for chunk in all_chunks:
            file_path = chunk["file_path"]
            text = chunk["text"]
            page = chunk["page"]
            text_hash = chunk["text_hash"]

            if text_hash not in chunk_to_embedding:
                continue

            doc_key = (str(file_path), page, text_hash)
            if doc_key in seen_doc_keys:
                continue
            seen_doc_keys.add(doc_key)

            embedding = chunk_to_embedding[text_hash]

            file_type = get_file_type(file_path)
            doc = {
                "chunk_id": str(uuid4()),
                "source_file": str(file_path),
                "page_number": page,
                "chunk_text": text,
                "embedding": embedding,
                "metadata": {
                    "file_type": file_type,
                    "ingested_at": None,
                    "chunk_index": chunk["original_index"],
                },
            }
            all_docs.append(doc)

        if all_docs:
            storage.store_batch(all_docs)

        return {"success": len(file_data), "failed": 0}

    def _extract_text(self, file_path):
        try:
            result = self.converter.convert(file_path)
            content = result.document

            segments = []

            if hasattr(content, "texts") and content.texts:
                for text_item in content.texts:
                    if not hasattr(text_item, "text") or not text_item.text:
                        continue

                    page_num = 1
                    if hasattr(text_item, "prov") and text_item.prov:
                        prov = text_item.prov[0]
                        if hasattr(prov, "page_no"):
                            page_num = prov.page_no

                    segments.append({"text": text_item.text, "page": page_num})

            if not segments:
                with file_path.open(encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                    segments = [{"text": text, "page": 1}]

            return segments

        except Exception:
            logger.error(f"Error extracting text from {file_path}")
            raise

    def _chunk_text(self, segments):
        chunks = []

        for segment in segments:
            text = segment["text"]
            page = segment["page"]

            start = 0
            while start < len(text):
                end = start + self.chunk_size

                if end < len(text):
                    last_space = text.rfind(" ", start, end)
                    if last_space > start:
                        end = last_space
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append({"text": chunk_text, "page": page})

                start = end - self.chunk_overlap
                if start < 0:
                    start = 0

        return chunks
