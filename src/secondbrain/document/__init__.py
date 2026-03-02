from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from docling.document_converter import DocumentConverter
from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


class Segment(TypedDict):
    text: str
    page: int


class DocumentExtractionError(Exception):
    pass


class UnsupportedFileError(Exception):
    pass


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


def is_supported(file_path: Path) -> bool:
    """Check if file extension is supported.

    Args:
        file_path: Path to check.

    Returns:
        True if file type is supported, False otherwise.
    """
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
    """Get the file type for a given file path.

    Args:
        file_path: Path to determine file type for.

    Returns:
        File type string (e.g., 'pdf', 'docx', 'image', etc.).
    """
    ext = file_path.suffix.lower()
    type_map: dict[str, str] = {
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


class DocumentIngestor:
    """Handles document ingestion and chunking."""

    def __init__(
        self,
        chunk_size: int = 4096,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ) -> None:
        """Initialize document ingestor.

        Args:
            chunk_size: Size of text chunks in tokens.
            chunk_overlap: Overlap between chunks in tokens.
            verbose: Enable verbose logging.
        """
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
    ) -> dict[str, int]:
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

        failed_files = 0

        embedding_gen = EmbeddingGenerator()
        storage = VectorStorage()

        # Use Segments directly; no need for TextSegment class wrapper
        file_data: list[tuple[Path, list[Segment], list[str]]] = []
        for file_path in files:
            try:
                segments: list[Segment] = self._extract_text(file_path)
                file_data.append((file_path, segments, [s["text"] for s in segments]))
            except (OSError, DocumentExtractionError) as e:
                logger.error(f"Failed to extract text from {file_path}: {e}")
                failed_files += 1
            except Exception as e:
                logger.error(f"Unexpected error extracting text from {file_path}: {e}")
                failed_files += 1

        all_chunks: list[dict[str, Any]] = []
        seen_hashes = set()

        for file_path, chunks, texts in file_data:
            for i, (chunk, text) in enumerate(zip(chunks, texts, strict=True)):
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
                            "page": chunk["page"],
                            "text_hash": text_hash,
                            "chunk": chunk,
                        }
                    )

        from concurrent.futures import ThreadPoolExecutor, as_completed

        from secondbrain.embedding import (
            EmbeddingGenerationError,
            OllamaUnavailableError,
        )

        chunk_to_embedding: dict[int, list[float]] = {}
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(embedding_gen.generate, c["text"]): c
                for c in all_chunks
            }

            for future in as_completed(futures):
                chunk_dict = futures[future]
                try:
                    embedding = future.result()
                    chunk_to_embedding[chunk_dict["text_hash"]] = embedding
                except (OllamaUnavailableError, EmbeddingGenerationError) as e:
                    logger.error(f"Failed to generate embedding for chunk: {e}")
                except Exception as e:
                    logger.error(
                        f"Unexpected error generating embedding for chunk: {e}"
                    )

        all_docs: list[dict[str, Any]] = []
        seen_doc_keys = set()

        for chunk_item in all_chunks:
            file_path = chunk_item["file_path"]
            text = chunk_item["text"]
            page = chunk_item["page"]
            text_hash = chunk_item["text_hash"]

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
                    "chunk_index": chunk_item["original_index"],
                },
            }
            all_docs.append(doc)

        if all_docs:
            storage.store_batch(all_docs)

        return {"success": len(file_data), "failed": failed_files}

    def _extract_text(self, file_path: Path) -> list[Segment]:
        try:
            result = self.converter.convert(file_path)
            content = result.document

            segments: list[Segment] = []

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

        except OSError as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise DocumentExtractionError(f"Failed to read file {file_path}") from e
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise DocumentExtractionError(
                f"Failed to extract text from {file_path}"
            ) from e

    def _chunk_text(self, segments: list[Segment]) -> list[Segment]:
        chunks: list[Segment] = []

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
