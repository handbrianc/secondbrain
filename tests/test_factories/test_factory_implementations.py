"""Tests for factory pattern implementations."""

from datetime import datetime

from secondbrain.config import config
from secondbrain.domain.value_objects import ChunkId, EmbeddingVector


def _expected_dims() -> int:
    """Return the embedding dimensions from config."""
    return config().embedding_dimensions


class TestDocumentMetadataFactory:
    """Tests for DocumentMetadataFactory."""

    def test_factory_creates_valid_metadata(self, metadata_factory):
        """Test that factory creates valid DocumentMetadata."""
        metadata = metadata_factory.create()

        assert metadata.source_file is not None
        assert metadata.file_type is not None
        assert isinstance(metadata.ingested_at, datetime)
        assert metadata.chunk_count >= 1
        assert metadata.total_chars >= 100

    def test_factory_allows_override(self, metadata_factory):
        """Test that factory allows attribute override."""
        metadata = metadata_factory.create(
            file_type="pdf",
            chunk_count=5,
        )

        assert metadata.file_type == "pdf"
        assert metadata.chunk_count == 5

    def test_factory_batch_creation(self, metadata_factory):
        """Test batch creation of metadata."""
        metadata_list = metadata_factory.create_batch(5)

        assert len(metadata_list) == 5
        # Each should have unique values
        assert len(set(m.ingested_at for m in metadata_list)) == 5


class TestDocumentChunkFactory:
    """Tests for DocumentChunkFactory."""

    def test_factory_creates_valid_chunk(self, chunk_factory):
        """Test that factory creates valid DocumentChunk."""
        chunk = chunk_factory.create()

        assert chunk.chunk_id is not None
        assert chunk.text is not None and len(chunk.text) > 0
        assert chunk.metadata is not None
        assert chunk.embedding is not None
        assert len(chunk.embedding) == _expected_dims()
        assert all(v == 0.1 for v in chunk.embedding)

    def test_factory_with_custom_id(self, chunk_factory):
        """Test factory with custom chunk ID."""
        chunk = chunk_factory.create(chunk_id=ChunkId("custom-id-123"))

        assert chunk.chunk_id == "custom-id-123"

    def test_factory_with_custom_text(self, chunk_factory):
        """Test factory with custom text content."""
        chunk = chunk_factory.create(text="Custom test content")

        assert chunk.text == "Custom test content"

    def test_factory_with_embedding(self, chunk_factory):
        """Test factory with custom embedding."""
        custom_embedding = EmbeddingVector([0.1] * _expected_dims())
        chunk = chunk_factory.create(embedding=custom_embedding)

        assert chunk.embedding == custom_embedding

    def test_factory_page_number(self, chunk_factory):
        """Test factory with page number."""
        chunk = chunk_factory.create(page_number=5)

        assert chunk.page_number == 5

    def test_factory_batch_creation(self, chunk_factory):
        """Test batch creation of chunks."""
        chunks = chunk_factory.create_batch(10)

        assert len(chunks) == 10
        # Each should have unique IDs
        assert len(set(c.chunk_id for c in chunks)) == 10


class TestChunkFactory:
    """Tests for ChunkFactory (alias for DocumentChunkFactory)."""

    def test_chunk_factory_default_embedding(self, chunk_factory):
        """Test that ChunkFactory creates chunks with default embedding."""
        chunk = chunk_factory.create()
        assert chunk.embedding is not None
        assert len(chunk.embedding) == _expected_dims()
        assert all(v == 0.1 for v in chunk.embedding)

    def test_chunk_factory_with_document_id(self, chunk_factory):
        """Test ChunkFactory creates chunk with metadata."""
        chunk = chunk_factory.create()

        assert chunk.chunk_id is not None
        assert chunk.text is not None
        assert chunk.metadata is not None


class TestMessageFactory:
    """Tests for MessageFactory."""

    def test_factory_creates_valid_message(self, message_factory):
        """Test that factory creates valid message dict."""
        message = message_factory.create()

        assert "role" in message
        assert "content" in message
        assert "timestamp" in message
        assert message["role"] in ["user", "assistant", "system"]

    def test_factory_with_custom_role(self, message_factory):
        """Test factory with custom role."""
        message = message_factory.create(role="user")

        assert message["role"] == "user"

    def test_factory_with_custom_content(self, message_factory):
        """Test factory with custom content."""
        message = message_factory.create(content="Hello, world!")

        assert message["content"] == "Hello, world!"

    def test_factory_batch_creation(self, message_factory):
        """Test batch creation of messages."""
        messages = message_factory.create_batch(5)

        assert len(messages) == 5
        assert all("role" in m and "content" in m for m in messages)


class TestSessionFactory:
    """Tests for SessionFactory."""

    def test_factory_creates_valid_session(self, session_factory):
        """Test that factory creates valid session dict."""
        session = session_factory.create()

        assert "session_id" in session
        assert "messages" in session
        assert "created_at" in session
        assert "updated_at" in session
        assert len(session["messages"]) >= 1

    def test_factory_with_custom_session_id(self, session_factory):
        """Test factory with custom session ID."""
        session = session_factory.create(session_id="custom-session-123")

        assert session["session_id"] == "custom-session-123"

    def test_factory_with_custom_messages(self, session_factory):
        """Test factory with custom messages."""
        custom_messages = [
            {"role": "user", "content": "Hello", "timestamp": "2024-01-01T00:00:00"},
            {"role": "assistant", "content": "Hi!", "timestamp": "2024-01-01T00:00:01"},
        ]
        session = session_factory.create(messages=custom_messages)

        assert len(session["messages"]) == 2
        assert session["messages"][0]["role"] == "user"

    def test_factory_batch_creation(self, session_factory):
        """Test batch creation of sessions."""
        sessions = session_factory.create_batch(3)

        assert len(sessions) == 3
        # Each should have unique session IDs
        assert len(set(s["session_id"] for s in sessions)) == 3


class TestFactoryIntegration:
    """Integration tests combining multiple factories."""

    def test_chunk_with_metadata_factory(self, chunk_factory, metadata_factory):
        """Test creating chunk with custom metadata from factory."""
        custom_metadata = metadata_factory.create(file_type="pdf")
        chunk = chunk_factory.create(metadata=custom_metadata)

        assert chunk.metadata.file_type == "pdf"
        assert chunk.chunk_id is not None

    def test_session_with_multiple_messages(self, session_factory, message_factory):
        """Test creating session with multiple factory messages."""
        messages = message_factory.create_batch(10)
        session = session_factory.create(messages=messages)

        assert len(session["messages"]) == 10
        assert all(m["role"] in ["user", "assistant", "system"] for m in messages)

    def test_document_chunk_pipeline(self, chunk_factory):
        """Test complete document chunk creation pipeline."""
        # Create chunk with factory
        chunk = chunk_factory.create(
            page_number=1,
            text="Test content for pipeline",
        )

        # Verify all properties
        assert chunk.chunk_id is not None
        assert chunk.text == "Test content for pipeline"
        assert chunk.page_number == 1
        assert chunk.metadata is not None
        assert chunk.metadata.source_file is not None
        assert chunk.metadata.file_type is not None
