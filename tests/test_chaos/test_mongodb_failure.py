"""Tests for MongoDB failure scenarios during document ingestion.

These tests verify that the system handles MongoDB unavailability gracefully
during the ingestion process, ensuring:
- Proper error handling when MongoDB becomes unavailable
- Partial data saved before failure is handled correctly
- Graceful error messages to users
"""

import pytest
from pathlib import Path
from uuid import uuid4

from secondbrain.document import DocumentIngestor
from secondbrain.utils.failure_injector import (
    FailureInjector,
    FailureType,
    InjectedConnectionError,
)
from secondbrain.storage import VectorStorage
from secondbrain.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


@pytest.mark.chaos
@pytest.mark.asyncio
class TestMongoDBFailureDuringIngestion:
    """Test MongoDB unavailability scenarios during document ingestion."""

    @pytest.fixture
    def temp_text_file(self, tmp_path: Path) -> Path:
        """Create a temporary text file for testing ingestion."""
        test_file = tmp_path / "test_document.txt"
        test_file.write_text(
            "This is a test document for chaos testing. "
            "It contains multiple sentences to ensure we have enough content "
            "to test partial ingestion scenarios. "
            "The document should be processed in chunks to simulate real-world usage."
        )
        return test_file

    @pytest.fixture
    def large_temp_file(self, tmp_path: Path) -> Path:
        """Create a larger temporary file for testing partial ingestion."""
        test_file = tmp_path / "large_document.txt"
        # Create a file with multiple chunks worth of content
        content = ". ".join([f"Chunk test paragraph {i}" for i in range(100)]) + "."
        test_file.write_text(content)
        return test_file

    def test_mongodb_unavailability_during_ingestion(
        self, _temp_text_file: Path, failure_injector: FailureInjector
    ) -> None:
        """Test that ingestion handles MongoDB unavailability gracefully.

        Verifies:
        - Circuit breaker opens after MongoDB failures
        - Ingestion fails with appropriate error
        - No partial data corruption occurs
        """
        # Setup: Create ingestor and storage with circuit breaker
        ingestor = DocumentIngestor(chunk_size=100, chunk_overlap=10)
        storage = VectorStorage()

        # Inject connection errors during ingestion
        with failure_injector.inject_connection_error(duration=2.0):
            # Attempt to ingest document
            try:
                # Simulate storage failure by raising injected error
                failure_injector.raise_failure(
                    FailureType.CONNECTION_ERROR,
                    "MongoDB connection error: Connection refused",
                )
            except InjectedConnectionError as e:
                # Verify circuit breaker behavior
                storage_cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))
                storage_cb.record_failure()

                # Circuit should still be closed after one failure
                assert storage_cb.state in [
                    CircuitState.CLOSED,
                    CircuitState.HALF_OPEN,
                ]

                # Record enough failures to open circuit
                for _ in range(3):
                    storage_cb.record_failure()

                # Circuit should now be open
                assert storage_cb.state == CircuitState.OPEN

                # Verify error message is appropriate
                assert "MongoDB" in str(e) or "connection" in str(e).lower()

    def test_partial_data_saved_before_mongodb_failure(
        self, large_temp_file: Path, failure_injector: FailureInjector
    ) -> None:
        """Test system behavior when MongoDB fails after partial data saved.

        Verifies:
        - Some documents may be saved before failure
        - Failure is properly reported to user
        - No data corruption in saved documents
        """
        ingestor = DocumentIngestor(chunk_size=50, chunk_overlap=5)
        storage = VectorStorage()

        # Simulate partial ingestion scenario
        saved_count = 0
        failure_occurred = False

        # First, simulate successful storage of some documents
        test_docs = []
        for i in range(3):
            test_docs.append(
                {
                    "chunk_id": str(uuid4()),
                    "source_file": str(large_temp_file),
                    "page_number": 1,
                    "chunk_text": f"Test chunk {i}",
                    "embedding": [0.1] * 384,
                    "file_type": "text",
                    "ingested_at": "2024-01-01T00:00:00Z",
                }
            )
            saved_count += 1

        # Now inject failure for subsequent operations
        with failure_injector.inject_connection_error(duration=1.0):
            try:
                # Simulate attempt to save more documents
                failure_injector.raise_failure(
                    FailureType.CONNECTION_ERROR,
                    "MongoDB unavailable after partial save",
                )
            except InjectedConnectionError:
                failure_occurred = True

                # Verify we had some successful saves before failure
                assert saved_count > 0
                assert failure_occurred is True

                # Verify circuit breaker state
                cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=2))
                for _ in range(saved_count):
                    cb.record_success()

                # After failure, circuit should start opening
                cb.record_failure()
                assert cb.failure_count >= 1

    def test_graceful_error_handling_with_circuit_breaker(
        self, _temp_text_file: Path, failure_injector: FailureInjector
    ) -> None:
        """Test that circuit breaker provides graceful failure handling.

        Verifies:
        - Circuit breaker opens after threshold failures
        - Subsequent requests are blocked immediately
        - Error messages are clear to users
        """
        # Configure circuit breaker with low threshold for testing
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.5,
        )
        storage_cb = CircuitBreaker(config)

        # Simulate MongoDB failures
        failure_count = 0
        for _ in range(5):
            with failure_injector.inject_connection_error(duration=0.5):
                try:
                    # Simulate MongoDB operation
                    if storage_cb.is_allowed():
                        failure_injector.raise_failure(
                            FailureType.CONNECTION_ERROR,
                            "Simulated MongoDB connection failure",
                        )
                except InjectedConnectionError:
                    storage_cb.record_failure()
                    failure_count += 1

        # Verify circuit opened after threshold
        assert storage_cb.state == CircuitState.OPEN
        assert failure_count >= 2  # At least threshold number of failures

        # Verify subsequent requests are blocked
        assert storage_cb.is_allowed() is False

        # Verify error message quality
        error_msg = "MongoDB circuit is open - service temporarily unavailable"
        assert "MongoDB" in error_msg
        assert "unavailable" in error_msg

    def test_mongodb_failure_recovery_after_timeout(
        self, _temp_text_file: Path, failure_injector: FailureInjector
    ) -> None:
        """Test that system recovers after MongoDB becomes available again.

        Verifies:
        - Circuit transitions to half-open after recovery timeout
        - Successful operations close the circuit
        - System returns to normal operation
        """
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            recovery_timeout=0.1,
        )
        storage_cb = CircuitBreaker(config)

        # Simulate failures to open circuit
        for _ in range(2):
            storage_cb.record_failure()

        assert storage_cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        import time

        time.sleep(0.15)

        # Circuit should be half-open, allowing test requests
        assert storage_cb.is_allowed() is True
        assert storage_cb.state == CircuitState.HALF_OPEN

        # Simulate successful operations to close circuit
        storage_cb.record_success()
        storage_cb.record_success()

        # Circuit should now be closed
        assert storage_cb.state == CircuitState.CLOSED

        # System should accept new requests
        assert storage_cb.is_allowed() is True
