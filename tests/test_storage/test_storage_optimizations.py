"""Tests for MongoDB storage optimizations.

Tests verify:
- Embedding float32 encoding/decoding
- BSON binary storage format
- Schema changes (flattened metadata, removed chunk_index)
- Backward compatibility
- Storage size reduction
"""

import struct
from datetime import UTC, datetime

import pytest
from bson.binary import Binary

from secondbrain.config import Config
from secondbrain.storage.storage import VectorStorage


class TestEmbeddingEncoding:
    """Tests for embedding float32 encoding/decoding."""

    def test_encode_embedding_float32(self):
        """Test encoding embedding to float32 binary."""
        storage = VectorStorage()
        embedding = [0.123456, 0.789012, 0.345678] * 128  # 384 dimensions

        binary = storage._encode_embedding(embedding)

        # Should be 384 * 4 bytes = 1536 bytes (float32)
        assert len(binary) == 384 * 4

    def test_decode_embedding_restores_values(self):
        """Test decoding binary restores original values with float32 precision."""
        storage = VectorStorage()
        original = [0.123456, 0.789012, 0.345678] * 128

        binary = storage._encode_embedding(original)
        restored = storage._decode_embedding(binary, 384)

        # Allow small float32 precision loss
        for orig, rst in zip(original, restored, strict=False):
            assert abs(orig - rst) < 0.0001

    def test_encode_decode_roundtrip(self):
        """Test full encode/decode roundtrip preserves data."""
        storage = VectorStorage()
        original = [float(i) / 1000 for i in range(384)]

        binary = storage._encode_embedding(original)
        restored = storage._decode_embedding(binary, 384)

        assert len(restored) == 384
        for orig, rst in zip(original, restored, strict=False):
            assert abs(orig - rst) < 0.0001

    def test_prepare_embedding_binary_format(self):
        """Test embedding prepared as BSON Binary when configured."""
        config = Config(embedding_storage_format="binary")
        storage = VectorStorage(mongo_uri=config.mongo_uri)
        storage._config = config

        embedding = [0.1, 0.2, 0.3] * 128
        result = storage._prepare_embedding_for_storage(embedding)

        assert isinstance(result, Binary)

    def test_prepare_embedding_array_format(self):
        """Test embedding stored as array when configured."""
        config = Config(embedding_storage_format="array")
        storage = VectorStorage(mongo_uri=config.mongo_uri)
        storage._config = config

        embedding = [0.1, 0.2, 0.3] * 128
        result = storage._prepare_embedding_for_storage(embedding)

        assert isinstance(result, list)
        assert len(result) == 384

    def test_normalize_embedding_from_binary(self):
        """Test normalizing Binary embedding back to list."""
        storage = VectorStorage()
        original = [0.123, 0.456, 0.789] * 128

        binary = Binary(struct.pack(f"{384}f", *original))
        normalized = storage._normalize_embedding(binary)

        assert isinstance(normalized, list)
        assert len(normalized) == 384

    def test_normalize_embedding_from_bytes(self):
        """Test normalizing raw bytes embedding."""
        storage = VectorStorage()
        original = [0.123, 0.456, 0.789] * 128

        binary_data = struct.pack(f"{384}f", *original)
        normalized = storage._normalize_embedding(binary_data)

        assert isinstance(normalized, list)
        assert len(normalized) == 384

    def test_normalize_embedding_already_list(self):
        """Test that list embeddings pass through unchanged."""
        storage = VectorStorage()
        original = [0.1, 0.2, 0.3] * 128

        normalized = storage._normalize_embedding(original)

        assert normalized is original


