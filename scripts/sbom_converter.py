#!/usr/bin/env python3
"""SBOM conversion utility - converts CycloneDX JSON to SPDX format."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def convert_cyclonedx_to_spdx(cyclonedx_path: str, spdx_path: str) -> None:
    """Convert CycloneDX JSON SBOM to SPDX format.

    Args:
        cyclonedx_path: Path to CycloneDX JSON file
        spdx_path: Path for output SPDX file
    """
    # Read the JSON SBOM
    with open(cyclonedx_path) as f:
        sbom_data = json.load(f)

    # Extract packages from CycloneDX format
    packages = []
    if "components" in sbom_data:
        for comp in sbom_data["components"]:
            license_info = "NOASSERTION"
            if comp.get("licenses"):
                license_data = comp["licenses"][0].get("license", {})
                license_info = license_data.get("id") or license_data.get(
                    "name", "NOASSERTION"
                )

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
                    "License": pkg.get("license", "NOASSERTION"),
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
    with open(spdx_path, "w") as f:
        f.write("\n".join(doc_lines))


def main() -> int:
    """Main entry point for SBOM conversion."""
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
