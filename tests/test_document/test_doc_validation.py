"""Tests for document validation logic.

This module tests validation methods in the document ingestion pipeline:
- Path security validation (traversal prevention)
- File size validation
- Core count resolution for parallel processing
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from secondbrain.document import DocumentIngestor


class TestValidateFilePath:
    """Tests for _validate_file_path security validation."""

    def test_validate_file_path_traversal(self) -> None:
        """Test path traversal attempts with '..' are rejected."""
        ingestor = DocumentIngestor()

        with pytest.raises(ValueError, match="Path traversal detected"):
            ingestor._validate_file_path(Path("../etc/passwd"))

        with pytest.raises(ValueError, match="Path traversal detected"):
            ingestor._validate_file_path(Path("data/../secret/file.txt"))

        valid_path = Path("/tmp/test/file.txt")
        ingestor._validate_file_path(valid_path)

    def test_validate_file_path_encoded(self) -> None:
        """Test URL-encoded traversal attempts are caught."""
        ingestor = DocumentIngestor()

        with pytest.raises(ValueError, match="Encoded path traversal detected"):
            ingestor._validate_file_path(Path("%2e%2e/etc/passwd"))

        with pytest.raises(ValueError, match="Encoded path traversal detected"):
            ingestor._validate_file_path(Path("%2E%2E/etc/passwd"))

        with pytest.raises(ValueError, match="Encoded path traversal detected"):
            ingestor._validate_file_path(Path("%2e./etc/passwd"))


class TestValidateFileSize:
    """Tests for _validate_file_size validation."""

    def test_validate_file_size_exceeds(self, tmp_path: Path) -> None:
        """Test files exceeding max_size limit are rejected."""
        large_file = tmp_path / "large_file.bin"
        large_file.write_bytes(b"x" * (150 * 1024 * 1024))

        ingestor = DocumentIngestor()

        with pytest.raises(ValueError, match="exceeds maximum size limit"):
            ingestor._validate_file_size(large_file)

    def test_validate_file_size_within_limit(self, tmp_path: Path) -> None:
        """Test files within limit pass validation."""
        ingestor = DocumentIngestor()

        exact_limit_file = tmp_path / "exact_limit.bin"
        exact_limit_file.write_bytes(b"x" * ingestor.max_file_size_bytes)
        ingestor._validate_file_size(exact_limit_file)

        small_file = tmp_path / "small.txt"
        small_file.write_text("Hello, world!")
        ingestor._validate_file_size(small_file)

        under_limit_file = tmp_path / "under_limit.bin"
        under_limit_file.write_bytes(b"x" * (ingestor.max_file_size_bytes - 1))
        ingestor._validate_file_size(under_limit_file)


class TestResolveCoreCount:
    """Tests for _resolve_core_count parallel processing configuration."""

    def test_resolve_core_count_auto(self) -> None:
        """Test cores=None triggers auto-detection."""
        ingestor = DocumentIngestor()

        with patch.object(os, "cpu_count", return_value=8):
            assert ingestor._resolve_core_count(None) == 8

        with patch.object(os, "cpu_count", return_value=None):
            assert ingestor._resolve_core_count(None) == 1

    def test_resolve_core_count_clamped(self) -> None:
        """Test cores > available are clamped to max."""
        ingestor = DocumentIngestor()

        with patch("secondbrain.document.get_config") as mock_config:
            mock_config.return_value.max_workers = 4

            with patch.object(os, "cpu_count", return_value=4):
                assert ingestor._resolve_core_count(8) == 8

            with patch.object(os, "cpu_count", return_value=4):
                assert ingestor._resolve_core_count(4) == 4

    def test_resolve_core_count_invalid(self) -> None:
        """Test non-positive core counts are rejected."""
        ingestor = DocumentIngestor()

        with pytest.raises(ValueError, match="cores must be positive"):
            ingestor._resolve_core_count(0)

        with pytest.raises(ValueError, match="cores must be positive"):
            ingestor._resolve_core_count(-1)

        with pytest.raises(ValueError, match="cores must be positive"):
            ingestor._resolve_core_count(-100)
