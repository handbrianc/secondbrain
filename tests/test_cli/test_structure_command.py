"""Tests for the ``secondbrain structure`` inspector command.

Exercises the Click command end-to-end through ``CliRunner`` against a real
:class:`StructureStore` on a tmp_path database: treeful rendering, the
``--json`` dump, treeless re-ingest guidance, unknown-source errors, and the
source_file resolution fallbacks (verbatim key, relative/absolute spelling,
unambiguous basename/suffix match, ambiguity error).
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from secondbrain.cli import cli
from secondbrain.cli.structure import ResolvedSource, resolve_source_file
from secondbrain.storage.structure_sqlite import (
    AudioSegment,
    DocumentStructure,
    PageLabelRange,
    StructureNode,
    StructureStore,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

DOC_KEY = "/data/uploads/hcd.pdf"


@pytest.fixture()
def structure_db(tmp_path):
    """A real structure store on an isolated tmp_path SQLite file."""
    return StructureStore(db_path=str(tmp_path / "structures.db"))


def _install_cli_stores(
    monkeypatch: pytest.MonkeyPatch,
    structure_db: StructureStore,
    stored_keys: list[str],
) -> None:
    """Point the command's store/key factories at the test doubles.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        structure_db: The tmp_path structure store the command should open.
        stored_keys: The vector-store ``source_file`` enumeration result.
    """
    monkeypatch.setattr(
        "secondbrain.cli.structure._open_structure_store",
        lambda: structure_db,
    )
    monkeypatch.setattr(
        "secondbrain.cli.structure._list_source_keys",
        lambda: list(stored_keys),
    )


def _sample_structure(source_file: str) -> DocumentStructure:
    """Build a treeful structure: two heading nodes + labels + audio."""
    return DocumentStructure(
        source_file=source_file,
        nodes=[
            StructureNode(
                node_id="ch01",
                parent_id=None,
                kind="chapter",
                level=1,
                number="1",
                title="Introduction",
                page_start=1,
                page_end=6,
                heading_path="Chapter 1 — Introduction",
            ),
            StructureNode(
                node_id="sec01.02",
                parent_id="ch01",
                kind="section",
                level=2,
                number="1.2",
                title="Scope",
                page_start=3,
                page_end=6,
                heading_path="Chapter 1 — Introduction > 1.2",
            ),
            StructureNode(
                node_id="seg00",
                parent_id=None,
                kind="segment",
                level=1,
                title="Welcome",
                t_start=0.0,
                t_end=83.0,
                heading_path="Welcome",
            ),
        ],
        page_labels=[
            PageLabelRange(page_start=1, page_end=2, label="i", style="roman"),
            PageLabelRange(page_start=3, page_end=6, label="1"),
        ],
        audio_segments=[
            AudioSegment(seg_id=0, t_start=0.0, t_end=83.0, title="Welcome")
        ],
        sources={
            "outline": True,
            "heading_hierarchy": True,
            "page_labels": True,
            "audio": False,
        },
        captured_at="2026-10-24T00:00:00+00:00",
    )


def _invoke(*args: str) -> Result:
    """Run the structure command through CliRunner."""
    return CliRunner().invoke(cli, ["structure", *args])


class TestTreefulRender:
    """Tests for the rendered tree / page-label / audio output."""

    def test_renders_tree_page_labels_and_audio(
        self, structure_db, monkeypatch
    ) -> None:
        """A stored tree renders nodes, ranges, printed labels and segments."""
        structure_db.save_structure(_sample_structure(DOC_KEY))
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY)

        assert result.exit_code == 0
        assert DOC_KEY in result.output
        assert "chapter 1 — Introduction" in result.output
        assert "section 1.2 — Scope" in result.output
        # Page ranges on the shared 1-based physical-page axis.
        assert "pp. 1–6" in result.output  # noqa: RUF001 - display format
        assert "pp. 3–6" in result.output  # noqa: RUF001 - display format
        # Printed labels resolved from the stored /PageLabels runs.
        assert "printed i–1" in result.output  # noqa: RUF001 - display format
        assert "printed 1" in result.output
        # The page-label table.
        assert "Printed page labels" in result.output
        assert "1–2" in result.output  # noqa: RUF001 - display format
        assert "roman" in result.output
        # Audio: tree node times and the segments table (mm:ss).
        assert "00:00–01:23" in result.output  # noqa: RUF001 - display format
        assert "Audio segments" in result.output
        assert "Welcome" in result.output

    def test_exact_source_key_matches_verbatim(self, structure_db, monkeypatch) -> None:
        """The stored key resolves without consulting the vector store."""
        key = "docs/hcd.pdf"  # relative key, exactly as ingested
        structure_db.save_structure(_sample_structure(key))
        # Enumeration unavailable (vector store down): exact match still works.
        _install_cli_stores(monkeypatch, structure_db, [])

        result = _invoke(key)

        assert result.exit_code == 0
        assert "chapter 1 — Introduction" in result.output

    def test_relative_argument_matches_absolute_stored_key(
        self, structure_db, monkeypatch, tmp_path
    ) -> None:
        """A relative spelling resolves via the absolute path variant."""
        key = str(tmp_path / "hcd.pdf")
        structure_db.save_structure(_sample_structure(key))
        _install_cli_stores(monkeypatch, structure_db, [key])
        monkeypatch.chdir(tmp_path)

        result = _invoke("hcd.pdf")

        assert result.exit_code == 0
        # Long absolute keys wrap in the 80-column capture (mid-word), so
        # assert on the rendered tree content.
        assert "chapter 1 — Introduction" in result.output
        # And pin the exact variant resolution directly.
        resolved = resolve_source_file(structure_db, "hcd.pdf", [key])
        assert resolved.source_file == key

    def test_basename_fallback_resolves_unique_match(
        self, structure_db, monkeypatch
    ) -> None:
        """A bare filename resolves when exactly one ingested key matches."""
        structure_db.save_structure(_sample_structure(DOC_KEY))
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke("hcd.pdf")

        assert result.exit_code == 0
        assert DOC_KEY in result.output
        assert "chapter 1 — Introduction" in result.output

    def test_suffix_fallback_resolves_relative_tail(
        self, structure_db, monkeypatch
    ) -> None:
        """A relative path tail resolves against an absolute stored key."""
        structure_db.save_structure(_sample_structure(DOC_KEY))
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke("uploads/hcd.pdf")

        assert result.exit_code == 0
        assert DOC_KEY in result.output


class TestResolveSourceFile:
    """Unit tests pinning the exact source_file resolution logic."""

    def test_exact_key_wins(self, structure_db) -> None:
        """The verbatim stored key resolves before anything else."""
        structure_db.save_structure(_sample_structure(DOC_KEY))

        resolved = resolve_source_file(structure_db, DOC_KEY, [])

        assert resolved == ResolvedSource(source_file=DOC_KEY)

    def test_suffix_requires_path_boundary(self, structure_db) -> None:
        """A suffix match never crosses a component boundary."""
        structure_db.save_structure(_sample_structure("/data/x/max.pdf"))

        # "x/max.pdf" matches the key at a path boundary ...
        hit = resolve_source_file(structure_db, "x/max.pdf", ["/data/x/max.pdf"])
        # ... but never inside a longer component such as "xmax.pdf".
        miss = resolve_source_file(structure_db, "x/max.pdf", ["/data/xmax.pdf"])

        assert hit.source_file == "/data/x/max.pdf"
        assert miss.source_file is None

    def test_treeful_candidate_preferred_over_treeless(self, structure_db) -> None:
        """Among ambiguous basenames, the one holding a tree resolves."""
        structure_db.save_structure(_sample_structure("/a/report.pdf"))
        keys = ["/a/report.pdf", "/b/report.pdf"]

        resolved = resolve_source_file(structure_db, "report.pdf", keys)

        assert resolved.source_file == "/a/report.pdf"

    @pytest.mark.parametrize("doc", ["/a/report.pdf", "a/report.pdf"])
    def test_stronger_treeless_match_wins(self, structure_db, doc) -> None:
        structure_db.save_structure(_sample_structure("/b/report.pdf"))

        resolved = resolve_source_file(
            structure_db, doc, ["/a/report.pdf", "/b/report.pdf"]
        )

        assert resolved.source_file == "/a/report.pdf"

    def test_exact_treeless_key_wins_over_normalized_tree(
        self, structure_db, tmp_path
    ) -> None:
        normalized = str(tmp_path / "report.pdf")
        verbatim = str(tmp_path) + "/./report.pdf"
        structure_db.save_structure(_sample_structure(normalized))

        resolved = resolve_source_file(structure_db, verbatim, [verbatim, normalized])

        assert resolved.source_file == verbatim

    def test_unavailable_enumeration_means_unknown(self, structure_db) -> None:
        """With enumeration unavailable, only exact/variant hits resolve."""
        structure_db.save_structure(_sample_structure(DOC_KEY))

        resolved = resolve_source_file(structure_db, "hcd.pdf", None)

        assert resolved.source_file is None
        assert resolved.candidates == []

    def test_empty_argument_is_unknown(self, structure_db) -> None:
        """An empty argument never resolves."""
        resolved = resolve_source_file(structure_db, "", [DOC_KEY])

        assert resolved.source_file is None


class TestAmbiguousMatch:
    """Tests for ambiguous basename/suffix fallbacks."""

    def test_ambiguous_basenames_error_and_list_candidates(
        self, structure_db, monkeypatch
    ) -> None:
        """Several treeful matches fail with the candidate list."""
        first = "/a/report.pdf"
        second = "/b/report.pdf"
        structure_db.save_structure(_sample_structure(first))
        structure_db.save_structure(_sample_structure(second))
        _install_cli_stores(monkeypatch, structure_db, [first, second])

        result = _invoke("report.pdf")

        assert result.exit_code != 0
        assert "matches multiple stored source files" in result.output
        assert first in result.output
        assert second in result.output
        assert "has stored tree" in result.output


class TestTreelessGuidance:
    """Tests for ingested documents without a stored tree."""

    def test_treeless_document_prints_reingest_guidance(
        self, structure_db, monkeypatch
    ) -> None:
        """An ingested but treeless document gets guidance and exits 0."""
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY)

        assert result.exit_code == 0
        assert "No stored structure tree" in result.output
        assert "secondbrain ingest" in result.output
        assert DOC_KEY in result.output
        assert "--no-skip-existing" not in result.output

    def test_json_flag_on_treeless_document_still_guides(
        self, structure_db, monkeypatch
    ) -> None:
        """--json cannot dump a missing tree; the guidance is shown instead."""
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY, "--json")

        assert result.exit_code == 0
        assert "No stored structure tree" in result.output


class TestUnknownSource:
    """Tests for arguments that match no stored source."""

    def test_unknown_source_errors_nonzero(self, structure_db, monkeypatch) -> None:
        """An argument matching nothing fails cleanly."""
        _install_cli_stores(monkeypatch, structure_db, ["/data/other.pdf"])

        result = _invoke("/data/missing.pdf")

        assert result.exit_code != 0
        assert "no stored document matches" in result.output

    def test_unknown_source_lists_stored_paths_hint(
        self, structure_db, monkeypatch
    ) -> None:
        """The error points users at the stored source paths."""
        _install_cli_stores(monkeypatch, structure_db, ["/data/other.pdf"])

        result = _invoke("missing.pdf")

        assert result.exit_code != 0
        assert "secondbrain ls --all" in result.output


class TestJsonOutput:
    """Tests for the --json raw DocumentStructure dump."""

    def test_json_dump_shape(self, structure_db, monkeypatch) -> None:
        """--json prints the raw stored structure as parseable JSON."""
        structure_db.save_structure(_sample_structure(DOC_KEY))
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY, "--json")

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert set(data) == {
            "source_file",
            "nodes",
            "page_labels",
            "audio_segments",
            "sources",
            "captured_at",
        }
        assert data["source_file"] == DOC_KEY
        assert data["sources"]["outline"] is True
        assert data["sources"]["audio"] is False
        assert data["captured_at"] == "2026-10-24T00:00:00+00:00"
        assert [node["node_id"] for node in data["nodes"]] == [
            "ch01",
            "sec01.02",
            "seg00",
        ]
        assert data["nodes"][0]["page_start"] == 1
        assert data["page_labels"][0]["label"] == "i"
        assert data["audio_segments"][0]["t_end"] == 83.0

    def test_json_dump_of_audio_only_structure(self, structure_db, monkeypatch) -> None:
        """Audio-only trees dump without node page fields set."""
        structure_db.save_structure(
            DocumentStructure(
                source_file=DOC_KEY,
                nodes=[
                    StructureNode(
                        node_id="seg00",
                        parent_id=None,
                        kind="segment",
                        level=1,
                        title="Talk",
                        t_start=10.0,
                        t_end=75.5,
                        heading_path="Talk",
                    )
                ],
                audio_segments=[AudioSegment(seg_id=0, t_start=10.0, t_end=75.5)],
                sources={"audio": True},
            )
        )
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY, "--json")

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["nodes"][0]["page_start"] is None
        assert data["nodes"][0]["t_start"] == 10.0
        assert data["audio_segments"][0]["t_end"] == 75.5

    def test_json_output_is_the_only_payload(self, structure_db, monkeypatch) -> None:
        """--json with a stored tree prints nothing but the JSON document."""
        structure_db.save_structure(_sample_structure(DOC_KEY))
        _install_cli_stores(monkeypatch, structure_db, [DOC_KEY])

        result = _invoke(DOC_KEY, "--json")

        assert result.exit_code == 0
        json.loads(result.output)  # the whole captured output is one document


class TestCommandRegistration:
    """Tests that the command is wired onto the CLI group."""

    def test_structure_help(self) -> None:
        """The registered command exposes its argument and option."""
        result = _invoke("--help")

        assert result.exit_code == 0
        assert "DOC" in result.output
        assert "--json" in result.output


class TestDocsCoverage:
    """Docs-completeness checks for the new command (keeps docs green)."""

    def test_structure_command_documented(self) -> None:
        """The CLI reference, user guide, nav and README mention it."""
        reference = (REPO_ROOT / "docs/user-guide/cli-reference.md").read_text(
            encoding="utf-8"
        )
        assert "## structure" in reference
        assert "--json" in reference

        guide = (REPO_ROOT / "docs/user-guide/document-structure.md").read_text(
            encoding="utf-8"
        )
        assert "secondbrain structure" in guide
        assert "secondbrain ingest <path>" in guide
        assert "--no-skip-existing" not in guide

        mkdocs = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
        assert "user-guide/document-structure.md" in mkdocs

        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        assert "secondbrain structure" in readme
