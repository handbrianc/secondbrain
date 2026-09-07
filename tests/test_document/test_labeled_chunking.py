"""Tests for label-aware merge/assembly behavior in chunk_segments."""

from secondbrain.document import Segment
from secondbrain.document.chunker import chunk_segments

CHUNK_SIZE = 4096
OVERLAP = 200

BODY_A = (
    "The Internet of Things connects physical devices to cloud platforms, "
    "enabling telemetry collection at scale. Edge nodes buffer measurements "
    "during connectivity loss and forward them once the link recovers. "
    "This chapter examines the architectural patterns behind such systems "
    "and the trade-offs engineers face when deploying them in production "
    "environments with unreliable networks."
)
BODY_C = (
    "Fog computing pushes processing closer to the sensors that generate "
    "data. Latency sensitive workloads such as anomaly detection benefit "
    "from local inference, while bulk analytics remain in the cloud. "
    "Deployment topology therefore becomes a first class design decision "
    "rather than an implementation detail discovered late in the project."
)


def _seg(text: str, page: int = 1, label: str | None = None) -> Segment:
    segment: Segment = {"text": text, "page": page}
    if label is not None:
        segment["label"] = label
    return segment


def test_section_header_starts_standalone_heading_chunk() -> None:
    """A labeled heading must NOT be appended into the preceding body chunk."""
    segments = [
        _seg(BODY_A, page=1),
        _seg("Introduction", page=2, label="section_header"),
        _seg(BODY_C, page=3),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert len(chunks) == 3
    assert chunks[0]["chunk_role"] == "navigation"
    assert "Introduction" not in chunks[0]["text"]
    assert chunks[1]["text"] == "Introduction"
    assert chunks[1]["chunk_role"] == "heading"
    assert chunks[2]["chunk_role"] == "body"


def test_document_index_gets_toc_entry_role() -> None:
    segments = [
        _seg(BODY_A, page=1),
        _seg("3.9 Data Processing and Analytics", page=2, label="document_index"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert chunks[-1]["chunk_role"] == "toc_entry"
    assert chunks[-1]["text"] == "3.9 Data Processing and Analytics"


def test_page_footer_gets_navigation_role() -> None:
    """Label wins over statistics: '12' alone would classify as a heading."""
    segments = [
        _seg(BODY_A, page=1),
        _seg(BODY_C, page=1),
        _seg("12", page=1, label="page_footer"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert chunks[-1]["chunk_role"] == "navigation"


def test_caption_gets_caption_role() -> None:
    """Label wins over statistics: a short caption line would look like a title."""
    segments = [
        _seg(BODY_A, page=1),
        _seg("Figure 3: Edge inference topology", page=1, label="caption"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert chunks[-1]["chunk_role"] == "caption"


def test_labeled_body_text_merges_like_label_less() -> None:
    """body-labeled short segments follow the same merge rules as unlabeled."""
    labeled = chunk_segments(
        [
            _seg("alpha beta", page=1, label="text"),
            _seg(BODY_A, page=1),
        ],
        CHUNK_SIZE,
        OVERLAP,
    )
    unlabeled = chunk_segments(
        [
            _seg("alpha beta", page=1),
            _seg(BODY_A, page=1),
        ],
        CHUNK_SIZE,
        OVERLAP,
    )

    assert len(labeled) == len(unlabeled) == 1
    assert labeled[0]["text"] == unlabeled[0]["text"]
    assert "alpha beta" in labeled[0]["text"]


def test_leading_label_decides_merged_chunk_role() -> None:
    """When body-labeled segments merge, the first segment's label decides.

    Statistics alone would classify the short merged text as a heading; the
    leading body label wins instead.
    """
    segments = [
        _seg("alpha beta", page=1, label="text"),
        _seg("gamma delta", page=1, label="list_item"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert len(chunks) == 1
    assert chunks[0]["chunk_role"] == "body"
    assert chunks[0]["text"] == "alpha beta gamma delta"


def test_chunks_carry_matching_chunk_role_and_element_type() -> None:
    segments = [
        _seg(BODY_A, page=1),
        _seg("Chapter Overview", page=2, label="section_header"),
        _seg("3.9 Data Processing and Analytics", page=2, label="document_index"),
        _seg("Figure 3: Edge inference topology", page=3, label="caption"),
        _seg(BODY_C, page=3, label="text"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert chunks
    for chunk in chunks:
        assert chunk["element_type"] == chunk["chunk_role"]


def test_unlabeled_segments_unchanged() -> None:
    """Label-less inputs keep the pre-migration burying/merge behavior."""
    segments = [
        _seg(BODY_A, page=1),
        _seg("Introduction", page=1),
        _seg(BODY_C, page=1),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert len(chunks) == 2
    assert "Introduction" in chunks[0]["text"]
    assert chunks[0]["chunk_role"] == "navigation"
