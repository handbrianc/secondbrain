"""Tests for converting license classifiers to SPDX identifiers."""

import pytest

from scripts.sbom_converter import _classifier_to_spdx


@pytest.mark.parametrize(
    ("classifier", "expected"),
    [
        ("BSD License", "NOASSERTION"),
        ("License :: OSI Approved :: BSD License", "NOASSERTION"),
        (
            "GNU Lesser General Public License v2 (LGPLv2)",
            "NOASSERTION",
        ),
        ("Other/Proprietary License", "NOASSERTION"),
        ("License :: OSI Approved", "NOASSERTION"),
        ("MIT License", "MIT"),
        ("License :: OSI Approved :: MIT License", "MIT"),
        ("BSD-2-Clause", "BSD-2-Clause"),
    ],
)
def test_classifier_to_spdx(classifier: str, expected: str) -> None:
    assert _classifier_to_spdx(classifier) == expected
