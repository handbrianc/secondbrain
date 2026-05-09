"""Root pytest fixtures for all tests with mock fallbacks."""

import os
os.environ["PYTEST_CURRENT_TEST"] = "pytest"

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

os.environ["SECONDBRAIN_TRACING_ENABLED"] = "false"
os.environ["OTEL_METRICS_ENABLED"] = "false"

# Disable PyTorch meta tensor mode globally to prevent xdist serialization errors
# This must happen before any torch imports occur
try:
    import torch
    if hasattr(torch, "set_default_device"):
        torch.set_default_device("cpu")
except ImportError:
    pass  # PyTorch not installed yet


def pytest_configure(config):
    """Called before any tests are collected."""
    try:
        import torch
        # Force CPU as default device before any model loading
        if hasattr(torch, "set_default_device"):
            torch.set_default_device("cpu")
    except ImportError:
        pass  # PyTorch not available

from secondbrain.config import get_config

get_config.cache_clear()


def pytest_sessionstart(session: pytest.Session) -> None:
    """Seed MongoDB with minimal test data before tests run."""
    import socket
    from contextlib import closing

    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(2)
            result = sock.connect_ex(("localhost", 27018))
            if result != 0:
                return
    except Exception:
        return

    client = None
    try:
        from secondbrain.config import Config
        from secondbrain.storage import VectorStorage

        config = Config()

        from pymongo import MongoClient as PyMongoClient

        client = PyMongoClient(config.mongo_uri, serverSelectionTimeoutMS=10000, maxPoolSize=50)
        direct_db = client.get_database(config.mongo_db)
        if "embeddings_test" in direct_db.list_collection_names():
            direct_count = direct_db.embeddings.count_documents({})
        else:
            direct_count = 0

        if direct_count > 0:
            return

        test_documents = [
            {
                "chunk_id": "test-chunk-001",
                "chunk_text": "Test document for testing. This is placeholder text.",
                "source_file": "/test/docs/test.md",
                "file_type": "markdown",
                "metadata": {"title": "Test Document", "page": 1, "test": True},
            },
        ]

        collection = direct_db.get_collection("embeddings_test")
        
        if test_documents:
            collection.insert_many(test_documents)
            print(f"Seeded {len(test_documents)} test documents")

    except Exception as e:
        print(f"Warning: Failed to seed test data: {e}")
    finally:
        if client is not None:
            client.close()


def _mock_docker_manager(request):
    """Automatically mock DockerManager to prevent MongoDB startup."""
    if "test_docker_manager.py" in str(request.path):
        yield
        return
    
    with patch("secondbrain.utils.docker_manager.DockerManager"):
        yield


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return path to a sample PDF file for testing."""
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf not installed for PDF creation")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.multi_cell(
            0,
            10,
            "SecondBrain test document\n\n"
            "This is sample content for testing PDF ingestion with "
            "machine learning and artificial intelligence topics.",
        )
        pdf.output(tmp.name)
        return Path(tmp.name)


@pytest.fixture
def sample_pdf_with_multiple_pages() -> Path:
    """Return path to a multi-page sample PDF file for testing."""
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf not installed for PDF creation")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf = FPDF()
        for page_num in range(1, 4):
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 10, f"Page {page_num} of SecondBrain test document\n\n")
            pdf.multi_cell(
                0,
                10,
                f"This is unique content for page {page_num} covering "
                "machine learning, deep learning, and neural networks.",
            )
        pdf.output(tmp.name)
        return Path(tmp.name)


from typing import Any


@pytest.fixture(scope="session")
def embedding_cache() -> Any:
    """Session-scoped embedding cache to prevent repeated generation."""
    cache: dict[str, list[float]] = {}

    def get_or_create(text: str, embed_gen: Any) -> list[float]:
        if text not in cache:
            cache[text] = embed_gen.generate(text)
        return cache[text]

    return get_or_create


# Global mock fixtures for service-independent testing


@pytest.fixture(scope="function")
def mock_llm():
    """Provide MockLLMProviderWithContext for tests."""
    from secondbrain.rag.providers.mock import MockLLMProviderWithContext
    return MockLLMProviderWithContext()


@pytest.fixture(scope="function")
def mock_storage():
    """Provide MockVectorStorage for tests."""
    from secondbrain.storage import MockVectorStorage
    storage = MockVectorStorage()
    storage.initialize()
    yield storage
    storage.close()


@pytest.fixture(scope="function")
def mock_embedding_gen():
    """Provide MockEmbeddingGenerator for tests."""
    from secondbrain.embedding.mock import MockEmbeddingGenerator
    return MockEmbeddingGenerator(model_name="mock-384", dimension=384)


@pytest.fixture(scope="function")
def mock_searcher():
    """Provide MockSearcher for tests."""
    from secondbrain.search.mock import MockSearcher
    return MockSearcher(verbose=False)


@pytest.fixture(scope="session", autouse=True)
def cleanup_mongo_connections():
    """Ensure MongoDB connections are cleaned up after test session."""
    yield
    import gc
    gc.collect()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Clean up OpenTelemetry resources after tests complete."""
    try:
        from secondbrain.utils.tracing import shutdown_tracing
        shutdown_tracing()
    except Exception:
        # Ignore errors during shutdown - we're already exiting
        pass
