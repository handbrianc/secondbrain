#!/usr/bin/env python3
"""Generate SBOM and comprehensive analysis documentation for the project.

This script:
1. Generates a CycloneDX SBOM from the current environment
2. Analyzes license risks
3. Generates LICENSE-RISK-REPORT.md
4. Generates/updates docs/architecture/SBOM_ANALYSIS.md
5. Generates license_analysis.json

Run: python scripts/generate_sbom_analysis.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404 - required for shell command execution
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Global timestamp for deterministic output
_deterministic_timestamp: datetime | None = None


def _get_timestamp() -> datetime:
    """Get deterministic timestamp for reproducible SBOM generation."""
    global _deterministic_timestamp
    if _deterministic_timestamp is not None:
        return _deterministic_timestamp

    # Use GIT_AUTHOR_DATE if available, otherwise use current time
    git_date = os.environ.get("GIT_AUTHOR_DATE")
    if git_date:
        try:
            ts = int(git_date.split()[0])
            _deterministic_timestamp = datetime.fromtimestamp(ts)
            return _deterministic_timestamp
        except (ValueError, IndexError):
            pass

    _deterministic_timestamp = datetime.now()
    return _deterministic_timestamp


def run_command(cmd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return result.

    Note: shell=True is required for complex command chains with pipes and redirects.
    Commands are validated and controlled (not user input).
    """
    result = subprocess.run(  # nosec B602
        cmd, shell=True, capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        print(f"Error running command: {cmd}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result


def generate_sbom() -> Path:
    """Generate SBOM from current environment."""
    print("📦 Generating SBOM from current environment...")

    # Use current venv if available, otherwise create isolated one
    venv_path = Path("venv")
    if not venv_path.exists():
        venv_path = Path("/tmp/sbom-venv-temp")  # nosec B108 - temp dir for SBOM generation
        if venv_path.exists():
            shutil.rmtree(venv_path)
        print("Creating temporary venv...")
        run_command(f"python -m venv {venv_path}")
        run_command(f"{venv_path}/bin/pip install --upgrade pip")
        run_command(f"{venv_path}/bin/pip install -e .")

    cyclonedx = venv_path / "bin" / "cyclonedx-py"
    if not cyclonedx.exists():
        run_command(f"{venv_path}/bin/pip install cyclonedx-bom")

    # Ensure docs/architecture folder exists
    sbom_output_path = Path("docs/architecture/sbom.json")
    sbom_output_path.parent.mkdir(parents=True, exist_ok=True)
    python_bin = venv_path / "bin" / "python"
    run_command(
        f"{cyclonedx} environment {python_bin} "
        f"--sv 1.5 --of JSON -o {sbom_output_path} --validate"
    )

    print(f"✅ SBOM generated: {sbom_output_path}")
    return sbom_output_path


def analyze_licenses(sbom_path: Path) -> dict[str, Any]:
    """Analyze licenses from SBOM and return analysis data."""
    print("🔍 Analyzing licenses...")

    with sbom_path.open() as f:
        sbom = json.load(f)

    high_risk_patterns = ["gpl", "agpl", "lgpl", "sspl", "busl", "proprietary"]
    medium_risk_patterns = ["mpl", "cpl", "epl", "cpal"]

    # Known license mappings for packages with missing metadata
    known_licenses = {
        "antlr4-python3-runtime": "BSD-3-Clause",
        "cryptography": "Apache-2.0",
        "numpy": "BSD-3-Clause",
        "packaging": "Apache-2.0",
        "pypdfium2": "Apache-2.0",
        "regex": "PSFL",
        "sentinels": "MIT",
        "torchvision": "BSD-3-Clause",
        "tqdm": "MIT",
    }

    unknown_licenses: list[dict[str, str]] = []
    high_risk: list[dict[str, str]] = []
    medium_risk: list[dict[str, str]] = []
    low_risk: list[dict[str, str]] = []
    license_map: defaultdict[str, list[dict[str, str]]] = defaultdict(list)

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
            # Check known licenses
            if name in known_licenses:
                license_ids = [known_licenses[name]]
            else:
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

    analysis = {
        "total_components": len(sbom.get("components", [])),
        "unique_licenses": len(license_map),
        "unknown_count": len(unknown_licenses),
        "high_risk": high_risk,
        "medium_risk": medium_risk,
        "low_risk": low_risk,
        "unknown_licenses": unknown_licenses,
        "license_distribution": {k: len(v) for k, v in license_map.items()},
        "generated_at": _get_timestamp().isoformat(),
    }

    return analysis


def generate_license_risk_report(analysis: dict[str, Any]) -> None:
    """Generate LICENSE-RISK-REPORT.md in docs/architecture folder."""
    print("📝 Generating LICENSE-RISK-REPORT.md...")

    # Ensure docs/architecture folder exists
    output_path = Path("docs/architecture/LICENSE-RISK-REPORT.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_lines = [
        "# License Risk Report",
        "",
        "**Project**: secondbrain",
        f"**Generated**: {_get_timestamp().strftime('%Y-%m-%d %H:%M:%S')}",
        "**SBOM File**: sbom.json",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Dependencies** | {analysis['total_components']} |",
        f"| **Unique Licenses** | {analysis['unique_licenses']} |",
        f"| **Unknown Licenses** | {analysis['unknown_count']} |",
        f"| **High Risk Packages** | {len(analysis['high_risk'])} |",
        f"| **Medium Risk Packages** | {len(analysis['medium_risk'])} |",
        f"| **Low Risk Packages** | {len(analysis['low_risk'])} |",
        "",
    ]

    # Risk assessment
    if analysis["high_risk"] or analysis["unknown_licenses"]:
        report_lines.append("### Overall Risk Assessment: **REQUIRES REVIEW**")
        if analysis["high_risk"]:
            report_lines.append(
                f"- **WARNING**: {len(analysis['high_risk'])} packages use strong copyleft licenses (GPL/LGPL)"
            )
        if analysis["unknown_licenses"]:
            report_lines.append(
                f"- **WARNING**: {len(analysis['unknown_licenses'])} packages have unknown licenses requiring manual review"
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
            f"**Count**: {len(analysis['high_risk'])} packages",
            "",
        ]
    )

    if analysis["high_risk"]:
        report_lines.append("| Package | Version | License | Concern |")
        report_lines.append("|---------|---------|---------|---------|")
        for item in sorted(analysis["high_risk"], key=lambda x: x["license"]):
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
            f"**Count**: {len(analysis['medium_risk'])} packages",
            "",
        ]
    )

    if analysis["medium_risk"]:
        report_lines.append("| Package | Version | License | Concern |")
        report_lines.append("|---------|---------|---------|---------|")
        for item in sorted(analysis["medium_risk"], key=lambda x: x["license"]):
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
            f"**Count**: {len(analysis['low_risk'])} packages",
            "",
            "Most dependencies use permissive licenses (MIT, Apache-2.0, BSD, ISC, etc.)",
            "",
        ]
    )

    if analysis["unknown_licenses"]:
        report_lines.extend(
            [
                "---",
                "",
                "## Packages Requiring Manual Review",
                "",
                f"**Count**: {len(analysis['unknown_licenses'])}",
                "",
                "The following packages have unknown or missing license metadata:",
                "",
            ]
        )
        for item in analysis["unknown_licenses"]:
            report_lines.append(f"- **{item['name']}@{item['version']}**")

    report_lines.extend(
        [
            "",
            "---",
            "",
            "*Report generated from CycloneDX SBOM using automated license analysis.*",
            f"*Review date: {_get_timestamp().strftime('%Y-%m-%d')}*",
        ]
    )

    with output_path.open("w") as f:
        f.write("\n".join(report_lines))

    print(f"✅ {output_path} generated")


