"""Tests for async embedding generation with native async client."""
import asyncio
import pytest


class TestAsyncEmbeddingNative:
    """Test native async embedding generation using aiohttp/httpx."""

    def test_async_embedding_method_exists(self):
        """LocalEmbeddingGenerator should have async method."""
        from secondbrain.embedding.local import LocalEmbeddingGenerator
        
        gen = LocalEmbeddingGenerator()
        
        assert hasattr(gen, 'generate_async')
        assert callable(gen.generate_async)

    def test_async_batch_method_exists(self):
        """LocalEmbeddingGenerator should have async batch method."""
        from secondbrain.embedding.local import LocalEmbeddingGenerator
        
        gen = LocalEmbeddingGenerator()
        
        assert hasattr(gen, 'generate_batch_async')
        assert callable(gen.generate_batch_async)

    @pytest.mark.asyncio
    async def test_async_embedding_generates_valid_vector(self):
        """Async embedding generates a valid vector with correct dimensions."""
        from secondbrain.embedding.local import LocalEmbeddingGenerator
        
        gen = LocalEmbeddingGenerator()
        
        # Generate async embedding
        embedding = await gen.generate_async("test text for embedding")
        
        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        # All values should be floats
        assert all(isinstance(v, float) for v in embedding)

    @pytest.mark.asyncio
    async def test_async_batch_embedding_returns_correct_count(self):
        """Async batch embedding returns one vector per input text."""
        from secondbrain.embedding.local import LocalEmbeddingGenerator
        
        gen = LocalEmbeddingGenerator()
        
        texts = ["text 1", "text 2", "text 3"]
        embeddings = await gen.generate_batch_async(texts)
        
        assert len(embeddings) == len(texts)
        for emb in embeddings:
            assert isinstance(emb, list)
            assert len(emb) > 0
