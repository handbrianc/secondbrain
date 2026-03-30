#!/usr/bin/env python3
"""
SBOM Generation Tool for SecondBrain

Generates Software Bill of Materials in SPDX and CycloneDX formats.
This wrapper provides a Python interface for SBOM generation with
additional features like comparison and validation.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SBOMGenerator:
    """Generates Software Bill of Materials in multiple formats."""

    def __init__(self, project_root: Path, output_dir: Path, include_dev: bool = True):
        """Initialize the SBOM generator.

        Args:
            project_root: Path to the project root directory
            output_dir: Path to output directory for SBOM files
            include_dev: Whether to include development dependencies
        """
        self.project_root = project_root
        self.output_dir = output_dir
        self.include_dev = include_dev
        self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def generate_cyclonedx(self) -> Path:
        """Generate SBOM in CycloneDX JSON format.

        Returns:
            Path to the generated SBOM file
        """
        output_file = self.output_dir / "sbom.cyclonedx.json"

        try:
            # Generate CycloneDX SBOM to file
            result = subprocess.run(
                ["cyclonedx-py", "environment", "-o", str(output_file)],
                capture_output=True,
                text=True,
                check=True,
                cwd=self.project_root,
            )

            # Read the generated file
            sbom_data = json.loads(output_file.read_text())

            sbom_data.setdefault("metadata", {})
            sbom_data["metadata"].setdefault("properties", [])
            sbom_data["metadata"]["properties"].extend(
                [
                    {"name": "project:version", "value": "0.4.0"},
                    {"name": "project:name", "value": "secondbrain"},
                    {"name": "generated:timestamp", "value": self.timestamp},
                    {
                        "name": "includes:dev-dependencies",
                        "value": str(self.include_dev).lower(),
                    },
                ]
            )

            output_file.write_text(json.dumps(sbom_data, indent=2))
            return output_file

        except subprocess.CalledProcessError as e:
            print(f"Error generating CycloneDX SBOM: {e.stderr}", file=sys.stderr)
            raise

    def generate_spdx(self) -> Path:
        """Generate SBOM in SPDX 2.3 JSON format.

        Returns:
            Path to the generated SBOM file
        """
        output_file = self.output_dir / "sbom.spdx.json"

        try:
            result = subprocess.run(
                ["cyclonedx-py", "environment"],
                capture_output=True,
                text=True,
                check=True,
                cwd=self.project_root,
            )

            cyclonedx_data = json.loads(result.stdout)
            components = cyclonedx_data.get("components", [])

            spdx_doc = {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": "secondbrain",
                "documentNamespace": f"https://spdx.example.com/secondbrain/{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "creationInfo": {
                    "created": self.timestamp,
                    "creators": ["Tool: cyclonedx-py", "Tool: generate_sbom.py"],
                },
                "packages": [
                    {
                        "SPDXID": "SPDXRef-Package-secondbrain",
                        "name": "secondbrain",
                        "versionInfo": "0.4.0",
                        "downloadLocation": "NOASSERTION",
                        "filesAnalyzed": False,
                        "licenseConcluded": "MIT",
                        "licenseDeclared": "MIT",
                        "copyrightText": "Copyright 2026",
                    }
                ],
            }

            for i, comp in enumerate(components):
                license_info = comp.get("license", {})
                license_id = (
                    license_info.get("id", "NOASSERTION")
                    if license_info
                    else "NOASSERTION"
                )
                license_name = (
                    license_info.get("name", "NOASSERTION")
                    if license_info
                    else "NOASSERTION"
                )

                spdx_doc["packages"].append(
                    {
                        "SPDXID": f"SPDXRef-Package-{i + 1}",
                        "name": comp.get("name", "unknown"),
                        "versionInfo": comp.get("version", "unknown"),
                        "downloadLocation": "NOASSERTION",
                        "filesAnalyzed": False,
                        "licenseConcluded": license_id or license_name,
                        "licenseDeclared": license_id or license_name,
                    }
                )

            spdx_doc["relationships"] = [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relatedSpdxElement": "SPDXRef-Package-secondbrain",
                    "relationshipType": "DESCRIBES",
                }
            ]

            for i in range(len(components)):
                spdx_doc["relationships"].append(
                    {
                        "spdxElementId": "SPDXRef-Package-secondbrain",
                        "relatedSpdxElement": f"SPDXRef-Package-{i + 1}",
                        "relationshipType": "DEPENDS_ON",
                    }
                )

            output_file.write_text(json.dumps(spdx_doc, indent=2))
            return output_file

        except subprocess.CalledProcessError as e:
            print(f"Error generating SPDX SBOM: {e.stderr}", file=sys.stderr)
            raise

    def compare_with_previous(self) -> dict[str, Any]:
        """Compare current SBOM with previous version.

        Returns:
            Dictionary with comparison results
        """
        current_file = self.output_dir / "sbom.cyclonedx.json"
        previous_file = self.output_dir / "sbom.cyclonedx.json.previous"

        if not previous_file.exists():
            return {
                "added": [],
                "removed": [],
                "changed": [],
                "message": "No previous SBOM found for comparison",
            }

        try:
            current = json.loads(current_file.read_text())
            previous = json.loads(previous_file.read_text())

            current_pkgs = {
                c["name"]: c["version"] for c in current.get("components", [])
            }
            previous_pkgs = {
                p["name"]: p["version"] for p in previous.get("components", [])
            }

            added = sorted(set(current_pkgs.keys()) - set(previous_pkgs.keys()))
            removed = sorted(set(previous_pkgs.keys()) - set(current_pkgs.keys()))
            changed = [
                {"name": name, "old": previous_pkgs[name], "new": current_pkgs[name]}
                for name in sorted(current_pkgs.keys() & previous_pkgs.keys())
                if current_pkgs[name] != previous_pkgs[name]
            ]

            return {
                "added": added,
                "removed": removed,
                "changed": changed,
                "summary": {
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "changed_count": len(changed),
                },
            }

        except (json.JSONDecodeError, KeyError) as e:
            return {"error": f"Failed to compare SBOMs: {e}"}

    def validate_sbom(self, sbom_file: Path) -> tuple[bool, list[str]]:
        """Validate an SBOM file.

        Args:
            sbom_file: Path to the SBOM file to validate

        Returns:
            Tuple of (is_valid, list of validation errors)
        """
        errors = []

        if not sbom_file.exists():
            return False, ["SBOM file does not exist"]

        try:
            data = json.loads(sbom_file.read_text())

            if "sbom.cyclonedx" in sbom_file.name:
                if "components" not in data and "packages" not in data:
                    errors.append("Missing components/packages")
                if "metadata" not in data:
                    errors.append("Missing metadata")

            elif "sbom.spdx" in sbom_file.name:
                if "spdxVersion" not in data:
                    errors.append("Missing spdxVersion")
                if "packages" not in data:
                    errors.append("Missing packages")
                if "creationInfo" not in data:
                    errors.append("Missing creationInfo")

            return len(errors) == 0, errors

        except json.JSONDecodeError as e:
            return False, [f"Invalid JSON: {e}"]


def main():
    """Main entry point for SBOM generation."""
    parser = argparse.ArgumentParser(
        description="Generate Software Bill of Materials for SecondBrain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Generate all formats
  %(prog)s --format spdx            # Generate SPDX only
  %(prog)s --format cyclonedx       # Generate CycloneDX only
  %(prog)s --output ./custom-sbom   # Custom output directory
  %(prog)s --no-dev                 # Exclude dev dependencies
  %(prog)s --compare                # Compare with previous
        """,
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["spdx", "cyclonedx", "all"],
        default="all",
        help="Output format (default: all)",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="reports/sbom",
        help="Output directory (default: reports/sbom)",
    )

    parser.add_argument(
        "--no-dev", action="store_true", help="Exclude development dependencies"
    )

    parser.add_argument(
        "--compare", action="store_true", help="Compare with previous SBOM"
    )

    parser.add_argument(
        "--validate", action="store_true", help="Validate generated SBOM files"
    )

    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    output_dir = project_root / args.output

    print("=" * 50)
    print("SecondBrain SBOM Generation")
    print("=" * 50)
    print()

    generator = SBOMGenerator(
        project_root=project_root, output_dir=output_dir, include_dev=not args.no_dev
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.compare and (output_dir / "sbom.cyclonedx.json").exists():
        import shutil

        shutil.copy(
            output_dir / "sbom.cyclonedx.json",
            output_dir / "sbom.cyclonedx.json.previous",
        )

    generated_files = []

    if args.format in ["cyclonedx", "all"]:
        print("Generating CycloneDX JSON SBOM...")
        cyclonedx_file = generator.generate_cyclonedx()
        generated_files.append(cyclonedx_file)
        print(f"  Generated: {cyclonedx_file}")

    if args.format in ["spdx", "all"]:
        print("Generating SPDX 2.3 JSON SBOM...")
        spdx_file = generator.generate_spdx()
        generated_files.append(spdx_file)
        print(f"  Generated: {spdx_file}")

    print()

    if args.compare:
        print("Comparing with previous SBOM...")
        comparison = generator.compare_with_previous()

        if "error" in comparison:
            print(f"  Error: {comparison['error']}")
        elif "message" in comparison:
            print(f"  {comparison['message']}")
        else:
            print(f"  Added packages: {comparison['summary']['added_count']}")
            print(f"  Removed packages: {comparison['summary']['removed_count']}")
            print(f"  Changed versions: {comparison['summary']['changed_count']}")

        print()

    if args.validate:
        print("Validating SBOM files...")
        all_valid = True

        for sbom_file in generated_files:
            is_valid, errors = generator.validate_sbom(sbom_file)

            if is_valid:
                print(f"  ✓ {sbom_file.name}")
            else:
                print(f"  ✗ {sbom_file.name}")
                for error in errors:
                    print(f"    - {error}")
                all_valid = False

        print()

        if not all_valid:
            print("Validation failed!")
            sys.exit(1)

    print("=" * 50)
    print("SBOM generation complete!")
    print("=" * 50)
    print(f"Output directory: {output_dir}")
    print(f"Generated files: {len(generated_files)}")

    for file in generated_files:
        size = file.stat().st_size
        print(f"  {file.name} ({size:,} bytes)")


if __name__ == "__main__":
    main()
