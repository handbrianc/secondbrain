"""Pairing tests: implausible heading labels bind to body text (D1).

fix-chunk-heading-context: a ``section_header`` segment failing
:func:`~secondbrain.document.chunker.is_plausible_heading` is run-in body
text — it joins the accumulation like body text instead of flushing
standalone, and its heading label is dropped on join so the merged chunk
carries no heading element type. Plausible headings and every other
structural/table label keep the standalone flush, and label-less streams
stay byte-identical.
"""

from __future__ import annotations

import pytest

from secondbrain.document import Segment
from secondbrain.document.chunker import chunk_segments

pytestmark = pytest.mark.unit

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
CHRONY_BODY = (
    "The chrony daemon keeps the system clock synchronized against the "
    "configured sources. Restart it after editing /etc/chrony/chrony.conf "
    "so the new servers take effect, and verify convergence with "
    "chronyc tracking before trusting the cluster time."
)


def _seg(text: str, page: int = 1, label: str | None = None) -> Segment:
    segment: Segment = {"text": text, "page": page}
    if label is not None:
        segment["label"] = label
    return segment


def test_implausible_label_joins_following_body() -> None:
    """A run-in label binds to the text it introduces — one body chunk.

    BODY_A exceeds MIN_SEGMENT_SIZE, so the demoted label starts a fresh
    accumulation that CHRONY_BODY then joins; the merged chunk classifies
    ``body`` (a leaked heading label would force ``heading`` instead).
    """
    segments = [
        _seg(BODY_A, page=1),
        _seg("Restart chrony:", page=2, label="section_header"),
        _seg(CHRONY_BODY, page=3),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    joined = [c for c in chunks if "Restart chrony:" in c["text"]]
    assert len(joined) == 1
    assert joined[0]["text"].startswith("Restart chrony: ")
    assert CHRONY_BODY in joined[0]["text"]
    assert joined[0]["chunk_role"] == "body"
    assert joined[0]["element_type"] == "body"
    assert all(c["element_type"] != "heading" for c in chunks)


def test_plausible_label_still_flushes_standalone_byte_identical() -> None:
    """A passing label keeps the standalone flush: own chunk, exact text."""
    segments = [
        _seg(BODY_A, page=1),
        _seg("FSYNCS/SECOND", page=2, label="section_header"),
        _seg(BODY_C, page=3),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    headings = [c for c in chunks if c["text"] == "FSYNCS/SECOND"]
    assert len(headings) == 1
    assert headings[0]["chunk_role"] == "heading"
    assert headings[0]["element_type"] == "heading"
    assert headings[0]["page"] == 2


def test_unlabeled_stream_byte_identical() -> None:
    """A label-less stream chunks exactly as before the change."""
    scrub = (
        "Scrub runs weekly on every node and reports drift into the cluster "
        "log. Maintenance windows are announced one week ahead, and the "
        "storage health dashboard flags any node whose rebalancing falls "
        "behind the schedule set by the administrators."
    )
    segments = [
        _seg("Storage Maintenance", page=1),
        _seg(scrub, page=2),
        _seg("Z" * 210, page=3),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert [(c["text"], c["page"]) for c in chunks] == [
        ("Storage Maintenance " + scrub, 2),
        ("Z" * 210, 3),
    ]


def test_other_structural_labels_keep_standalone_flush() -> None:
    """Only section_header is gated: every other labeled text flushes alone.

    Even implausible-shaped text keeps its label's standalone flush when the
    label is anything but ``section_header`` — page_footer, document_index,
    caption, and the "title" label (which also maps to ``heading`` but is
    not gated, per design D1's "apply only to the section_header label").
    """
    segments = [
        _seg(BODY_A, page=1),
        _seg("Restart chrony:", page=2, label="page_footer"),
        _seg("3.9 Data Processing and Analytics", page=3, label="document_index"),
        _seg("Figure 3: Edge inference topology", page=4, label="caption"),
        _seg("Restart chrony:", page=5, label="title"),
        _seg("| a | b |", page=6, label="table"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    standalone = {
        ("Restart chrony:", "navigation"),  # page_footer, page 2
        ("3.9 Data Processing and Analytics", "toc_entry"),
        ("Figure 3: Edge inference topology", "caption"),
        ("Restart chrony:", "heading"),  # title label, page 5
        ("| a | b |", "body"),  # table label maps to body, still standalone
    }
    assert standalone <= {(c["text"], c["chunk_role"]) for c in chunks}


def test_demoted_join_keeps_the_earlier_label() -> None:
    """A demoted join after a labeled start keeps that start's label.

    Mirrors the label-less join branch: the join never overwrites
    ``current_label``, so the body-labeled start still decides the chunk
    role after the implausible heading text lands inside it.
    """
    segments = [
        _seg("alpha beta", page=1, label="text"),
        _seg("Restart chrony:", page=1, label="section_header"),
        _seg("gamma delta", page=1, label="list_item"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert len(chunks) == 1
    assert chunks[0]["text"] == "alpha beta Restart chrony: gamma delta"
    assert chunks[0]["chunk_role"] == "body"


def test_trailing_demoted_label_lands_as_body() -> None:
    """A demoted label with nothing after it is body text, not a heading.

    The text stream is unchanged (two segments, same texts as the old
    standalone flush) — only the classification becomes truthful.
    """
    segments = [
        _seg(BODY_A, page=1),
        _seg("Restart chrony:", page=2, label="section_header"),
    ]

    chunks = chunk_segments(segments, CHUNK_SIZE, OVERLAP)

    assert [c["text"] for c in chunks] == [BODY_A, "Restart chrony:"]
    assert chunks[-1]["element_type"] == "body"
    assert all(c["element_type"] != "heading" for c in chunks)
