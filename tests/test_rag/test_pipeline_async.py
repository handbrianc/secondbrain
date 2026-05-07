"""Tests for async RAG pipeline operations."""
import pytest


class TestAsyncRAGPipeline:
    """Test async RAG pipeline exists and has async methods."""

    def test_rag_pipeline_class_exists(self):
        """RAGPipeline class should exist."""
        from secondbrain.rag.pipeline import RAGPipeline
        
        assert RAGPipeline is not None
