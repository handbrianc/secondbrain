"""End-to-end integration tests for document ingestion.

Note: Full end-to-end ingestion tests require real MongoDB and embedding service
due to multiprocessing architecture. See test_integration/test_end_to_end.py for
workflow tests using mongomock.
"""

from pathlib import Path


class TestEndToEndIngestion:
    """Test full document ingestion workflow."""
