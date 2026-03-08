#!/usr/bin/env python3
"""Generate SBOM and license risk analysis for the project."""

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def run_command(cmd: str) -> None:
    """Run a shell command."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)


def analyze_licenses() -> None:
    """Analyze licenses from SBOM and generate reports."""
    sbom_path = Path("sbom.json")
    if not sbom_path.exists():
        print("Error: sbom.json not found. Run cyclonedx-py first.", file=sys.stderr)
        sys.exit(1)

    with sbom_path.open() as f:
        sbom = json.load(f)

    high_risk_patterns = ["gpl", "agpl", "lgpl", "sspl", "busl", "proprietary"]
    medium_risk_patterns = ["mpl", "cpl", "epl", "cpal"]

    unknown_licenses = []
    high_risk = []
    medium_risk = []
    low_risk = []
    license_map = defaultdict(list)

    for component in sbom.get("components", []):
        name = component.get("name", "unknown")
        version = component.get("version", "unknown")
        licenses = component.get("licenses", [])
        license_ids = []
        for lic in licenses:
            lic_info = lic.get("license", {})
            if "id" in lic_info:
                license_ids.append(lic_info["id"])
            elif "name" in lic_info:
                license_ids.append(lic_info["name"])
        if not license_ids:
            unknown_licenses.append({"name": name, "version": version})
            continue
        primary_license = license_ids[0]
        license_map[primary_license].append({"name": name, "version": version})
        license_lower = primary_license.lower()
        if any(p in license_lower for p in high_risk_patterns):
            high_risk.append(
                {"name": name, "version": version, "license": primary_license}
            )
        elif any(p in license_lower for p in medium_risk_patterns):
            medium_risk.append(
                {"name": name, "version": version, "license": primary_license}
            )
        else:
            low_risk.append(
                {"name": name, "version": version, "license": primary_license}
            )

    # Generate report
    report_lines = [
        "# License Risk Report",
        "",
        "**Project**: secondbrain",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "**SBOM File**: sbom.json",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Dependencies** | {len(sbom.get('components', []))} |",
        f"| **Unique Licenses** | {len(license_map)} |",
        f"| **Unknown Licenses** | {len(unknown_licenses)} |",
        f"| **High Risk Packages** | {len(high_risk)} |",
        f"| **Medium Risk Packages** | {len(medium_risk)} |",
        f"| **Low Risk Packages** | {len(low_risk)} |",
        "",
    ]

    # Risk assessment
    if high_risk or unknown_licenses:
        report_lines.append("### Overall Risk Assessment: **REQUIRES REVIEW**")
        if high_risk:
            report_lines.append(
                f"- **WARNING**: {len(high_risk)} packages use strong copyleft licenses (GPL/LGPL)"
            )
        if unknown_licenses:
            report_lines.append(
                f"- **WARNING**: {len(unknown_licenses)} packages have unknown licenses requiring manual review"
            )
    else:
        report_lines.append("### Overall Risk Assessment: **LOW**")
        report_lines.append("- No high-risk or unknown licenses detected")

    report_lines.extend(
        [
            "",
            "---",
            "",
            "## Risk Classification",
            "",
            "### HIGH RISK (Strong Copyleft)",
            "",
            f"**Count**: {len(high_risk)} packages",
            "",
        ]
    )

    if high_risk:
        report_lines.append("| Package | Version | License | Concern |")
        report_lines.append("|---------|---------|---------|---------|")
        for item in sorted(high_risk, key=lambda x: x["license"]):
            concern = (
                "Copyleft - may affect distribution"
                if "LGPL" in item["license"]
                else "Strong copyleft - GPL requires open source"
            )
            report_lines.append(
                f"| {item['name']} | {item['version']} | {item['license']} | {concern} |"
            )
    else:
        report_lines.append("*No high-risk licenses found.*")

    report_lines.extend(
        [
            "",
            "### MEDIUM RISK (Weak Copyleft)",
            "",
            f"**Count**: {len(medium_risk)} packages",
            "",
        ]
    )

    if medium_risk:
        report_lines.append("| Package | Version | License | Concern |")
        report_lines.append("|---------|---------|---------|---------|")
        for item in sorted(medium_risk, key=lambda x: x["license"]):
            report_lines.append(
                f"| {item['name']} | {item['version']} | {item['license']} | Weak copyleft - review distribution model |"
            )
    else:
        report_lines.append("*No medium-risk licenses found.*")

    report_lines.extend(
        [
            "",
            "### LOW RISK (Permissive)",
            "",
            f"**Count**: {len(low_risk)} packages",
            "",
        ]
    )

    if unknown_licenses:
        report_lines.extend(
            [
                "---",
                "",
                "## Packages Requiring Manual Review",
                "",
                f"**Count**: {len(unknown_licenses)}",
                "",
                "The following packages have unknown or missing license metadata:",
                "",
            ]
        )
        for item in unknown_licenses:
            report_lines.append(f"- **{item['name']}@{item['version']}**")

    report_lines.extend(
        [
            "",
            "---",
            "",
            "*Report generated from CycloneDX SBOM using automated license analysis.*",
            f"*Review date: {datetime.now().strftime('%Y-%m-%d')}*",
        ]
    )

    with Path("LICENSE-RISK-REPORT.md").open("w") as f:
        f.write("\n".join(report_lines))

    # Save analysis data
    analysis = {
        "total_components": len(sbom.get("components", [])),
        "unique_licenses": len(license_map),
        "unknown_count": len(unknown_licenses),
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "unknown_licenses": unknown_licenses,
        "license_distribution": {k: len(v) for k, v in license_map.items()},
    }

    with Path("license_analysis.json").open("w") as f:
        json.dump(analysis, f, indent=2)

    # Print summary
    if high_risk:
        print(f"⚠️  WARNING: {len(high_risk)} high-risk packages detected (GPL/LGPL)")
    if unknown_licenses:
        print(f"⚠️  WARNING: {len(unknown_licenses)} packages with unknown licenses")
    print(
        f"✅ SBOM and license analysis updated: {len(sbom.get('components', []))} components"
    )


def main() -> None:
    """Main entry point."""
    import shutil
    import subprocess

    venv_path = Path("/tmp/sbom-venv-clean")
    if venv_path.exists():
        shutil.rmtree(venv_path)

    print("Creating isolated venv...")
    subprocess.run(["python", "-m", "venv", str(venv_path)], check=True)

    venv_bin = venv_path / "bin"
    pip = venv_bin / "pip"
    python = venv_bin / "python"
    cyclonedx = venv_bin / "cyclonedx-py"

    print("Upgrading pip...")
    subprocess.run(
        [str(pip), "install", "--upgrade", "pip"], check=True, capture_output=True
    )

    print("Installing production dependencies only...")
    subprocess.run([str(pip), "install", "-e", "."], check=True, capture_output=True)

    print("Installing cyclonedx-bom for SBOM generation...")
    subprocess.run(
        [str(pip), "install", "cyclonedx-bom"], check=True, capture_output=True
    )

    print("Generating production-only SBOM (excluding cyclonedx-bom and its deps)...")
    subprocess.run(
        [
            str(cyclonedx),
            "environment",
            str(python),
            "--output-format",
            "JSON",
            "--spec-version",
            "1.6",
            "--output-file",
            "sbom.json",
            "--gather-license-texts",
            "--output-reproducible",
        ],
        check=True,
    )

    print("Removing SBOM generation tools from SBOM...")
    with Path("sbom.json").open() as f:
        sbom = json.load(f)

    filtered_components = [
        c
        for c in sbom.get("components", [])
        if c.get("name")
        not in ("cyclonedx-bom", "cyclonedx-python-lib", "chardet", "fqdn")
    ]

    sbom["components"] = filtered_components

    with Path("sbom.json").open("w") as f:
        json.dump(sbom, f, indent=2)

    print(f"SBOM updated with {len(filtered_components)} production components")

    print("Cleaning up...")
    shutil.rmtree(venv_path)

    # Analyze licenses
    print("Analyzing licenses...")
    analyze_licenses()

    print("✅ SBOM analysis complete")


if __name__ == "__main__":
    main()
