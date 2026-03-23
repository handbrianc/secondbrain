"""Tests for CLI display module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from secondbrain.cli.display import (
    display_health_status,
    display_list_results,
    display_search_results,
    display_status,
)
from secondbrain.logging import HealthStatus
from secondbrain.types import ChunkInfo


class TestDisplaySearchResults:
    """Tests for display_search_results function."""

    def test_display_search_results(self, console_mock: MagicMock) -> None:
        """Test search results display formatting with Rich table structure."""
        results = [
            {
                "source_file": "test.pdf",
                "chunk_text": "This is a test chunk with some content",
                "score": 0.95,
                "page_number": 1,
            },
            {
                "source_file": "test2.pdf",
                "chunk_text": "Another chunk with different content",
                "score": 0.85,
                "page_number": 2,
            },
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results(results, "table")

            # Verify console.print was called for each result
            assert console_mock.print.call_count == 2

            # Verify score formatting in output
            output_str = str(console_mock.print.call_args_list[0])
            assert "0.95" in output_str or "0.9500" in output_str

    def test_display_search_results_empty(self, console_mock: MagicMock) -> None:
        """Test search results display with empty results."""
        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results([], "table")

            # Verify "No results found" message
            console_mock.print.assert_called_once_with(
                "[yellow]No results found[/yellow]"
            )

    def test_display_search_results_multiple(self, console_mock: MagicMock) -> None:
        """Test search results display with multiple results."""
        results = [
            {
                "source_file": f"doc{i}.pdf",
                "chunk_text": f"Content {i}",
                "score": 0.95 - i * 0.02,
                "page_number": i,
            }
            for i in range(5)
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results(results, "table")

            assert console_mock.print.call_count == 5

    def test_display_search_results_score_formatting(
        self, console_mock: MagicMock
    ) -> None:
        """Test search results score formatting."""
        results = [
            {
                "source_file": "test.pdf",
                "chunk_text": "Test content",
                "score": 0.87654321,
                "page_number": 1,
            }
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results(results, "table")

            # Verify score is formatted to 4 decimal places
            output_str = str(console_mock.print.call_args_list[0])
            assert "0.8765" in output_str

    def test_display_search_results_json_format(self, console_mock: MagicMock) -> None:
        results = [
            {
                "source_file": "test.pdf",
                "chunk_text": "Test content",
                "score": 0.95,
                "page_number": 1,
            }
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results(results, "json")

            console_mock.print.assert_called_once()
            json_output = console_mock.print.call_args[0][0]
            parsed = json.loads(json_output)
            assert parsed == results

    def test_display_search_results_below_threshold(
        self, console_mock: MagicMock
    ) -> None:
        results = [
            {
                "source_file": "test.pdf",
                "chunk_text": "Test content",
                "score": 0.5,
                "page_number": 1,
            },
            {
                "source_file": "test2.pdf",
                "chunk_text": "More content",
                "score": 0.6,
                "page_number": 2,
            },
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_search_results(results, "table", min_score=0.78)

            assert console_mock.print.call_count == 2
            output_str = str(console_mock.print.call_args_list)
            assert "No relevant results found" in output_str
            assert "Try different keywords" in output_str


class TestDisplayListResults:
    """Tests for display_list_results function."""

    def test_display_list_results(self, console_mock: MagicMock) -> None:
        """Test document list display with table formatting."""
        results: list[ChunkInfo] = [
            {
                "chunk_id": "abc123def456ghi789jkl012mno345pqr678stu901vwx234yz",
                "source_file": "document1.pdf",
                "page_number": 1,
            },
            {
                "chunk_id": "xyz987wvu654tsr321qpo098nml765kji432hgf210edc098ba",
                "source_file": "document2.pdf",
                "page_number": 2,
            },
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_list_results(results)

            assert console_mock.print.call_count >= 1
            table_arg = console_mock.print.call_args_list[-1][0][0]
            assert table_arg.title == "Ingested Documents"

    def test_display_list_results_no_documents(self, console_mock: MagicMock) -> None:
        """Test document list display with no documents."""
        with patch("secondbrain.cli.display.console", console_mock):
            display_list_results([])

            # Verify "No results found" message
            console_mock.print.assert_called_once_with(
                "[yellow]No results found[/yellow]"
            )

    def test_display_list_results_pagination_indicators(
        self, console_mock: MagicMock
    ) -> None:
        """Test document list display with pagination indicators."""
        results: list[ChunkInfo] = [
            {
                "chunk_id": f"chunk{i:050d}",
                "source_file": f"file{i}.pdf",
                "page_number": i,
            }
            for i in range(10)
        ]

        with patch("secondbrain.cli.display.console", console_mock):
            display_list_results(results)

            assert console_mock.print.call_count == 1
            table_arg = console_mock.print.call_args_list[0][0][0]
            assert len(table_arg.rows) == 10


class TestDisplayStatus:
    """Tests for display_status function."""

    def test_display_status(self, console_mock: MagicMock) -> None:
        """Test status display formatting with statistics shown correctly."""
        stats = {
            "total_chunks": 100,
            "unique_sources": 5,
            "database": "test_db",
            "collection": "test_collection",
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_status(stats)

            assert console_mock.print.call_count == 5
            output_str = str(console_mock.print.call_args_list)
            assert "Database Status" in output_str
            assert "100" in output_str
            assert "5" in output_str
            assert "test_db" in output_str
            assert "test_collection" in output_str

    def test_display_status_zero_documents(self, console_mock: MagicMock) -> None:
        """Test status display with zero documents."""
        stats = {
            "total_chunks": 0,
            "unique_sources": 0,
            "database": "empty_db",
            "collection": "empty_collection",
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_status(stats)

            # Verify zero values are displayed correctly
            output_str = str(console_mock.print.call_args_list)
            assert "0" in output_str
            assert "empty_db" in output_str

    def test_display_status_large_dataset(self, console_mock: MagicMock) -> None:
        """Test status display with large dataset."""
        stats = {
            "total_chunks": 1000000,
            "unique_sources": 500,
            "database": "large_db",
            "collection": "large_collection",
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_status(stats)

            # Verify large numbers are displayed
            output_str = str(console_mock.print.call_args_list)
            assert "1000000" in output_str
            assert "500" in output_str


class TestDisplayHealthStatus:
    """Tests for display_health_status function."""

    def test_display_health_status(self, console_mock: MagicMock) -> None:
        """Test health status display with service status indicators."""
        status: HealthStatus = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 1000.0,
            "services": {"mongodb": True, "sentence-transformers": True},
            "check_duration_seconds": 0.123456,
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_health_status(status)

            # Verify health status displayed
            output_str = str(console_mock.print.call_args_list)
            assert "HEALTHY" in output_str
            assert "Services" in output_str
            assert "mongodb" in output_str

    def test_display_health_status_all_healthy(self, console_mock: MagicMock) -> None:
        """Test health status display with all services healthy."""
        status: HealthStatus = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 5000.0,
            "services": {"mongodb": True, "sentence-transformers": True, "cache": True},
            "check_duration_seconds": 0.05,
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_health_status(status)

            # Verify all services shown as healthy
            output_str = str(console_mock.print.call_args_list)
            assert output_str.count("green") >= 3  # At least 3 green checkmarks

    def test_display_health_status_some_unhealthy(
        self, console_mock: MagicMock
    ) -> None:
        """Test health status display with some services unhealthy."""
        status: HealthStatus = {
            "status": "degraded",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": 5000.0,
            "services": {
                "mongodb": True,
                "sentence-transformers": False,
                "cache": False,
            },
            "check_duration_seconds": 0.2,
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_health_status(status)

            # Verify degraded status and red indicators
            output_str = str(console_mock.print.call_args_list)
            assert "DEGRADED" in output_str
            assert "red" in output_str  # At least one red indicator

    def test_display_health_status_json_format(self, console_mock: MagicMock) -> None:
        """Test health status JSON output format."""
        # Note: The current implementation doesn't support JSON format for health status
        # This test verifies the text format behavior
        status: HealthStatus = {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "uptime": None,
            "services": {"mongodb": True},
            "check_duration_seconds": 0.1,
        }

        with patch("secondbrain.cli.display.console", console_mock):
            display_health_status(status)

            # Verify timestamp is displayed
            output_str = str(console_mock.print.call_args_list)
            assert "2024-01-01" in output_str


@pytest.fixture
def console_mock() -> MagicMock:
    """Create a mock console for testing."""
    return MagicMock(spec=Console)
