"""Benchmark tests for document ingestion throughput.

This module measures the performance of document ingestion operations:
- Single document ingestion
- Batch ingestion
- Embedding generation speed

Run with: pytest benchmarks/test_ingestion_benchmarks.py --benchmark-only
"""

import contextlib
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_docx_file():
    """Create a temporary DOCX file for benchmarking."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        # Create a simple DOCX with some content
        f.write(b"PK\x03\x04")  # ZIP header (DOCX is a ZIP file)
        f.write(b"Test content for benchmarking " * 100)
        temp_path = f.name

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def temp_pdf_file():
    """Create a temporary PDF file for benchmarking."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        # Create a minimal PDF structure
        f.write(b"%PDF-1.4\n")
        f.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        f.write(b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n")
        f.write(
            b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
        )
        f.write(b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n116\n%%EOF\n")
        temp_path = f.name

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


def test_ingest_single_document(benchmark, temp_docx_file):
    """Benchmark single document ingestion throughput."""
    from secondbrain.config import get_config
    from secondbrain.document import DocumentIngestor

    get_config.cache_clear()

    def ingest_document():
        ingestor = DocumentIngestor()
        with contextlib.suppress(Exception):
            ingestor.ingest(temp_docx_file)

    result = benchmark(ingest_document)

    print(f"\nIngestion benchmark: {result.stats['mean'] * 1000:.2f}ms mean")
    print(f"Std deviation: {result.stats['stddev'] * 1000:.2f}ms")


def test_batch_ingest_documents(benchmark, temp_docx_file, temp_pdf_file):
    """Benchmark batch document ingestion throughput."""
    from secondbrain.document import DocumentIngestor

    files = [temp_docx_file, temp_pdf_file]

    def ingest_batch():
        ingestor = DocumentIngestor()
        for file_path in files:
            with contextlib.suppress(Exception):
                ingestor.ingest(file_path)

    result = benchmark(ingest_batch)

    docs_per_second = len(files) / result.stats["mean"]
    print(f"\nBatch ingestion: {docs_per_second:.2f} docs/second")


if __name__ == "__main__":
    pytest.main([__file__, "--benchmark-only", "-v"])


# ============================================================================
# Additional Performance Benchmarks
# ============================================================================
#
# These benchmarks measure key performance metrics for the SecondBrain tool.
# Run with: pytest benchmarks/ --benchmark-only
#
# For regression testing, see:
#   - scripts/run_benchmarks.sh
#   - scripts/benchmark_compare.py
#   - docs/performance-testing.md
#

import time
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_mongodb():
    """Mock MongoDB connection for consistent benchmarking."""
    with patch("secondbrain.storage.MongoClient") as mock_client:
        mock_db = MagicMock()
        mock_client.return_value.__getitem__.return_value = mock_db
        mock_db.__getitem__.return_value = MagicMock()
        yield mock_client


@pytest.mark.benchmark
def test_embedding_generation(benchmark, mock_mongodb):
    """Benchmark embedding generation performance."""
    from secondbrain.embedding import EmbeddingGenerator

    generator = EmbeddingGenerator()
    test_texts = [
        "This is a test document for benchmarking embedding generation.",
        "Machine learning is a subset of artificial intelligence.",
        "Python is a popular programming language for data science.",
    ]

    def generate_embeddings():
        for text in test_texts:
            embedding = generator.generate(text)
            assert len(embedding) > 0

    result = benchmark(generate_embeddings)

    docs_per_second = len(test_texts) / result.stats["mean"]
    print(f"\nEmbedding generation: {docs_per_second:.2f} docs/second")


@pytest.mark.benchmark
def test_chunking_performance(benchmark):
    """Benchmark document chunking performance."""
    from secondbrain.document import TextChunker

    chunker = TextChunker(chunk_size=500, chunk_overlap=50)
    test_text = " ".join(["This is a test sentence."] * 100)

    def chunk_document():
        chunks = chunker.chunk(test_text)
        assert len(chunks) > 0

    result = benchmark(chunk_document)

    chars_per_second = len(test_text) / result.stats["mean"]
    print(f"\nChunking performance: {chars_per_second:,.0f} chars/second")


@pytest.mark.benchmark
def test_metadata_extraction(benchmark, temp_docx_file):
    """Benchmark metadata extraction performance."""
    from secondbrain.document import DocumentParser

    parser = DocumentParser()

    def extract_metadata():
        metadata = parser.extract_metadata(temp_docx_file)
        assert metadata is not None

    result = benchmark(extract_metadata)

    print(f"\nMetadata extraction: {result.stats['mean'] * 1000:.2f}ms mean")


# Mark these as fast benchmarks for pre-commit hook
fast = pytest.mark.skipif(
    "BENCHMARK_FAST" not in [k for k, v in globals().items() if isinstance(v, str)],
    reason="Skip in fast mode",
)
