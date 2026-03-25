import uuid

import pytest

from secondbrain.domain.value_objects import (
    ChunkId,
    EmbeddingVector,
    FileSize,
    PageNumber,
    SourcePath,
)


class TestSourcePathValidation:
    def test_valid_path_accepted(self) -> None:
        path = SourcePath("/test/file.pdf")
        assert path == "/test/file.pdf"

    def test_empty_path_accepted(self) -> None:
        path = SourcePath("")
        assert path == ""

    def test_type_checking_only(self) -> None:
        path = SourcePath("test")  # type: ignore
        assert isinstance(path, str)


class TestSourcePathNormalization:
    def test_path_as_is(self) -> None:
        path = SourcePath("/test/file.pdf")
        assert path == "/test/file.pdf"

    def test_trailing_slashes_preserved(self) -> None:
        path = SourcePath("/test/dir/")
        assert path == "/test/dir/"

    def test_relative_vs_absolute(self) -> None:
        relative = SourcePath("relative/path.txt")
        absolute = SourcePath("/absolute/path.txt")
        assert relative == "relative/path.txt"
        assert absolute == "/absolute/path.txt"


class TestSourcePathEquality:
    def test_equality_operator(self) -> None:
        path1 = SourcePath("/test/file.pdf")
        path2 = SourcePath("/test/file.pdf")
        assert path1 == path2

    def test_hash_consistency(self) -> None:
        path1 = SourcePath("/test/file.pdf")
        path2 = SourcePath("/test/file.pdf")
        assert hash(path1) == hash(path2)

    def test_different_paths_not_equal(self) -> None:
        path1 = SourcePath("/test/file1.pdf")
        path2 = SourcePath("/test/file2.pdf")
        assert path1 != path2


class TestEmbeddingVectorValidation:
    def test_valid_vector_accepted(self) -> None:
        vector = EmbeddingVector([0.1, 0.2, 0.3])
        assert vector == [0.1, 0.2, 0.3]

    def test_empty_vector_accepted(self) -> None:
        vector = EmbeddingVector([])
        assert vector == []

    def test_type_checking_only(self) -> None:
        vector = EmbeddingVector([0.1])  # type: ignore
        assert isinstance(vector, list)


class TestEmbeddingVectorProperties:
    def test_vector_as_list(self) -> None:
        vector = EmbeddingVector([0.1, 0.2, 0.3])
        assert isinstance(vector, list)
        assert len(vector) == 3

    def test_vector_mutable(self) -> None:
        vector = EmbeddingVector([0.1, 0.2, 0.3])
        vector[0] = 0.5
        assert vector[0] == 0.5

    def test_vector_equality(self) -> None:
        vector1 = EmbeddingVector([0.1, 0.2, 0.3])
        vector2 = EmbeddingVector([0.1, 0.2, 0.3])
        assert vector1 == vector2


class TestChunkIdGeneration:
    def test_unique_id_generation(self) -> None:
        chunk_id1 = ChunkId(str(uuid.uuid4()))
        chunk_id2 = ChunkId(str(uuid.uuid4()))
        assert chunk_id1 != chunk_id2

    def test_format_consistency(self) -> None:
        chunk_id = ChunkId(str(uuid.uuid4()))
        assert len(chunk_id) == 36
        assert chunk_id.count("-") == 4

    def test_uuid_based_generation(self) -> None:
        test_uuid = uuid.uuid4()
        chunk_id = ChunkId(str(test_uuid))
        assert chunk_id == str(test_uuid)


class TestChunkIdValidation:
    def test_valid_id_format(self) -> None:
        chunk_id = ChunkId("test-id-123")
        assert isinstance(chunk_id, str)
        assert len(chunk_id) > 0

    def test_invalid_format_accepted(self) -> None:
        chunk_id = ChunkId("invalid-id-format")
        assert chunk_id == "invalid-id-format"

    def test_parsing_logic(self) -> None:
        test_uuid = uuid.uuid4()
        chunk_id = ChunkId(str(test_uuid))
        parsed = uuid.UUID(chunk_id)
        assert parsed == test_uuid


class TestFileSize:
    def test_valid_size(self) -> None:
        size = FileSize(1024)
        assert size.bytes == 1024

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            FileSize(-100)

    def test_kilobytes_property(self) -> None:
        size = FileSize(2048)
        assert size.kilobytes == 2.0

    def test_megabytes_property(self) -> None:
        size = FileSize(1048576)
        assert size.megabytes == 1.0

    def test_string_representation_mb(self) -> None:
        size = FileSize(2097152)
        assert str(size) == "2.00 MB"

    def test_string_representation_kb(self) -> None:
        size = FileSize(2048)
        assert str(size) == "2.00 KB"

    def test_string_representation_bytes(self) -> None:
        size = FileSize(512)
        assert str(size) == "512 B"

    def test_zero_bytes(self) -> None:
        size = FileSize(0)
        assert size.bytes == 0
        assert str(size) == "0 B"


class TestPageNumber:
    def test_valid_page_number(self) -> None:
        page = PageNumber(1)
        assert page.number == 1

    def test_zero_page_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            PageNumber(0)

    def test_negative_page_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            PageNumber(-1)

    def test_int_conversion(self) -> None:
        page = PageNumber(5)
        assert int(page) == 5

    def test_multi_digit_page(self) -> None:
        page = PageNumber(100)
        assert page.number == 100

    def test_frozen_immutability(self) -> None:
        page = PageNumber(1)
        with pytest.raises(Exception):
            page.number = 2  # type: ignore
