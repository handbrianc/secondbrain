"""Audio time bounds remain attached to their source transcript segments."""

from pathlib import Path

import pytest

from secondbrain.document.chunker import (
    _merge_segments,
    chunk_segments,
    deduplicate_segments,
)
from secondbrain.document.protocols import Segment


@pytest.mark.parametrize("chunk_size", [70, 1000])
@pytest.mark.parametrize("bounds", [{}, {"t_start": 0.0}, {"t_end": 40.0}])
def test_chunks_preserve_only_present_time_bounds(
    chunk_size: int, bounds: dict[str, float]
) -> None:
    segments: list[Segment] = [
        {
            "text": "words from the same transcript segment " * 10,
            "page": 1,
            **bounds,
        }
    ]

    chunks = chunk_segments(segments, chunk_size, 10)

    assert chunks
    for chunk in chunks:
        assert {
            key: chunk[key] for key in ("t_start", "t_end") if key in chunk
        } == bounds


def test_timed_segments_keep_merge_text_stream_and_aggregate_bounds() -> None:
    segments: list[Segment] = [
        {"text": "untimed introduction", "page": 1},
        {"text": "first topic", "page": 1, "t_start": 10.0, "t_end": 20.0},
        {"text": "second topic", "page": 1, "t_start": 0.0, "t_end": 10.0},
        {"text": "untimed ending", "page": 1},
    ]

    merged = _merge_segments(segments)
    chunks = chunk_segments(segments, 100, 10)

    untimed: list[Segment] = [
        {"text": segment["text"], "page": segment["page"]} for segment in segments
    ]
    original = chunk_segments(untimed, 100, 10)
    assert [chunk["text"] for chunk in chunks] == [chunk["text"] for chunk in original]
    assert len(merged) == 1
    assert (merged[0]["t_start"], merged[0]["t_end"]) == (0.0, 20.0)
    assert all((chunk["t_start"], chunk["t_end"]) == (0.0, 20.0) for chunk in chunks)
    timed_hashes = deduplicate_segments(Path("/recordings/talk.m4a"), chunks)
    original_hashes = deduplicate_segments(Path("/recordings/talk.m4a"), original)
    assert [chunk["text_hash"] for chunk in timed_hashes] == [
        chunk["text_hash"] for chunk in original_hashes
    ]


def test_split_audio_chunks_keep_source_bounds_and_label() -> None:
    segments: list[Segment] = [
        {
            "text": "words from the same transcript segment " * 10,
            "page": 1,
            "label": "text",
            "t_start": 20.0,
            "t_end": 40.0,
        }
    ]

    chunks = chunk_segments(segments, 70, 10)

    assert len(chunks) > 1
    assert all((chunk["t_start"], chunk["t_end"]) == (20.0, 40.0) for chunk in chunks)
    assert all(chunk["chunk_role"] == "body" for chunk in chunks)


def test_deduplication_retains_time_bounds() -> None:
    chunks = deduplicate_segments(
        Path("/recordings/talk.m4a"),
        [{"text": "transcript", "page": 1, "t_start": 20.0, "t_end": 40.0}],
    )

    assert len(chunks) == 1
    assert (chunks[0]["t_start"], chunks[0]["t_end"]) == (20.0, 40.0)
