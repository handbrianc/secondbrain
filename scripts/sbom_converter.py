#!/usr/bin/env python3
"""SBOM conversion utility - converts CycloneDX JSON to SPDX format."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# PyPI trove classifier phrases resolved to SPDX license identifiers.
# cyclonedx-py emits these classifier strings verbatim when a distribution
# declares only a classifier instead of an SPDX expression. Classifiers name
# a license family, not an exact text: "BSD License" maps to the dominant
# 3-clause form on PyPI, and "Other/Proprietary License" maps to a LicenseRef
# so it stays flagged for manual review. Non-identifying classifiers
# ("License :: OSI Approved", "License :: DFSG approved") are intentionally
# absent and remain as-is.
CLASSIFIER_TO_SPDX: dict[str, str] = {
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License": "ISC",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.1-only",
    "GNU Lesser General Public License v2.1 (LGPLv2.1)": "LGPL-2.1-only",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "Python Software Foundation License": "Python-2.0",
    "Other/Proprietary License": "LicenseRef-Proprietary",
}


def _classifier_to_spdx(value: str) -> str:
    """Resolve a PyPI trove classifier license string to an SPDX identifier.

    Args:
        value: Raw license value from the CycloneDX SBOM

    Returns:
        SPDX identifier when the value is a classifier string (starting
        with "License ::") or a bare known classifier phrase, otherwise
        the value unchanged
    """
    stripped = value.strip()
    if stripped.startswith("License ::"):
        # The final "::"-separated segment carries the license phrase,
        # e.g. "License :: OSI Approved :: MIT License" -> "MIT License".
        phrase = stripped.rsplit("::", 1)[-1].strip()
    else:
        phrase = stripped
    return CLASSIFIER_TO_SPDX.get(phrase, value)


def convert_cyclonedx_to_spdx(cyclonedx_path: str, spdx_path: str) -> None:
    """Convert CycloneDX JSON SBOM to SPDX format.

    Args:
        cyclonedx_path: Path to CycloneDX JSON file
        spdx_path: Path for output SPDX file
    """
    # Read the JSON SBOM
    with Path(cyclonedx_path).open() as f:
        sbom_data = json.load(f)

    # Extract packages from CycloneDX format
    packages = []
    if "components" in sbom_data:
        for comp in sbom_data["components"]:
            license_info = "NOASSERTION"
            if comp.get("licenses"):
                license_data = comp["licenses"][0].get("license", {})
                license_info = (
                    license_data.get("id")
                    or license_data.get("name")
                    or comp["licenses"][0].get("expression")
                    or "NOASSERTION"
                )
                license_info = _classifier_to_spdx(license_info)

            packages.append(
                {
                    "Name": comp.get("name", "unknown"),
                    "Version": comp.get("version", "unknown"),
                    "License": license_info,
                }
            )
    elif "packages" in sbom_data:
        for pkg in sbom_data["packages"]:
            packages.append(
                {
                    "Name": pkg.get("name", "unknown"),
                    "Version": pkg.get("version", "unknown"),
                    "License": _classifier_to_spdx(pkg.get("license", "NOASSERTION")),
                }
            )

    # Create SPDX document header
    spdx_version = "2.3"
    spdx_id = "SPDXRef-DOCUMENT"
    namespace = "https://spdx.example.com/secondbrain"

    doc_lines = [
        f"SPDXVersion: SPDX-{spdx_version}",
        "DataLicense: CC0-1.0",
        f"SPDXID: {spdx_id}",
        "DocumentName: secondbrain",
        f"DocumentNamespace: {namespace}",
        "Creator: Tool: cyclonedx-py",
        f"Created: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "",
        "",
    ]

    # Add each package
    for i, pkg in enumerate(packages):
        pkg_id = f"SPDXRef-Package-{i + 1}"
        name = pkg["Name"]
        version = pkg["Version"]
        license_info = pkg["License"]

        pkg_lines = [
            f"PackageName: {name}",
            f"SPDXID: {pkg_id}",
            f"PackageVersion: {version}",
            f"PackageLicenseConcluded: {license_info}",
            "PackageLicenseInfoFromFiles: NOASSERTION",
            "PackageDownloadLocation: NOASSERTION",
            "FilesAnalyzed: false",
            "",
        ]
        doc_lines.extend(pkg_lines)

    # Write SPDX document
    with Path(spdx_path).open("w") as f:
        f.write("\n".join(doc_lines))


def main() -> int:
    """Convert CycloneDX JSON to SPDX format (entry point)."""
    # Default paths relative to project root
    project_root = Path(__file__).parent.parent
    cyclonedx_path = project_root / "sbom.json"
    spdx_path = project_root / "sbom.spdx"

    if not cyclonedx_path.exists():
        print(f"Error: {cyclonedx_path} not found", file=sys.stderr)
        return 1

    print(f"Converting {cyclonedx_path} to SPDX format...")
    convert_cyclonedx_to_spdx(str(cyclonedx_path), str(spdx_path))
    print(f"✅ SPDX SBOM generated: {spdx_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
