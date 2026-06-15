"""Root pytest fixtures for all tests with mock fallbacks."""

import os

os.environ["PYTHOSTRACKING_TEST"] = "pytest"
os.environ["SECONDBRAIN_TRACING_ENABLED"] = "false"
os.environ["OTEL_METRICS_ENABLED"] = "false"

from collections.abc import Generator
from pathlib import Path
from typing import Any
import pytest

# Disable PyTorch meta tensor mode globally to prevent xdist serialization errors
try:
    import torch

    if hasattr(torch, "set_default_device"):
        torch.set_default_device("cpu")
except ImportError:
    pass


def pytest_configure(config: Any) -> None:
    from secondbrain.config import get_config
    try:
        import torch

        if hasattr(torch, "set_default_device"):
            torch.set_default_device("cpu")
    except ImportError:
        pass

    get_config.cache_clear()

    try:
        import secondbrain.utils.tracing as tracing_mod
        tracing_mod._tracer = None
        tracing_mod._tracing_enabled = False
    except Exception:
        pass


@pytest.fixture
def sample_pdf_path() -> Path:
    """Return path to a sample PDF file for testing.

    Creates a temporary PDF file with test content using reportlab (preferred)
    or fpdf as fallback. Skips only if neither library is available.
    """
    import tempfile

    # Try reportlab first (preferred, already installed in test env)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        pass
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
            c = canvas.Canvas(pdf_path, pagesize=A4)
            _, height = A4
            c.setFont("Helvetica", 12)
            c.drawString(50 * mm, height - 50 * mm,
                "SecondBrain test document\n\n"
                "This is sample content for testing PDF ingestion with "
                "machine learning and artificial intelligence topics."
            )
            c.save()
            return Path(pdf_path)

    # Fallback to fpdf
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("Neither reportlab nor fpdf is installed for PDF creation")

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
    """Return path to a multi-page sample PDF file for testing.

    Creates a temporary multi-page PDF file with test content using reportlab
    (preferred) or fpdf as fallback. Skips only if neither library is available.
    """
    import tempfile

    # Try reportlab first (preferred, already installed in test env)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError:
        pass
    else:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            pdf_path = tmp.name
            c = canvas.Canvas(pdf_path, pagesize=A4)
            _, height = A4
            for page_num in range(1, 4):
                c.setFont("Helvetica", 12)
                c.drawString(50 * mm, height - 50 * mm,
                    f"Page {page_num} of SecondBrain test document\n\n"
                    f"This is unique content for page {page_num} covering "
                    "machine learning, deep learning, and neural networks."
                )
                c.showPage()
            c.save()
            return Path(pdf_path)

    # Fallback to fpdf
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("Neither reportlab nor fpdf is installed for PDF creation")

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


# Module-level cache: populated once when shared_embedding_model is first used
_SB_WARM_MODEL: Any = None


@pytest.fixture(scope="session")
def shared_embedding_model() -> Any:
    """Session-scoped pre-loaded embedding model.

    Lazily warms a LocalEmbeddingProvider("all-MiniLM-L6-v2") on first use,
    then installs a __init__ patch so all subsequent default-model constructions
    share the already-loaded model — avoiding the ~17-25 s SentenceTransformer
    cold-load tax on every new instantiation.

    Tests that construct LocalEmbeddingProvider with a custom model name are
    unaffected (patched __init__ delegates to real __init__).  Tests that wrap
    sentence_transformers.SentenceTransformer in a mock context are also
    unaffected (_model is pre-set by the mock block, triggering the passthrough).
    """
    from secondbrain.embedding.local import LocalEmbeddingProvider

    global _SB_WARM_MODEL

    if _SB_WARM_MODEL is None:
        _SB_WARM_MODEL = LocalEmbeddingProvider(model_name="all-MiniLM-L6-v2").model

    orig_init = LocalEmbeddingProvider.__init__

    def patched_init(
        self: Any, model_name: str = "all-MiniLM-L6-v2", **kwargs: Any
    ) -> None:
        if model_name == "all-MiniLM-L6-v2":
            # Passthrough if a test already initialised _model under a mock
            if getattr(self, "_model", None) is not None:
                orig_init(self, model_name=model_name, **kwargs)
                return
            self.model_name = model_name
            self._model = _SB_WARM_MODEL
            self._connection_valid = True
            self._connection_checked_at = 0.0
        else:
            orig_init(self, model_name=model_name, **kwargs)

    LocalEmbeddingProvider.__init__ = patched_init  # type: ignore[method-assign]

    yield _SB_WARM_MODEL

    LocalEmbeddingProvider.__init__ = orig_init  # type: ignore[method-assign]


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
    storage._chunks.clear()
    storage._chunk_ids.clear()
    storage._initialized = False
    storage.close()


@pytest.fixture(scope="function")
def mock_embedding_gen():
    from secondbrain.embedding.mock import MockEmbeddingGenerator

    return MockEmbeddingGenerator(model_name="mock-384", dimension=384)


@pytest.fixture(scope="function")
def mock_searcher():
    from secondbrain.search.mock import MockSearcher

    return MockSearcher(verbose=False)


@pytest.fixture(scope="function", autouse=True)
def cleanup_mongo_connections() -> Generator[None, None, None]:
    yield
    # Prevent env var leakage across randomized test order
    for _key in (
        "SECONDBRAIN_LLM_API_KEY",
        "SECONDBRAIN_OPENAI_API_KEY",
        "SECONDBRAIN_OPENAI_BASE_URL",
    ):
        os.environ.pop(_key, None)
    # Reset global tracing cache to prevent stale flag from earlier tests
    import secondbrain.utils.tracing as _tm

    _tm._tracing_enabled = False
    _tm._tracer = None
    _tm._metrics_enabled = False
    # Reset Config singleton cache
    import secondbrain.config as _cm

    _cm.get_config.cache_clear()
    


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    try:
        from secondbrain.utils.tracing import shutdown_tracing

        shutdown_tracing()
    except Exception:
        pass
