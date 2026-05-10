"""Root pytest fixtures for all tests with mock fallbacks."""

import os

os.environ["PYTEST_CURRENT_TEST"] = "pytest"
os.environ["SECONDBRAIN_TRACING_ENABLED"] = "false"
os.environ["OTEL_METRICS_ENABLED"] = "false"

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Disable PyTorch meta tensor mode globally to prevent xdist serialization errors
try:
    import torch

    if hasattr(torch, "set_default_device"):
        torch.set_default_device("cpu")
except ImportError:
    pass


def pytest_configure(config: Any) -> None:
    try:
        import torch

        if hasattr(torch, "set_default_device"):
            torch.set_default_device("cpu")
    except ImportError:
        pass


from secondbrain.config import get_config

get_config.cache_clear()


def pytest_sessionstart(session: pytest.Session) -> None:
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

        client = PyMongoClient(
            config.mongo_uri, serverSelectionTimeoutMS=10000, maxPoolSize=50
        )
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
    if "test_docker_manager.py" in str(request.path):
        yield
        return

    with patch("secondbrain.utils.docker_manager.DockerManager"):
        yield


@pytest.fixture
def sample_pdf_path() -> Path:
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
    cache: dict[str, list[float]] = {}

    def get_or_create(text: str, embed_gen: Any) -> list[float]:
        if text not in cache:
            cache[text] = embed_gen.generate(text)
        return cache[text]

    return get_or_create


# Global mock fixtures for service-independent testing


@pytest.fixture(scope="function")
def mock_llm():
    from secondbrain.rag.providers.mock import MockLLMProviderWithContext

    return MockLLMProviderWithContext()


@pytest.fixture(scope="function")
def mock_storage():
    from secondbrain.storage import MockVectorStorage

    storage = MockVectorStorage()
    storage.initialize()
    yield storage
    storage.close()


@pytest.fixture(scope="function")
def mock_embedding_gen():
    from secondbrain.embedding.mock import MockEmbeddingGenerator

    return MockEmbeddingGenerator(model_name="mock-384", dimension=384)


@pytest.fixture(scope="function")
def mock_searcher():
    from secondbrain.search.mock import MockSearcher

    return MockSearcher(verbose=False)


@pytest.fixture(scope="session", autouse=True)
def cleanup_mongo_connections() -> None:
    yield


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        from secondbrain.utils.tracing import shutdown_tracing

        shutdown_tracing()
    except Exception:
        pass