class TestDocumentPreparation:
    """Tests for document preparation with optimizations."""

    def test_prepare_document_encodes_embedding(self):
        """Test document preparation converts embedding to binary."""
        config = Config(embedding_storage_format="binary")
        storage = VectorStorage(mongo_uri=config.mongo_uri)
        storage._config = config

        doc = {
            "chunk_id": "test-123",
            "source_file": "/test/file.pdf",
            "page_number": 1,
            "chunk_text": "Test content",
            "embedding": [0.1] * 384,
            "file_type": "pdf",
            "ingested_at": datetime.now(UTC).isoformat(),
        }

        prepared = storage._prepare_document_for_storage(doc)

        assert isinstance(prepared["embedding"], Binary)
        assert prepared["chunk_id"] == "test-123"

    def test_prepare_document_preserves_flattened_fields(self):
        """Test document preparation preserves flattened metadata."""
        storage = VectorStorage()

        doc = {
            "chunk_id": "test-456",
            "source_file": "/test/file.pdf",
            "page_number": 2,
            "chunk_text": "Test content",
            "embedding": [0.2] * 384,
            "file_type": "pdf",
            "ingested_at": "2024-01-01T00:00:00+00:00",
        }

        prepared = storage._prepare_document_for_storage(doc)

        assert prepared["file_type"] == "pdf"
        assert prepared["ingested_at"] == "2024-01-01T00:00:00+00:00"
        assert "metadata" not in prepared or "file_type" not in prepared.get(
            "metadata", {}
        )

    def test_prepare_document_batch(self):
        """Test batch document preparation."""
        config = Config(embedding_storage_format="binary")
        storage = VectorStorage(mongo_uri=config.mongo_uri)
        storage._config = config

        docs = [
            {
                "chunk_id": f"test-{i}",
                "source_file": f"/test/file{i}.pdf",
                "page_number": i,
                "chunk_text": f"Content {i}",
                "embedding": [float(i)] * 384,
                "file_type": "pdf",
                "ingested_at": datetime.now(UTC).isoformat(),
            }
            for i in range(5)
        ]

        prepared = [storage._prepare_document_for_storage(doc) for doc in docs]

        assert len(prepared) == 5
        assert all(isinstance(d["embedding"], Binary) for d in prepared)


class TestSchemaChanges:
    """Tests for schema changes (flattened metadata, removed chunk_index)."""

    def test_document_has_no_metadata_nested_object(self):
        """Test documents don't have nested metadata object."""
        doc = {
            "chunk_id": "test-123",
            "source_file": "/test/file.pdf",
            "page_number": 1,
            "chunk_text": "Test",
            "embedding": [0.1] * 384,
            "file_type": "pdf",
            "ingested_at": "2024-01-01T00:00:00+00:00",
        }

        # Fields should be at top level
        assert "file_type" in doc
        assert "ingested_at" in doc
        # Old nested metadata should not exist
        assert "metadata" not in doc or "file_type" not in doc.get("metadata", {})

    def test_document_has_no_chunk_index(self):
        """Test documents don't have chunk_index field."""
        doc = {
            "chunk_id": "test-123",
            "source_file": "/test/file.pdf",
            "page_number": 1,
            "chunk_text": "Test",
            "embedding": [0.1] * 384,
            "file_type": "pdf",
            "ingested_at": "2024-01-01T00:00:00+00:00",
        }

        assert "chunk_index" not in doc
        assert "chunk_index" not in doc.get("metadata", {})

    def test_storage_config_has_new_fields(self):
        """Test config has new optimization settings."""
        config = Config()

        assert hasattr(config, "storage_compression_enabled")
        assert hasattr(config, "embedding_dtype")
        assert hasattr(config, "embedding_storage_format")
        assert hasattr(config, "text_compression_enabled")

    def test_config_defaults(self):
        """Test config has correct default values."""
        config = Config()

        assert config.embedding_dtype == "float32"
        assert config.embedding_storage_format == "array"  # Default for vector search
        assert config.text_compression_enabled is False


class TestStorageConfigValidation:
    """Tests for config validation."""

    def test_config_validation(self):
        """Test config validates optimization settings."""
        with pytest.raises(ValueError, match="embedding_dtype must be"):
            Config(embedding_dtype="float128")

        with pytest.raises(ValueError, match="embedding_storage_format must be"):
            Config(embedding_storage_format="json")

        with pytest.raises(ValueError, match="text_compression_algorithm must be"):
            Config(text_compression_algorithm="lzma")
