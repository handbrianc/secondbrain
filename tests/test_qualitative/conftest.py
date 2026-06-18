"""
Shared fixtures for qualitative testing framework.

This module provides pytest fixtures for loading qualitative test data
from JSON files in the tests/data/qualitative/ directory, plus mock LLM
fixtures for running tests without external services.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

# Base path for qualitative test data
QUALITATIVE_DATA_PATH = Path(__file__).parent.parent / "data" / "qualitative"


@pytest.fixture(scope="session")
def mock_llm_for_qualitative():
    """Provide mock LLM provider for qualitative tests.

    Returns:
        MockLLMProviderWithContext instance for consistent testing.
    """
    from secondbrain.rag.providers.mock import MockLLMProviderWithContext

    return MockLLMProviderWithContext()


@pytest.fixture(scope="session")
def pii_patterns():
    """
    Load PII (Personally Identifiable Information) patterns from JSON.

    Returns:
        dict: PII patterns with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "pii_patterns.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def dangerous_topics():
    """
    Load dangerous topics from JSON.

    Returns:
        dict: Dangerous topics with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "dangerous_topics.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def factual_claims():
    """
    Load factual claims from JSON.

    Returns:
        dict: Factual claims with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "factual_claims.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def citation_templates():
    """
    Load citation templates from JSON.

    Returns:
        dict: Citation templates with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "citation_templates.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def edge_case_queries():
    """
    Load edge case queries from JSON.

    Returns:
        dict: Edge case queries with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "edge_case_queries.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def llm_judge_prompts():
    """
    Load LLM judge prompts from JSON.

    Returns:
        dict: LLM judge prompts with metadata and test cases
    """
    file_path = QUALITATIVE_DATA_PATH / "llm_judge_prompts.json"
    with open(file_path, encoding="utf-8") as f:
        return json.load(f)



