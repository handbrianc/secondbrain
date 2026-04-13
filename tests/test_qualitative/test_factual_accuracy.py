"""Factual accuracy tests with claim decomposition and verification."""

import re
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.mark.qualitative
@pytest.mark.factual
class TestFactVerification:
    @pytest.mark.parametrize(
        "claim",
        [
            pytest.param("fv_config_python_version", id="python_version"),
            pytest.param("fv_config_mongodb_version", id="mongodb_version"),
        ],
    )
    def test_configuration_facts(self, factual_claims: dict, claim: str) -> None:
        claim_data = self._get_claim(factual_claims, claim)
        assert claim_data["expected"]["verifiable"] is True
        assert claim_data["expected"]["source_required"] is True
        fact = claim_data["expected"]["fact"]
        source = claim_data["expected"]["source"]
        self._verify_fact_in_source(fact, source, claim_data["id"])

    @pytest.mark.parametrize(
        "claim",
        [
            pytest.param("fv_feature_embedding_model", id="embedding_model"),
            pytest.param("fv_feature_document_formats", id="document_formats"),
            pytest.param("fv_feature_vector_search", id="vector_search"),
        ],
    )
    def test_feature_facts(self, factual_claims: dict, claim: str) -> None:
        claim_data = self._get_claim(factual_claims, claim)
        assert claim_data["expected"]["verifiable"] is True
        assert claim_data["expected"]["source_required"] is True
        fact = claim_data["expected"]["fact"]
        source = claim_data["expected"]["source"]
        components = self._decompose_fact(fact)
        assert len(components) > 0
        self._verify_fact_in_source(fact, source, claim_data["id"])

    @pytest.mark.parametrize(
        "claim",
        [
            pytest.param("fv_limitation_no_github_actions", id="no_github_actions"),
            pytest.param("fv_limitation_local_processing", id="local_processing"),
        ],
    )
    def test_limitation_facts(self, factual_claims: dict, claim: str) -> None:
        claim_data = self._get_claim(factual_claims, claim)
        assert claim_data["expected"]["verifiable"] is True
        assert claim_data["expected"]["source_required"] is True
        fact = claim_data["expected"]["fact"]
        source = claim_data["expected"]["source"]
        self._verify_fact_in_source(fact, source, claim_data["id"])

    @pytest.mark.parametrize(
        "claim",
        [
            pytest.param("fv_dependency_docling", id="docling"),
            pytest.param(
                "fv_dependency_sentence_transformers", id="sentence_transformers"
            ),
            pytest.param("fv_dependency_ruff_linting", id="ruff_linting"),
        ],
    )
    def test_dependency_facts(self, factual_claims: dict, claim: str) -> None:
        claim_data = self._get_claim(factual_claims, claim)
        assert claim_data["expected"]["verifiable"] is True
        assert claim_data["expected"]["source_required"] is True
        fact = claim_data["expected"]["fact"]
        source = claim_data["expected"]["source"]
        dep_name, version_constraint = self._parse_dependency(fact)
        assert dep_name is not None
        assert version_constraint is not None
        self._verify_dependency_in_pyproject(
            dep_name, version_constraint, claim_data["id"]
        )

    def _get_claim(self, factual_claims: dict, claim_id: str) -> dict[str, Any]:
        for claim in factual_claims["test_cases"]:
            if claim["id"] == claim_id:
                return claim
        raise ValueError(f"Claim {claim_id} not found")

    def _decompose_fact(self, fact: str) -> list[str]:
        components = re.split(r"[,\-;]", fact)
        return [c.strip() for c in components if c.strip()]

    def _parse_dependency(self, fact: str) -> tuple[str | None, str | None]:
        match = re.match(r"^([a-zA-Z0-9_-]+)([>=<]+[\d.]+.*)$", fact)
        if match:
            return match.group(1), match.group(2)
        return None, None

    def _verify_fact_in_source(self, fact: str, source: str, claim_id: str) -> None:
        source_path = None
        if "pyproject.toml" in source:
            source_path = PROJECT_ROOT / "pyproject.toml"
        elif "README.md" in source:
            source_path = PROJECT_ROOT / "README.md"
        elif "AGENTS.md" in source:
            source_path = PROJECT_ROOT / "AGENTS.md"
        assert source_path is not None, f"Unknown source: {source}"
        assert source_path.exists(), f"Source file not found: {source_path}"
        source_content = source_path.read_text(encoding="utf-8")
        source_lower = source_content.lower()
        
        # Handle version constraints specially
        if ">=" in fact or "<=" in fact or "==" in fact:
            # Extract version pattern and check if it exists
            import re
            version_match = re.search(r'[>=<]+[\d.]+', fact)
            if version_match:
                version_pattern = version_match.group()
                assert version_pattern in source_content, (
                    f"Version constraint '{version_pattern}' not found in {source_path.name}"
                )
        else:
            # For other facts, check key terms
            key_terms = self._decompose_fact(fact)
            found_terms = sum(1 for term in key_terms if term.lower() in source_lower)
            assert found_terms >= len(key_terms) * 0.5, (
                f"Fact '{fact}' not sufficiently found in {source_path.name}. "
                f"Found {found_terms}/{len(key_terms)} terms"
            )

    def _verify_dependency_in_pyproject(
        self, dep_name: str, version: str, claim_id: str
    ) -> None:
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        assert pyproject_path.exists()
        content = pyproject_path.read_text(encoding="utf-8")
        pattern = rf"{re.escape(dep_name)}\s*{re.escape(version)}"
        assert re.search(pattern, content), (
            f"Dependency '{dep_name}{version}' not found in pyproject.toml"
        )
