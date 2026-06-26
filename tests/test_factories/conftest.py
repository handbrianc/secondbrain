"""Pytest fixtures for factory pattern tests."""

import pytest

from tests.factories import (
    ChunkFactory,
    DocumentChunkFactory,
    DocumentMetadataFactory,
    MessageFactory,
    SessionFactory,
)


@pytest.fixture
def metadata_factory():
    """Fixture providing DocumentMetadataFactory class."""
    return DocumentMetadataFactory


@pytest.fixture
def chunk_factory():
    """Fixture providing DocumentChunkFactory class."""
    return DocumentChunkFactory


@pytest.fixture
def simple_chunk_factory():
    """Fixture providing ChunkFactory class."""
    return ChunkFactory


@pytest.fixture
def session_factory():
    """Fixture providing SessionFactory class."""
    return SessionFactory


@pytest.fixture
def message_factory():
    """Fixture providing MessageFactory class."""
    return MessageFactory
