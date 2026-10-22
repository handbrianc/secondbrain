"""Tests for scripts/sbom_compare.py (CycloneDX SBOM baseline comparison)."""

import json
from pathlib import Path
from typing import Any

from scripts.sbom_compare import (
    ComparisonResult,
    compare_components,
    component_versions,
    main,
    write_baseline,
)


def _component(name: str, version: str) -> dict[str, Any]:
    """Build a minimal CycloneDX component entry."""
    return {"type": "library", "name": name, "version": version}


def _sbom_doc(components: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal CycloneDX JSON SBOM document."""
    return {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": components}


def _write_json(path: Path, document: dict[str, Any]) -> Path:
    """Write a JSON document to path and return the path."""
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


class TestCompareComponents:
    """Unit tests for the pure comparison logic."""

    def test_no_change_yields_no_unexpected_changes(self) -> None:
        """Identical baseline and current maps report no changes."""
        result = compare_components({"click": "8.5.0"}, {"click": "8.5.0"})
        assert result.added == []
        assert result.removed == []
        assert result.changed == {}
        assert not result.has_unexpected_changes

    def test_added_component_is_reported(self) -> None:
        """A component only present in current is reported as added."""
        result = compare_components(
            {"click": "8.5.0"}, {"click": "8.5.0", "mcp": "1.0"}
        )
        assert result.added == ["mcp"]
        assert result.has_unexpected_changes

    def test_removed_component_is_reported(self) -> None:
        """A component only present in baseline is reported as removed."""
        result = compare_components(
            {"click": "8.5.0", "mcp": "1.0"}, {"click": "8.5.0"}
        )
        assert result.removed == ["mcp"]
        assert result.has_unexpected_changes

    def test_version_change_is_informational_only(self) -> None:
        """A version bump does not count as an unexpected change."""
        result = compare_components({"click": "8.4.0"}, {"click": "8.5.0"})
        assert result.added == []
        assert result.removed == []
        assert result.changed == {"click": ("8.4.0", "8.5.0")}
        assert not result.has_unexpected_changes

    def test_component_names_are_case_insensitive(self) -> None:
        """Name matching is case-insensitive (normalized names)."""
        result = compare_components({"Click": "8.5.0"}, {"click": "8.5.0"})
        assert not result.has_unexpected_changes


class TestComponentVersions:
    """Unit tests for SBOM document parsing."""

    def test_extracts_name_version_map(self) -> None:
        """Component entries are reduced to a name -> version map."""
        document = _sbom_doc(
            [_component("Click", "8.5.0"), _component("rich", "15.0.0")]
        )
        assert component_versions(document) == {"click": "8.5.0", "rich": "15.0.0"}

    def test_missing_version_maps_to_empty_string(self) -> None:
        """Entries without a version map to the empty string."""
        document = _sbom_doc([{"type": "library", "name": "odd-package"}])
        assert component_versions(document) == {"odd-package": ""}

    def test_skips_entries_without_name(self) -> None:
        """Entries lacking a name are ignored instead of crashing."""
        document = _sbom_doc([{"type": "library", "version": "1.0"}])
        assert component_versions(document) == {}


class TestMain:
    """End-to-end tests through the CLI entry point."""

    def test_no_change_passes(self, tmp_path: Path) -> None:
        """Identical SBOM and baseline exit 0."""
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("click", "8.5.0")])
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 0

    def test_added_component_fails(self, tmp_path: Path) -> None:
        """An added component exits 1."""
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("click", "8.5.0")])
        )
        sbom = _write_json(
            tmp_path / "sbom.json",
            _sbom_doc([_component("click", "8.5.0"), _component("mcp", "1.0")]),
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 1

    def test_removed_component_fails(self, tmp_path: Path) -> None:
        """A removed component exits 1."""
        baseline = _write_json(
            tmp_path / "baseline.json",
            _sbom_doc([_component("click", "8.5.0"), _component("rich", "15.0.0")]),
        )
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 1

    def test_added_and_removed_reported_in_output(
        self, tmp_path: Path, capsys: Any
    ) -> None:
        """The report names the added and removed components."""
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("rich", "15.0.0")])
        )
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 1
        output = capsys.readouterr().out
        assert "ADDED components" in output
        assert "click" in output
        assert "REMOVED components" in output
        assert "rich" in output

    def test_version_change_passes(self, tmp_path: Path) -> None:
        """A version-only bump exits 0 and is reported informationally."""
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("click", "8.4.0")])
        )
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 0

    def test_missing_baseline_notices_and_exits_zero(self, tmp_path: Path) -> None:
        """No baseline yet: notice printed, exit 0 so CI stays green."""
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        assert (
            main(["--sbom", str(sbom), "--baseline", str(tmp_path / "none.json")]) == 0
        )

    def test_missing_sbom_is_an_error(self, tmp_path: Path) -> None:
        """A missing current SBOM is an operational error (exit 2)."""
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("click", "8.5.0")])
        )
        missing = tmp_path / "missing.json"
        assert main(["--sbom", str(missing), "--baseline", str(baseline)]) == 2

    def test_invalid_json_is_an_error(self, tmp_path: Path) -> None:
        """Malformed JSON in the current SBOM is an operational error (exit 2)."""
        baseline = _write_json(
            tmp_path / "baseline.json", _sbom_doc([_component("click", "8.5.0")])
        )
        sbom = tmp_path / "sbom.json"
        sbom.write_text("{not json", encoding="utf-8")
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 2

    def test_document_without_components_is_an_error(self, tmp_path: Path) -> None:
        """A document lacking a components array is an operational error."""
        baseline = _write_json(tmp_path / "baseline.json", {"bomFormat": "CycloneDX"})
        sbom = _write_json(tmp_path / "sbom.json", {"bomFormat": "CycloneDX"})
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 2


class TestUpdateBaseline:
    """Tests for the --update-baseline flow."""

    def test_update_baseline_writes_trimmed_sorted_components(
        self, tmp_path: Path
    ) -> None:
        """The baseline keeps only components, sorted, without volatile fields."""
        sbom = _write_json(
            tmp_path / "sbom.json",
            {
                "serialNumber": "urn:uuid:volatile",
                "metadata": {"timestamp": "2026-10-22T00:00:00Z"},
                "bomFormat": "CycloneDX",
                "components": [
                    _component("rich", "15.0.0"),
                    _component("click", "8.5.0"),
                ],
            },
        )
        baseline = tmp_path / "baseline.json"
        assert (
            main(
                ["--update-baseline", "--sbom", str(sbom), "--baseline", str(baseline)]
            )
            == 0
        )
        written = json.loads(baseline.read_text(encoding="utf-8"))
        assert set(written) == {"components"}
        assert written["components"] == [
            _component("click", "8.5.0"),
            _component("rich", "15.0.0"),
        ]

    def test_update_then_compare_detects_new_change(self, tmp_path: Path) -> None:
        """After updating the baseline, a later addition is detected."""
        sbom = _write_json(
            tmp_path / "sbom.json", _sbom_doc([_component("click", "8.5.0")])
        )
        baseline = tmp_path / "baseline.json"
        assert (
            main(
                ["--update-baseline", "--sbom", str(sbom), "--baseline", str(baseline)]
            )
            == 0
        )
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 0

        current = json.loads(sbom.read_text(encoding="utf-8"))
        current["components"].append(_component("mcp", "1.0"))
        sbom.write_text(json.dumps(current, indent=2), encoding="utf-8")
        assert main(["--sbom", str(sbom), "--baseline", str(baseline)]) == 1

    def test_write_baseline_helper_counts_components(self, tmp_path: Path) -> None:
        """write_baseline returns the number of components written."""
        sbom = _write_json(
            tmp_path / "sbom.json",
            _sbom_doc([_component("click", "8.5.0"), _component("rich", "15.0.0")]),
        )
        assert write_baseline(sbom, tmp_path / "baseline.json") == 2

    def test_update_baseline_with_missing_sbom_is_error(self, tmp_path: Path) -> None:
        """--update-baseline without a current SBOM is an operational error."""
        assert (
            main(
                [
                    "--update-baseline",
                    "--sbom",
                    str(tmp_path / "missing.json"),
                    "--baseline",
                    str(tmp_path / "baseline.json"),
                ]
            )
            == 2
        )


def test_comparison_result_defaults_are_frozen() -> None:
    """ComparisonResult is an immutable value object."""
    result = ComparisonResult(added=[], removed=[], changed={})
    assert not result.has_unexpected_changes