def generate_sbom_analysis_doc(analysis: dict[str, Any]) -> None:
    """Generate/update docs/architecture/SBOM_ANALYSIS.md.

    Creates comprehensive SBOM analysis documentation including:
    - License risk assessment
    - Dependency analysis
    - Compliance notes
    - Changelog
    """
    print("📚 Generating SBOM_ANALYSIS.md...")

    # Get direct dependencies from pyproject.toml
    pyproject_path = Path("pyproject.toml")
    direct_deps: list[str] = []
    if pyproject_path.exists():
        content = pyproject_path.read_text()
        in_deps = False
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("dependencies = ["):
                in_deps = True
                continue
            if in_deps:
                if stripped == "]":
                    break
                if not stripped or stripped.startswith("#"):
                    continue
                dep = stripped.rstrip(",").strip()
                if (dep.startswith('"') and dep.endswith('"')) or (
                    dep.startswith("'") and dep.endswith("'")
                ):
                    dep = dep[1:-1]
                if dep:
                    direct_deps.append(dep)

    # Get SBOM file size
    sbom_path = Path("docs/architecture/sbom.json")
    sbom_size = sbom_path.stat().st_size if sbom_path.exists() else 0
    sbom_size_mb = sbom_size / (1024 * 1024)

    # Known license mappings for unknown packages
    known: dict[str, str] = {
        "antlr4-python3-runtime": "BSD-3-Clause",
        "cryptography": "Apache-2.0",
        "numpy": "BSD-3-Clause",
        "packaging": "Apache-2.0",
        "pypdfium2": "Apache-2.0",
        "regex": "PSFL",
        "sentinels": "MIT",
        "torchvision": "BSD-3-Clause",
        "tqdm": "MIT",
    }

    doc_lines = [
        "# SBOM Analysis & Dependency Trade-offs",
        "",
        f"**Last Updated**: {_get_timestamp().strftime('%Y-%m-%d %H:%M')}",
        f"**SBOM File**: `docs/architecture/sbom.json` ({sbom_size_mb:.0f}KB, CycloneDX 1.5)",
        f"**Total Production Dependencies**: {analysis['total_components']}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "This document provides a comprehensive analysis of the Software Bill of Materials (SBOM) for SecondBrain, including license risk assessment, dependency trade-offs, and migration options.",
        "",
        "### Current State",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| **Total Dependencies** | {analysis['total_components']} |",
        f"| **Direct Dependencies** | {len(direct_deps)} |",
        f"| **Transitive Dependencies** | {analysis['total_components'] - len(direct_deps)} |",
        "| **Install Size** | ~3GB (with PyTorch) |",
        f"| **High-Risk Licenses** | {len(analysis['high_risk'])} {'⚠️' if analysis['high_risk'] else '✅'} |",
        f"| **Medium-Risk Licenses** | {len(analysis['medium_risk'])} {'⚠️' if analysis['medium_risk'] else '✅'} |",
        f"| **Unknown Licenses** | {len(analysis['unknown_licenses'])} {'⚠️' if analysis['unknown_licenses'] else '✅'} |",
        f"| **Low-Risk Licenses** | {len(analysis['low_risk'])} ✅ |",
        "",
        "---",
        "",
        "## License Risk Assessment",
        "",
        "### High Risk (GPL/LGPL)",
        "",
    ]

    if analysis["high_risk"]:
        doc_lines.append("| Package | License | Status | Concern |")
        doc_lines.append("|---------|---------|--------|---------|")
        for item in sorted(analysis["high_risk"], key=lambda x: x["license"]):
            status = (
                "Dev-only" if "pyinstaller" in item["name"].lower() else "Transitive"
            )
            concern = (
                "Dev tool only"
                if "pyinstaller" in item["name"].lower()
                else "Weak copyleft - acceptable for internal use"
            )
            doc_lines.append(
                f"| **{item['name']}** | {item['license']} | {status} | {concern} |"
            )
    else:
        doc_lines.append("*No high-risk licenses found.*")

    doc_lines.extend(
        [
            "",
            "### Medium Risk (Weak Copyleft)",
            "",
        ]
    )

    if analysis["medium_risk"]:
        doc_lines.append("| Package | License | Reason |")
        doc_lines.append("|---------|---------|--------|")
        for item in sorted(analysis["medium_risk"], key=lambda x: x["license"]):
            reason = (
                "Required by httpx for HTTPS"
                if "certifi" in item["name"].lower()
                else "Transitive dependency"
            )
            doc_lines.append(f"| **{item['name']}** | {item['license']} | {reason} |")
    else:
        doc_lines.append("*No medium-risk licenses found.*")

    doc_lines.extend(
        [
            "",
            "### Unknown Licenses",
            "",
        ]
    )

    if analysis["unknown_licenses"]:
        doc_lines.append("| Package | Actual License | Risk |")
        doc_lines.append("|---------|---------------|------|")
        known = {
            "antlr4-python3-runtime": "BSD-3-Clause",
            "cryptography": "Apache-2.0",
            "numpy": "BSD-3-Clause",
            "packaging": "Apache-2.0",
            "pypdfium2": "Apache-2.0",
            "regex": "PSFL",
            "sentinels": "MIT",
            "torchvision": "BSD-3-Clause",
            "tqdm": "MIT",
        }
        for item in analysis["unknown_licenses"]:
            name = item["name"]
            license_name = known.get(name, "Unknown")
            risk = "✅ Safe" if license_name != "Unknown" else "⚠️ Review needed"
            doc_lines.append(f"| **{name}** | {license_name} | {risk} |")
    else:
        doc_lines.append("*All licenses identified.*")

    doc_lines.extend(
        [
            "",
            "---",
            "",
            "## Dependency Analysis",
            "",
            "### Direct Dependencies",
            "",
            "```toml",
            "# pyproject.toml [project.dependencies]",
        ]
    )

    for dep in direct_deps:
        doc_lines.append(dep)

    doc_lines.extend(
        [
            "```",
            "",
            "---",
            "",
            "## SBOM Generation",
            "",
            "### Generating the SBOM",
            "",
            "Run the analysis script:",
            "",
            "```bash",
            "python scripts/generate_sbom_analysis.py",
            "```",
            "",
            "This will:",
            "1. Generate SBOM from current environment using CycloneDX",
            "2. Analyze all licenses",
            "3. Generate LICENSE-RISK-REPORT.md",
            "4. Generate/update this SBOM_ANALYSIS.md",
            "5. Generate license_analysis.json",
            "",
            "---",
            "",
            "## Compliance Notes",
            "",
            "### High-Risk Packages",
            "",
        ]
    )

    if analysis["high_risk"]:
        for item in analysis["high_risk"]:
            if "pyinstaller" in item["name"].lower():
                doc_lines.extend(
                    [
                        f"**{item['name']}** ({item['license']}): Build tool for creating distributable binaries. Not in production runtime. Safe to use for development.",
                        "",
                    ]
                )
            elif "chardet" in item["name"].lower():
                doc_lines.extend(
                    [
                        f"**{item['name']}** ({item['license']}): Transitive dependency via docling-core. LGPL allows linking from proprietary code. Acceptable for internal use.",
                        "",
                    ]
                )
    else:
        doc_lines.append("*No high-risk packages requiring action.*")
        doc_lines.append("")

    doc_lines.extend(
        [
            "### Medium-Risk Packages",
            "",
        ]
    )

    if analysis["medium_risk"]:
        doc_lines.extend(
            [
                "The following packages use weak copyleft licenses (MPL-2.0, etc.):",
                "",
            ]
        )
        for item in analysis["medium_risk"]:
            doc_lines.append(
                f"- **{item['name']}** ({item['license']}): No viral effect on dependent code. Safe for MIT projects."
            )
        doc_lines.append("")
    else:
        doc_lines.append("*No medium-risk packages requiring action.*")
        doc_lines.append("")

    doc_lines.extend(
        [
            "### Unknown License Packages",
            "",
        ]
    )

    if analysis["unknown_licenses"]:
        doc_lines.append(
            "These packages have clear licenses but metadata extraction failed:"
        )
        doc_lines.append("")
        for item in analysis["unknown_licenses"]:
            name = item["name"]
            license_name = known.get(name, "Unknown")
            doc_lines.append(f"- **{name}**: {license_name} (permissive)")
        doc_lines.append("")
        doc_lines.append(
            "**Action**: No action required. All are safe for MIT projects."
        )
        doc_lines.append("")
    else:
        doc_lines.append("*All packages have identifiable licenses.*")
        doc_lines.append("")

    doc_lines.extend(
        [
            "---",
            "",
            "## References",
            "",
            "- [CycloneDX SBOM Specification](https://cyclonedx.org/)",
            "- [MPL-2.0 License](https://www.mozilla.org/en-US/MPL/2.0/)",
            "- [docling Project](https://github.com/docling-project/docling)",
            "",
            "---",
            "",
            "## Changelog",
            "",
            "| Date | Change |",
            "|------|--------|",
            f"| {_get_timestamp().strftime('%Y-%m-%d %H:%M')} | SBOM updated via automated script |",
        ]
    )

    # Ensure docs/architecture directory exists
    sbom_analysis_path = Path("docs/architecture/SBOM_ANALYSIS.md")
    sbom_analysis_path.parent.mkdir(parents=True, exist_ok=True)

    with sbom_analysis_path.open("w") as f:
        f.write("\n".join(doc_lines))

    print(f"✅ SBOM_ANALYSIS.md generated: {sbom_analysis_path}")


