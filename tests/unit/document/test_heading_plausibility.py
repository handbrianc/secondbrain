"""Unit tests for the heading plausibility gate (fix-chunk-heading-context D1).

:func:`is_plausible_heading` is the single predicate both structure capture
(:func:`~secondbrain.document.structure_capture.capture_docling_headings`)
and chunk assembly (``chunker._merge_segments``) consult: a docling
``section_header`` whose text passes it may become a tree node / standalone
heading chunk; text failing it is run-in body noise — a trailing-colon
label, a sentence fragment, or a "command - description" synopsis line.
"""

from __future__ import annotations

import pytest

from secondbrain.document import is_plausible_heading as reexported_predicate
from secondbrain.document.chunker import is_plausible_heading

pytestmark = pytest.mark.unit


def test_package_reexports_the_predicate() -> None:
    """secondbrain.document re-exports the chunker predicate like its peers."""
    assert reexported_predicate is is_plausible_heading


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Numbered section prefixes always pass — whatever else looks off.
        ("19.2 pveperf", True),
        ("11.18 Configuring the Autostart Service", True),
        ("5.2.3 Details", True),
        ("19.2 pveperf benchmark run:", True),  # numbered beats trailing ":"
        # Real PVE headings the gate must keep.
        ("GENERAL BTRFS ADVANTAGES", True),
        ("FSYNCS/SECOND", True),
        ("Introduction", True),
        ("Chapter 5 — Installing", True),  # em dash mid-title is not synopsis
        ("Full-Stack Deployment", True),  # hyphenated words are not " - "
        ("Storage nodes replicate writes across three racks", True),
        # Run-in labels and fragments (the defect this gate fixes).
        ("Restart chrony:", False),
        ("By running:", False),
        ("pvesubscription - Subscription Management", False),
        ("qm guest exec - Run command via guest agent", False),
        # Trailing sentence punctuation rejects.
        ("This is a sentence.", False),
        ("Comma ending,", False),
        ("Semicolon ending;", False),
        ("Em dash ending—", False),
        # Length cap: 120+ characters are prose, not a heading.
        ("Filler prose word " * 7 + "tail", False),  # 130 chars, no punct
    ],
)
def test_predicate_cases(text: str, expected: bool) -> None:
    assert is_plausible_heading(text) is expected


@pytest.mark.parametrize("length", [119, 120])
def test_length_threshold_boundary(length: int) -> None:
    """The cap is exclusive: 119 characters pass, 120 fail."""
    text = "a" * length
    assert is_plausible_heading(text) is (length < 120)


def test_numbered_prefix_beats_every_other_signal() -> None:
    """A long, colon-terminated, synopsis-shaped line still passes numbered."""
    text = (
        "11.18 Configuring the Autostart Service - restart the daemons "
        "after the configuration file changes have been applied and "
        "verified by the cluster health check."
    )
    assert len(text) > 120
    assert text.endswith(".")
    assert " - " in text
    assert is_plausible_heading(text) is True
