"""Root pytest fixtures for all tests."""

import os
from unittest.mock import patch

import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Seed MongoDB with test data before tests run.

    This ensures quantitative tests have data to run against instead of skipping.
    Creates 10 test chunks with embeddings that have semantic overlap for testing.
    """
    import socket
    from contextlib import closing

    # Check if MongoDB is reachable before attempting to seed
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(2)
            result = sock.connect_ex(("localhost", 27018))
            if result != 0:
                return  # MongoDB not available, skip seeding
    except Exception:
        return  # Network issue, skip seeding

    try:
        from secondbrain.config import Config
        from secondbrain.embedding.local import LocalEmbeddingGenerator
        from secondbrain.storage import VectorStorage

        config = Config()
        storage = VectorStorage()
        embedding_gen = LocalEmbeddingGenerator(model_name=config.local_embedding_model)

        # Check if data already exists
        existing_chunks = storage.list_chunks(limit=1)
        if len(existing_chunks) > 0:
            return  # Data already seeded

        # Generate 50 test documents with semantic overlap for threshold tests
        # Include documents that answer common test queries
        test_documents = [
            # Documents for "What is SecondBrain?" query
            {
                "chunk_text": "SecondBrain is a powerful local document intelligence CLI tool that enables semantic search over your documents using state-of-the-art embedding models and MongoDB vector search.",
                "source_file": "/test/docs/what-is-secondbrain.md",
                "file_type": "markdown",
                "metadata": {"title": "What is SecondBrain?", "page": 1},
            },
            {
                "chunk_text": "SecondBrain provides privacy-first document intelligence with multi-format support for PDF, DOCX, PPTX, XLSX, HTML, and Markdown files.",
                "source_file": "/test/docs/features.md",
                "file_type": "markdown",
                "metadata": {"title": "SecondBrain Features", "page": 1},
            },
            # Documents for "How does semantic search work?" query
            {
                "chunk_text": "Semantic search uses vector embeddings to find conceptually similar documents. SecondBrain uses sentence-transformers models like all-MiniLM-L6-v2 for generating high-quality 384-dimensional embeddings.",
                "source_file": "/test/docs/semantic-search.md",
                "file_type": "markdown",
                "metadata": {"title": "Semantic Search", "page": 1},
            },
            {
                "chunk_text": "The benefits of semantic search include finding conceptually related content without exact keyword matches, understanding context and intent, and providing more relevant search results. Semantic search improves information retrieval accuracy.",
                "source_file": "/test/docs/semantic-search-benefits.md",
                "file_type": "markdown",
                "metadata": {"title": "Benefits of Semantic Search", "page": 1},
            },
            {
                "chunk_text": "Vector search works by converting text into mathematical vectors, then finding documents with similar vectors using cosine similarity. This allows finding conceptually related content even without exact keyword matches.",
                "source_file": "/test/docs/vector-search.md",
                "file_type": "markdown",
                "metadata": {"title": "Vector Search Explained", "page": 1},
            },
            # Documents for "What is MongoDB used for?" query
            {
                "chunk_text": "MongoDB is used in SecondBrain as a vector database for storing document embeddings. It provides efficient vector search capabilities with configurable indexes and supports authentication.",
                "source_file": "/test/docs/mongodb-usage.md",
                "file_type": "markdown",
                "metadata": {"title": "MongoDB in SecondBrain", "page": 1},
            },
            {
                "chunk_text": "The MongoDB collection in SecondBrain stores chunked documents with their embeddings, metadata, and source file information for efficient retrieval during semantic search operations.",
                "source_file": "/test/docs/database-schema.md",
                "file_type": "markdown",
                "metadata": {"title": "Database Schema", "page": 1},
            },
            # Documents for "What is the purpose of document chunking?" query
            {
                "chunk_text": "Document chunking is the process of splitting large documents into smaller, manageable pieces for embedding and search. Chunking preserves context while enabling efficient vector search operations.",
                "source_file": "/test/docs/document-chunking.md",
                "file_type": "markdown",
                "metadata": {"title": "Document Chunking Purpose", "page": 1},
            },
            {
                "chunk_text": "The purpose of document chunking in SecondBrain is to break down large documents into smaller segments that can be individually embedded and searched. This improves retrieval accuracy and search performance.",
                "source_file": "/test/docs/chunking-strategy.md",
                "file_type": "markdown",
                "metadata": {"title": "Chunking Strategy", "page": 1},
            },
            # Documents for "How to ingest documents?" query
            {
                "chunk_text": "To ingest documents in SecondBrain, use the CLI command: secondbrain ingest /path/to/documents/. The system automatically detects file formats, chunks documents, generates embeddings, and stores them in MongoDB for semantic search.",
                "source_file": "/test/docs/ingestion-guide.md",
                "file_type": "markdown",
                "metadata": {"title": "Document Ingestion Guide", "page": 1},
            },
            {
                "chunk_text": "Document ingestion in SecondBrain supports multiple formats including PDF, DOCX, PPTX, XLSX, HTML, and Markdown. Use the ingest command with optional flags for chunk size, overlap, and CPU cores: secondbrain ingest /path/ --chunk-size 4096 --cores 4",
                "source_file": "/test/docs/ingestion-commands.md",
                "file_type": "markdown",
                "metadata": {"title": "Ingestion Commands", "page": 1},
            },
            # Specific answers for ROUGE test queries
            {
                "chunk_text": "The default chunk size in SecondBrain is 4096 tokens. This configuration parameter controls how documents are split into smaller pieces for embedding and vector search. You can override this with the --chunk-size flag.",
                "source_file": "/test/docs/default-chunk-size.md",
                "file_type": "markdown",
                "metadata": {"title": "Default Chunk Size", "page": 1},
            },
            {
                "chunk_text": "The default embedding model is all-MiniLM-L6-v2 from the sentence-transformers library. This model provides a good balance between speed and accuracy for semantic search operations.",
                "source_file": "/test/docs/default-embedding-model.md",
                "file_type": "markdown",
                "metadata": {"title": "Default Embedding Model", "page": 1},
            },
            {
                "chunk_text": "SecondBrain supports PDF, DOCX, PPTX, XLSX, HTML, Markdown, images, and audio files for document ingestion. The Ingestor class uses Docling for multi-format document parsing and processing.",
                "source_file": "/test/docs/supported-formats.md",
                "file_type": "markdown",
                "metadata": {"title": "Supported Document Formats", "page": 1},
            },
            {
                "chunk_text": "To configure the MongoDB connection URI, set the SECONDBRAIN_MONGO_URI environment variable to your MongoDB connection string. This is the primary method for specifying database connectivity and authentication.",
                "source_file": "/test/docs/mongodb-configuration.md",
                "file_type": "markdown",
                "metadata": {"title": "MongoDB Configuration", "page": 1},
            },
            {
                "chunk_text": "The default top-k value for search results is 5. This means the search returns the 5 most relevant results by default. You can adjust this with the --top-k flag or in your configuration.",
                "source_file": "/test/docs/top-k-default.md",
                "file_type": "markdown",
                "metadata": {"title": "Default Top-K Value", "page": 1},
            },
            {
                "chunk_text": "The default chunk overlap is 256 tokens. This overlap preserves context between adjacent chunks and improves retrieval quality for queries that span multiple chunks.",
                "source_file": "/test/docs/chunk-overlap.md",
                "file_type": "markdown",
                "metadata": {"title": "Chunk Overlap Setting", "page": 1},
            },
        ]

        # Add more topic-based documents for broader coverage
        topics = [
            "configuration",
            "setup",
            "formats",
            "resilience",
            "search",
            "performance",
            "rag",
            "testing",
            "embeddings",
            "chunking",
            "circuit breaker",
            "rate limiting",
            "vector database",
            "document processing",
            "API design",
            "security",
            "monitoring",
            "deployment",
            "optimization",
            "caching",
            "indexing",
            "querying",
            "data modeling",
            "schema design",
            "backup",
            "recovery",
            "scaling",
            "load balancing",
            "fault tolerance",
            "error handling",
            "logging",
            "tracing",
            "metrics",
            "alerts",
            "dashboard",
            "reporting",
            "automation",
            "CI/CD",
            "version control",
            "collaboration",
            "documentation",
            "knowledge base",
            "information retrieval",
            "natural language processing",
            "machine learning",
            "deep learning",
            "neural networks",
            "transformers",
            "attention mechanism",
        ]

        for _, topic in enumerate(topics):
            test_documents.append(
                {
                    "chunk_text": f"{topic.capitalize()} is a key concept in SecondBrain. This document discusses {topic} in detail with examples and best practices for implementation.",
                    "source_file": f"/test/docs/{topic.replace(' ', '_')}.md",
                    "file_type": "markdown",
                    "metadata": {"title": f"{topic.capitalize()} Guide", "page": 1},
                }
            )

        # Generate embeddings and store chunks
        chunks_to_store = []
        for doc in test_documents:
            embedding = embedding_gen.generate(doc["chunk_text"])
            chunk = {
                "chunk_text": doc["chunk_text"],
                "source_file": doc["source_file"],
                "file_type": doc["file_type"],
                "metadata": doc["metadata"],
                "embedding": embedding,
            }
            chunks_to_store.append(chunk)

        # Store all chunks
        storage.store_batch(chunks_to_store)

    except Exception as e:
        # If seeding fails, tests will skip gracefully
        pass


# Set test environment variables before tests run
def pytest_configure(config: pytest.Config) -> None:
    """Set test environment variables before tests run.

    This ensures all tests use the correct test service URLs
    (ports 27018 and 11435) instead of production ports.
    """
    # Set test MongoDB URI with authentication (authSource=admin for root user)
    if "SECONDBRAIN_MONGO_URI" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_URI"] = (
            "mongodb://testuser:testpass@localhost:27018/secondbrain_test?authSource=admin"
        )

    # Set test Ollama host
    if "SECONDBRAIN_OLLAMA_HOST" not in os.environ:
        os.environ["SECONDBRAIN_OLLAMA_HOST"] = "http://localhost:11435"

    # Set test database and collection
    if "SECONDBRAIN_MONGO_DB" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_DB"] = "secondbrain_test"

    if "SECONDBRAIN_MONGO_COLLECTION" not in os.environ:
        os.environ["SECONDBRAIN_MONGO_COLLECTION"] = "test_embeddings"


# Auto-mock DockerManager for all tests to prevent MongoDB startup
# Integration tests that need real MongoDB will patch it back or use real setup
original_patch = patch("secondbrain.utils.docker_manager.DockerManager")
mock_manager = None


@pytest.fixture(autouse=True, scope="function")
def _mock_docker_manager():
    """Automatically mock DockerManager to prevent MongoDB startup."""
    global mock_manager
    if mock_manager is None:
        mock_manager = original_patch.start()
    yield
    # No cleanup needed - patch is persistent
