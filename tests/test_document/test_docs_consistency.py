"""Docs-consistency checks for the ingestion-performance configuration surface.

Verifies that the configuration settings and CLI flags added by the
ingestion-performance plan are documented, and that the CLI exposes the
expected flags. Fast, non-integration tests.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from secondbrain.cli import cli

REPO_ROOT = Path(__file__).resolve().parents[2]

CONFIGURATION_DOC = REPO_ROOT / "docs/getting-started/configuration.md"
README = REPO_ROOT / "README.md"
CLI_REFERENCE = REPO_ROOT / "docs/user-guide/cli-reference.md"
INGEST_CLI = REPO_ROOT / "src/secondbrain/cli/ingest.py"


@pytest.mark.parametrize(
    "setting",
    [
        "pdf_ocr_enabled",
        "pdf_table_structure_enabled",
        "ingest_pool",
        "skip_existing_on_reingest",
    ],
)
def test_new_settings_documented(setting: str) -> None:
    content = CONFIGURATION_DOC.read_text(encoding="utf-8")
    assert setting in content


@pytest.mark.parametrize(
    "env_var",
    [
        "SECONDBRAIN_INGEST_POOL",
        "SECONDBRAIN_PDF_OCR_ENABLED",
        "SECONDBRAIN_PDF_TABLE_STRUCTURE_ENABLED",
        "SECONDBRAIN_SKIP_EXISTING_ON_REINGEST",
    ],
)
def test_env_vars_documented_in_readme(env_var: str) -> None:
    content = README.read_text(encoding="utf-8")
    assert env_var in content
    assert env_var in CONFIGURATION_DOC.read_text(encoding="utf-8")


@pytest.mark.parametrize("flag", ["--pool", "--no-skip-existing"])
def test_cli_flags_in_docs(flag: str) -> None:
    cli_reference = CLI_REFERENCE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    assert flag in cli_reference or flag in readme


def test_cli_flags_present_in_source() -> None:
    content = INGEST_CLI.read_text(encoding="utf-8")
    assert "--pool" in content
    assert "--no-skip-existing" in content


def test_ingest_help_lists_new_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "--pool" in result.output
    assert "--no-skip-existing" in result.output
