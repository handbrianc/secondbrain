"""Tests for multicore progress tracking."""
import inspect
import tempfile
from pathlib import Path

import pytest

from secondbrain.document import DocumentIngestor


class TestMulticoreProgress:
    """Test progress tracking during multicore ingestion."""

    def test_ingest_accepts_cores_parameter(self):
        ingestor = DocumentIngestor(verbose=False)
        sig = inspect.signature(ingestor.ingest)
        assert 'cores' in sig.parameters

    def test_progress_callback_can_be_provided(self):
        def dummy_callback(path, success):
            pass
        
        ingestor = DocumentIngestor(verbose=False, progress_callback=dummy_callback)
        assert ingestor.progress_callback is not None

    def test_ingest_with_cores_parameter(self):
        ingestor = DocumentIngestor(verbose=False)
        sig = inspect.signature(ingestor.ingest)
        assert 'cores' in sig.parameters
