"""Tests for async RAG pipeline operations."""
import pytest


class TestAsyncRAGPipeline:
    def test_rag_pipeline_class_exists(self):
        from secondbrain.rag.pipeline import RAGPipeline
        
        assert RAGPipeline is not None