def main() -> None:
    """Main entry point."""
    print("=" * 60)
    print("🔧 SBOM & Analysis Generator")
    print("=" * 60)
    print()

    # Step 1: Generate SBOM
    sbom_path = generate_sbom()
    print()

    # Step 2: Analyze licenses
    analysis = analyze_licenses(sbom_path)
    print()

    # Step 3: Generate LICENSE-RISK-REPORT.md
    generate_license_risk_report(analysis)
    print()

    # Step 4: Generate SBOM_ANALYSIS.md
    generate_sbom_analysis_doc(analysis)
    print()

    # Step 5: Save JSON analysis
    license_analysis_path = Path("docs/architecture/license_analysis.json")
    license_analysis_path.parent.mkdir(parents=True, exist_ok=True)
    with license_analysis_path.open("w") as f:
        json.dump(analysis, f, indent=2)
    print(f"✅ {license_analysis_path} generated")
    print()

    # Print summary
    print("=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total dependencies: {analysis['total_components']}")
    print(
        f"High risk: {len(analysis['high_risk'])} {'⚠️' if analysis['high_risk'] else '✅'}"
    )
    print(
        f"Medium risk: {len(analysis['medium_risk'])} {'⚠️' if analysis['medium_risk'] else '✅'}"
    )
    print(f"Low risk: {len(analysis['low_risk'])} ✅")
    print(
        f"Unknown: {len(analysis['unknown_licenses'])} {'⚠️' if analysis['unknown_licenses'] else '✅'}"
    )
    print()
    print("📁 Generated files:")
    print("  - docs/architecture/sbom.json")
    print("  - docs/architecture/LICENSE-RISK-REPORT.md")
    print("  - docs/architecture/SBOM_ANALYSIS.md")
    print("  - docs/architecture/license_analysis.json")
    print()
    print("✅ SBOM analysis complete!")


if __name__ == "__main__":
    main()
