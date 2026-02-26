"""Document ingestion module."""

import logging
import uuid
from pathlib import Path
from typing import Any

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


def is_supported(file_path: Path) -> bool:
    return file_path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_file_type(file_path: Path) -> str:
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


class DocumentIngestor:
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        verbose: bool = False,
    ) -> None:
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
            logger.warning("No supported files found")
            return {"success": 0, "failed": 0}

        embedding_gen = EmbeddingGenerator()
        storage = VectorStorage()

        success_count = 0
        failed_count = 0

        for file_path in files:
            try:
                if self.verbose:
                    logger.info(f"Processing: {file_path}")

                text = self._extract_text(file_path)
                chunks = self._chunk_text(text)
                file_type = get_file_type(file_path)

                for i, chunk in enumerate(chunks):
                    chunk_id = str(uuid.uuid4())
                    embedding = embedding_gen.generate(chunk["text"])

                    doc = {
                        "chunk_id": chunk_id,
                        "source_file": str(file_path),
                        "page_number": chunk.get("page", 1),
                        "chunk_text": chunk["text"],
                        "embedding": embedding,
                        "metadata": {
                            "file_type": file_type,
                            "ingested_at": None,
                            "chunk_index": i,
                        },
                    }

                    storage.store(doc)

                success_count += 1
                logger.info(f"Successfully processed: {file_path}")

            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to process {file_path}: {e}")

        return {"success": success_count, "failed": failed_count}

    def _extract_text(self, file_path: Path) -> list[dict[str, Any]]:
        try:
            result = self.converter.convert(file_path)
            content = result.document

            segments: list[dict[str, Any]] = []
            for page in content.pages:
                text = getattr(page, "text", "")
                if text.strip():
                    page_num = getattr(page, "page_number", 1)
                    segments.append({"text": text, "page": page_num})

            if not segments:
                with file_path.open(encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                    segments = [{"text": text, "page": 1}]

            return segments

        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            raise

    def _chunk_text(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
