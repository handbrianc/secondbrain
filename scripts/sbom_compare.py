#!/usr/bin/env python3
"""Compare a generated CycloneDX SBOM against a committed baseline.

The dependency-security spec requires that a generated SBOM "SHALL be compared
for unexpected changes". This tool performs that comparison: it reads the
current CycloneDX JSON SBOM (``sbom.json`` produced by
``scripts/generate-sbom.sh``) and compares its component list against a
committed baseline (``sbom.baseline.json``).

Semantics
---------
Components are identified by name (case-insensitive). The comparison fails
with exit code 1 when a component was ADDED or REMOVED relative to the
baseline - both are unexpected supply-chain changes that need review. A
version-only update of an existing component is reported informationally but
does not fail, so routine dependency bumps do not break the check.

Exit codes
----------
0
    No unexpected changes, baseline absent (a notice is printed so CI stays
    green until a baseline is committed), or baseline updated via
    ``--update-baseline``.
1
    Unexpected changes: at least one component added or removed.
2
    Operational error: missing or invalid SBOM file, malformed JSON.

Only the Python standard library is used; no network access is required.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Project root (the directory that contains scripts/). Absolute by
# construction so the defaults below work from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SBOM_PATH = PROJECT_ROOT / "sbom.json"
DEFAULT_BASELINE_PATH = PROJECT_ROOT / "sbom.baseline.json"

EXIT_OK = 0
EXIT_UNEXPECTED_CHANGES = 1
EXIT_ERROR = 2


class SbomCompareError(Exception):
    """Raised when an input SBOM cannot be read, parsed, or interpreted."""


@dataclass(frozen=True)
class ComparisonResult:
    """Outcome of comparing a current SBOM against a baseline.

    Attributes
    ----------
    added
        Component names present in the current SBOM but missing from the
        baseline, sorted.
    removed
        Component names present in the baseline but missing from the current
        SBOM, sorted.
    changed
        Component names present in both whose versions differ, mapped to a
        ``(baseline_versions, current_versions)`` tuple. Version changes are
        informational only and do not fail the comparison.
    """

    added: list[str]
    removed: list[str]
    changed: dict[str, tuple[str, str]]

    @property
    def has_unexpected_changes(self) -> bool:
        """Whether any component was added or removed.

        Returns
        -------
            True when at least one component was added or removed relative
            to the baseline; those are the unexpected changes the spec calls
            out for alerting.
        """
        return bool(self.added or self.removed)


def read_sbom_document(sbom_path: Path) -> dict[str, Any]:
    """Read and structurally validate a CycloneDX JSON SBOM document.

    Args:
        sbom_path: Path to a CycloneDX JSON SBOM document.

    Returns
    -------
        The parsed SBOM document as a dictionary.

    Raises
    ------
    SbomCompareError
        If the file is missing, is not valid JSON, is not a JSON object, or
        lacks a ``components`` array.
    """
    try:
        with sbom_path.open(encoding="utf-8") as fh:
            document = json.load(fh)
    except FileNotFoundError as exc:
        raise SbomCompareError(f"SBOM file not found: {sbom_path}") from exc
    except json.JSONDecodeError as exc:
        raise SbomCompareError(f"Invalid JSON in {sbom_path}: {exc}") from exc
    except OSError as exc:
        raise SbomCompareError(f"Cannot read SBOM file {sbom_path}: {exc}") from exc

    if not isinstance(document, dict):
        raise SbomCompareError(f"{sbom_path} is not a JSON object")
    if "components" not in document:
        raise SbomCompareError(f"{sbom_path} has no 'components' array")
    if not isinstance(document["components"], list):
        raise SbomCompareError(f"{sbom_path} 'components' is not an array")
    return document


def component_versions(document: dict[str, Any]) -> dict[str, str]:
    """Extract a component name to version map from an SBOM document.

    Args:
        document: Parsed CycloneDX JSON SBOM document (must have a
            ``components`` array; entries without a usable name are skipped).

    Returns
    -------
        Mapping from lowercased component name to version string ("" when a
        component carries no version). When several entries share a name the
        first version encountered wins.
    """
    versions: dict[str, str] = {}
    for entry in document["components"]:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        version = entry.get("version")
        versions.setdefault(name.lower(), version if isinstance(version, str) else "")
    return versions


def compare_components(
    baseline: dict[str, str], current: dict[str, str]
) -> ComparisonResult:
    """Compare baseline and current component-version maps.

    Names are matched case-insensitively so normalized PyPI names compare
    equal regardless of the source document's casing.

    Args:
        baseline: Component name -> version map from the baseline SBOM.
        current: Component name -> version map from the current SBOM.

    Returns
    -------
        ComparisonResult with sorted added/removed names and informational
        version changes.
    """
    baseline_versions = {name.lower(): version for name, version in baseline.items()}
    current_versions = {name.lower(): version for name, version in current.items()}
    added = sorted(set(current_versions) - set(baseline_versions))
    removed = sorted(set(baseline_versions) - set(current_versions))
    changed = {
        name: (baseline_versions[name], current_versions[name])
        for name in sorted(set(baseline_versions) & set(current_versions))
        if baseline_versions[name] != current_versions[name]
    }
    return ComparisonResult(added=added, removed=removed, changed=changed)


def write_baseline(sbom_path: Path, baseline_path: Path) -> int:
    """Write a trimmed copy of the current SBOM as the new baseline.

    The baseline keeps only the ``components`` array, sorted by name and
    version, dropping volatile fields (serial numbers, timestamps) that
    change on every generation so the committed file stays stable.

    Args:
        sbom_path: Path to the current CycloneDX JSON SBOM.
        baseline_path: Path the baseline is written to (overwritten).

    Returns
    -------
        Number of components written to the baseline.

    Raises
    ------
    SbomCompareError
        If the current SBOM cannot be read or parsed.
    """
    document = read_sbom_document(sbom_path)
    components = [entry for entry in document["components"] if isinstance(entry, dict)]
    components.sort(
        key=lambda entry: (
            str(entry.get("name", "")).lower(),
            str(entry.get("version", "")),
        )
    )
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps({"components": components}, indent=2) + "\n", encoding="utf-8"
    )
    return len(components)


def render_report(
    result: ComparisonResult,
    baseline_versions: dict[str, str],
    current_versions: dict[str, str],
) -> str:
    """Render the human-readable comparison report.

    Args:
        result: The comparison outcome to render.
        baseline_versions: Component name -> version map of the baseline.
        current_versions: Component name -> version map of the current SBOM.

    Returns
    -------
        Multi-line report listing added/removed components (unexpected
        changes) and version-only updates (informational).
    """
    lines = [
        f"SBOM comparison: baseline has {len(baseline_versions)} components,"
        f" current has {len(current_versions)}"
    ]
    if result.added:
        lines.append("ADDED components (not in baseline):")
        lines.extend(f"  + {name} {current_versions[name]}" for name in result.added)
    if result.removed:
        lines.append("REMOVED components (in baseline, missing now):")
        lines.extend(f"  - {name} {baseline_versions[name]}" for name in result.removed)
    if result.changed:
        lines.append("Version changes (informational, not a failure):")
        lines.extend(
            f"  ~ {name}: {old or '(none)'} -> {new or '(none)'}"
            for name, (old, new) in result.changed.items()
        )
    if not result.has_unexpected_changes:
        lines.append("OK: no unexpected SBOM changes (added/removed components).")
    else:
        lines.append(
            "FAIL: unexpected SBOM changes - review the added/removed"
            " components above, then update the baseline with"
            " --update-baseline if the changes are expected."
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the SBOM comparison tool.

    Returns
    -------
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Compare the current CycloneDX JSON SBOM against a committed"
            " baseline and fail on added/removed components (unexpected"
            " changes). Version-only updates are reported informationally."
        )
    )
    parser.add_argument(
        "--sbom",
        default=str(DEFAULT_SBOM_PATH),
        help=f"Path to the current CycloneDX JSON SBOM (default: {DEFAULT_SBOM_PATH})",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE_PATH),
        help=f"Path to the committed baseline SBOM (default: {DEFAULT_BASELINE_PATH})",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help=(
            "Regenerate the baseline from the current SBOM (trimmed to its"
            " components) instead of comparing"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the SBOM comparison command-line flow.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]`` when None.

    Returns
    -------
        0 on no unexpected changes (or baseline absent/updated), 1 on
        unexpected changes, 2 on operational errors.
    """
    args = build_parser().parse_args(argv)
    sbom_path = Path(args.sbom).resolve()
    baseline_path = Path(args.baseline).resolve()

    try:
        if args.update_baseline:
            count = write_baseline(sbom_path, baseline_path)
            print(f"Baseline updated: {baseline_path} ({count} components)")
            return EXIT_OK

        if not baseline_path.is_file():
            print(f"Notice: no SBOM baseline found at {baseline_path}.")
            print("Comparison skipped (exit 0) until a baseline is committed.")
            print("Record one with:")
            print(f"  {Path(__file__).name} --update-baseline")
            return EXIT_OK

        baseline_versions = component_versions(read_sbom_document(baseline_path))
        current_versions = component_versions(read_sbom_document(sbom_path))
    except SbomCompareError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR

    result = compare_components(baseline_versions, current_versions)
    print(render_report(result, baseline_versions, current_versions))
    return EXIT_UNEXPECTED_CHANGES if result.has_unexpected_changes else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
