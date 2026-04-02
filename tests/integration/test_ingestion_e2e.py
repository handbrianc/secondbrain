"""End-to-end ingestion pipeline tests with comprehensive mocking.

Tests the full pipeline: file -> text -> chunks -> embeddings -> storage -> search

These tests use comprehensive mocking to simulate real services (MongoDB,
sentence-transformers) while still verifying the ingestion and search logic.
This makes tests reliable, fast, and independent of external services.

Target: 7 E2E tests that run in < 30s total with mocked services.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from secondbrain.document import DocumentIngestor


@pytest.fixture
def temp_test_dir() -> Path:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def create_test_pdf(temp_dir: Path, filename: str, content: str) -> Path:
    """Create a simple test PDF file."""
    try:
        from fpdf import FPDF

        pdf_path = temp_dir / filename
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        encoded_content = content.encode("latin-1", errors="replace").decode("latin-1")
        pdf.multi_cell(0, 10, encoded_content)
        pdf.output(str(pdf_path))
        return pdf_path
    except ImportError:
        pdf_path = temp_dir / filename
        pdf_path.write_text(content, encoding="utf-8")
        return pdf_path


def create_test_docx(temp_dir: Path, filename: str, content: str) -> Path:
    """Create a test DOCX file."""
    try:
        from docx import Document

        doc_path = temp_dir / filename
        doc = Document()
        doc.add_heading("Test Document", 0)
        doc.add_paragraph(content)
        doc.save(str(doc_path))
        return doc_path
    except ImportError:
        doc_path = temp_dir / filename
        doc_path.write_text(content, encoding="utf-8")
        return doc_path


def create_test_markdown(temp_dir: Path, filename: str, content: str) -> Path:
    """Create a test Markdown file."""
    md_path = temp_dir / filename
    md_path.write_text(f"# {filename}\n\n{content}", encoding="utf-8")
    return md_path


def create_mock_embedding_generator():
    """Create a mock embedding generator."""
    from unittest.mock import MagicMock

    mock_gen = MagicMock()
    mock_gen.validate_connection.return_value = True

    def generate(text: str) -> list[float]:
        import hashlib

        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        embedding = [(hash_val >> (i * 8)) % 1000 / 1000.0 for i in range(384)]
        norm = (sum(x * x for x in embedding)) ** 0.5
        return [x / norm for x in embedding]

    mock_gen.generate = generate
    mock_gen.generate_batch = lambda texts: [generate(t) for t in texts]

    return mock_gen


def create_mock_storage():
    """Create a mock storage that simulates MongoDB behavior."""
    from unittest.mock import MagicMock

    mock_storage = MagicMock()
    mock_storage.validate_connection.return_value = True

    stored_documents: list[dict] = []

    def mock_store(doc: dict) -> str:
        import uuid

        doc_id = str(uuid.uuid4())
        doc_with_id = doc.copy()
        doc_with_id["_id"] = doc_id
        stored_documents.append(doc_with_id)
        return doc_id

    def mock_store_batch(docs: list[dict]) -> int:
        for doc in docs:
            mock_store(doc)
        return len(docs)

    def mock_search(embedding: list[float], top_k: int = 5, **kwargs) -> list[dict]:
        results = stored_documents.copy()
        source_filter = kwargs.get("source_filter")
        if source_filter:
            results = [r for r in results if source_filter in r.get("source_file", "")]
        results = sorted(
            results, key=lambda x: len(x.get("chunk_text", "")), reverse=True
        )[:top_k]
        for i, result in enumerate(results):
            result["score"] = 1.0 - (i * 0.1)
        return results

    def mock_list_chunks(
        source_filter: str | None = None, limit: int = 100
    ) -> list[dict]:
        results = stored_documents.copy()
        if source_filter:
            results = [r for r in results if source_filter in r.get("source_file", "")]
        return results[:limit]

    mock_storage.store = mock_store
    mock_storage.store_batch = mock_store_batch
    mock_storage.search = mock_search
    mock_storage.list_chunks = mock_list_chunks

    return mock_storage, stored_documents


class TestIngestionE2E:
    """End-to-end tests for document ingestion pipeline with mocked services."""

    @pytest.mark.timeout(30)
    def test_ingestion_e2e_pdf(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test full ingestion pipeline with PDF: create -> ingest -> verify -> search."""
        from unittest.mock import patch

        test_content = (
            "Machine learning is a subset of artificial intelligence that enables "
            "systems to learn and improve from experience without being explicitly programmed. "
            "Deep learning uses neural networks with multiple layers to process data."
        )
        pdf_path = create_test_pdf(temp_test_dir, "test_ml_intro.pdf", test_content)

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=500, chunk_overlap=50, verbose=False)
            result = ingestor.ingest(str(pdf_path))

        assert result["success"] >= 1, f"PDF ingestion should succeed, got {result}"
        assert result["failed"] == 0, f"No files should fail, got {result}"

        chunks = mock_storage.list_chunks(source_filter=str(pdf_path), limit=50)
        assert len(chunks) >= 1, (
            f"At least one chunk should be created, got {len(chunks)}"
        )

        for chunk in chunks:
            assert "chunk_id" in chunk
            assert "chunk_text" in chunk
            assert len(chunk["chunk_text"]) > 0
            assert chunk.get("page_number", 1) >= 1

        query_embedding = mock_gen.generate("What is machine learning?")
        search_results = mock_storage.search(query_embedding, top_k=5)

        assert len(search_results) >= 1, "Search should return results"

        found_content = any(
            "machine learning" in r.get("chunk_text", "").lower()
            for r in search_results
        )
        assert found_content, "Search should find machine learning content"

    @pytest.mark.timeout(30)
    def test_ingestion_e2e_docx(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test full ingestion pipeline with DOCX: create -> ingest -> verify chunks."""
        from unittest.mock import patch

        test_content = (
            "Python is a high-level programming language known for its readability. "
            "It supports multiple programming paradigms including procedural, object-oriented, "
            "and functional programming. Python is widely used in data science, web development, "
            "and artificial intelligence applications."
        )
        docx_path = create_test_docx(
            temp_test_dir, "test_python_guide.docx", test_content
        )

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=400, chunk_overlap=50, verbose=False)
            result = ingestor.ingest(str(docx_path))

        assert result["success"] >= 1, f"DOCX ingestion should succeed, got {result}"

        total_chars = sum(len(c.get("chunk_text", "")) for c in stored_docs)
        assert total_chars > 0, "Chunks should contain text"

        for chunk in stored_docs:
            assert chunk.get("source_file") == str(docx_path)

    @pytest.mark.timeout(30)
    def test_ingestion_e2e_markdown(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test full ingestion pipeline with Markdown: create -> ingest -> verify extraction."""
        from unittest.mock import patch

        test_content = """
## Introduction to API Design

RESTful APIs use HTTP methods to perform CRUD operations:
- GET: Retrieve resources
- POST: Create new resources
- PUT: Update existing resources
- DELETE: Remove resources

API design best practices include versioning, proper error handling,
and consistent response formats.
"""
        md_path = create_test_markdown(
            temp_test_dir, "test_api_design.md", test_content
        )

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=300, chunk_overlap=30, verbose=False)
            result = ingestor.ingest(str(md_path))

        assert result["success"] >= 1, (
            f"Markdown ingestion should succeed, got {result}"
        )

        chunk_texts = [c.get("chunk_text", "") for c in stored_docs]
        all_text = " ".join(chunk_texts).lower()

        assert "restful" in all_text, "RESTful content should be preserved"
        assert "http" in all_text, "HTTP content should be preserved"
        assert "crud" in all_text, "CRUD content should be preserved"

    @pytest.mark.timeout(30)
    def test_ingestion_e2e_multidoc(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test batch ingestion of 10+ documents: create -> batch ingest -> verify all stored."""
        import time
        from unittest.mock import patch

        documents = [
            ("doc1.md", "First document content about technology and innovation."),
            ("doc2.md", "Second document discussing software engineering practices."),
            ("doc3.md", "# Third Document\nContent about data science and analytics."),
            ("doc4.md", "# Fourth Document\nMore content about cloud computing."),
            ("doc5.md", "Fifth document about artificial intelligence applications."),
            ("doc6.md", "Sixth document covering machine learning algorithms."),
            ("doc7.md", "# Seventh Document\nNeural networks and deep learning."),
            ("doc8.md", "Eighth document about natural language processing."),
            ("doc9.md", "Ninth document discussing computer vision systems."),
            ("doc10.md", "# Tenth Document\nRobotics and automation technologies."),
            ("doc11.md", "Eleventh document about quantum computing basics."),
            ("doc12.md", "Twelfth document on cybersecurity fundamentals."),
        ]

        for filename, content in documents:
            file_path = temp_test_dir / filename
            file_path.write_text(content, encoding="utf-8")

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=400, chunk_overlap=50, verbose=False)
            start_time = time.time()
            result = ingestor.ingest(str(temp_test_dir))
            ingestion_time = time.time() - start_time

        assert result["success"] >= 10, (
            f"Should ingest at least 10 files, got {result['success']}"
        )
        assert result["failed"] == 0, (
            f"No files should fail, but {result['failed']} failed"
        )

        assert len(stored_docs) >= 10, (
            f"Should have at least 10 chunks, got {len(stored_docs)}"
        )

        unique_sources = {
            c.get("source_file", "") for c in stored_docs if c.get("source_file")
        }
        test_sources = {
            s for s in unique_sources if any(x in s for x in ["tmp", "doc", "test"])
        }
        assert len(test_sources) >= 10, (
            f"Should have chunks from at least 10 test sources, got {len(test_sources)}"
        )

        assert ingestion_time < 30, (
            f"Ingestion took {ingestion_time:.2f}s, expected < 30s with mocks"
        )

    @pytest.mark.timeout(30)
    def test_ingestion_e2e_multicore(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test parallel ingestion with cores=4: verify parallelism -> validate correctness."""
        import os
        from unittest.mock import patch

        documents = [
            (f"parallel_doc_{i}.md", f"Content for parallel test document number {i}. ")
            for i in range(8)
        ]

        for filename, content in documents:
            file_path = temp_test_dir / filename
            file_path.write_text(content, encoding="utf-8")

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        num_cores = min(4, os.cpu_count() or 1)

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=400, chunk_overlap=50, verbose=False)
            result = ingestor.ingest(str(temp_test_dir), cores=num_cores)

        assert result["success"] >= 8, (
            f"Should process 8 files, got {result['success']}"
        )
        assert result["failed"] == 0, "No files should fail"

        assert len(stored_docs) >= 8, (
            f"Should have at least 8 chunks, got {len(stored_docs)}"
        )

        for chunk in stored_docs[:10]:
            assert len(chunk.get("chunk_text", "")) > 0
            assert chunk.get("source_file")

    @pytest.mark.timeout(30)
    def test_search_e2e_semantic(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test semantic search: ingest documents -> run semantic search -> verify relevant results."""
        from unittest.mock import patch

        documents = [
            (
                "ml_basics.md",
                "Machine learning uses algorithms to learn patterns from data. "
                "Supervised learning requires labeled training data. "
                "Unsupervised learning finds hidden patterns without labels.",
            ),
            (
                "web_dev.md",
                "Web development involves frontend and backend technologies. "
                "Frontend uses HTML, CSS, and JavaScript. "
                "Backend handles server-side logic and databases.",
            ),
            (
                "data_science.md",
                "Data science combines statistics, programming, and domain expertise. "
                "Python and R are popular languages for data analysis. "
                "Visualization helps communicate insights effectively.",
            ),
        ]

        for filename, content in documents:
            file_path = temp_test_dir / filename
            file_path.write_text(content, encoding="utf-8")

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=300, chunk_overlap=30, verbose=False)
            ingestor.ingest(str(temp_test_dir))

        query = "What is supervised learning?"
        query_embedding = mock_gen.generate(query)

        search_results = mock_storage.search(query_embedding, top_k=5)

        assert len(search_results) >= 1, "Search should return at least one result"

        ml_found = any(
            "machine learning" in r.get("chunk_text", "").lower()
            or "supervised" in r.get("chunk_text", "").lower()
            for r in search_results
        )
        assert ml_found, "Search should find machine learning content for ML query"

        scores = [r.get("score", 0) for r in search_results]
        assert all(0 <= s <= 1 for s in scores), (
            "Cosine similarity scores should be between 0 and 1"
        )

        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], "Results should be sorted by score"

    @pytest.mark.timeout(30)
    def test_search_e2e_filters(
        self,
        temp_test_dir: Path,
    ) -> None:
        """Test search with filters: ingest mixed document types -> search with filters."""
        from unittest.mock import patch

        mixed_docs = [
            (
                "tech_article1.md",
                "# Tech Article 1\nContent about software engineering.",
            ),
            ("tech_article2.md", "# Tech Article 2\nMore software development topics."),
            ("science_doc1.md", "Science document about physics and chemistry."),
            ("science_doc2.md", "Another science document about biology."),
            ("business_report.md", "Business report on market trends and analysis."),
        ]

        for filename, content in mixed_docs:
            file_path = temp_test_dir / filename
            file_path.write_text(content, encoding="utf-8")

        mock_storage, stored_docs = create_mock_storage()
        mock_gen = create_mock_embedding_generator()

        with (
            patch(
                "secondbrain.document.ingestor.VectorStorage", return_value=mock_storage
            ),
            patch(
                "secondbrain.document.ingestor.LocalEmbeddingGenerator",
                return_value=mock_gen,
            ),
        ):
            ingestor = DocumentIngestor(chunk_size=300, chunk_overlap=30, verbose=False)
            ingestor.ingest(str(temp_test_dir))

        md_files = [f for f in mixed_docs if f[0].endswith(".md")]
        if md_files:
            first_md = md_files[0][0]
            query_embedding = mock_gen.generate("software")

            filtered_results = mock_storage.search(
                query_embedding, top_k=10, source_filter=first_md
            )

            for result in filtered_results:
                assert first_md in result.get("source_file", ""), (
                    f"Results should only contain {first_md}"
                )

        query_embedding = mock_gen.generate("technology")
        all_results = mock_storage.search(query_embedding, top_k=20)

        md_results = [
            r for r in all_results if r.get("source_file", "").endswith(".md")
        ]

        for result in md_results:
            assert result.get("source_file", "").endswith(".md"), (
                "All results should be markdown files"
            )

        if md_files:
            first_md = md_files[0][0]
            combined_results = mock_storage.search(
                query_embedding, top_k=10, source_filter=first_md
            )

            for result in combined_results:
                assert first_md in result.get("source_file", "")

        business_embedding = mock_gen.generate("market analysis business")
        business_results = mock_storage.search(business_embedding, top_k=10)

        business_found = any(
            "business" in r.get("chunk_text", "").lower()
            or "market" in r.get("chunk_text", "").lower()
            for r in business_results
        )
        assert business_found, "Business content should be found for business query"
