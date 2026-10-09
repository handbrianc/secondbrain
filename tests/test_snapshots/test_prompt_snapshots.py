"""Golden-file snapshot tests for RAG prompt assembly.

Pins the two text stages of the RAG prompt path against the golden files in
``tests/snapshots/`` so silent regressions in the prompt text sent to the
LLM are caught:

- ``RAGPipeline._format_context`` → ``context_assembly.json``'s
  ``expected_formatted_context``
- ``RAGPipeline._build_prompt``   → ``assembled_prompt.txt``

The pipeline runs over in-repo doubles (MagicMock searcher/provider — never
called by these methods); no network, no heavy mocking.
"""

from __future__ import annotations

from typing import Any

import pytest


def test_format_context_matches_golden(
    snapshot_pipeline: Any,
    sample_chunks: list[dict[str, Any]],
    expected_formatted_context: str,
) -> None:
    """_format_context reproduces the golden formatted context exactly."""
    assert (
        snapshot_pipeline._format_context(sample_chunks) == expected_formatted_context
    )


def test_build_prompt_matches_golden(
    snapshot_pipeline: Any,
    sample_chunks: list[dict[str, Any]],
    sample_query: str,
    expected_assembled_prompt: str,
) -> None:
    """The full format→assemble path reproduces the golden prompt exactly."""
    context = snapshot_pipeline._format_context(sample_chunks)
    prompt = snapshot_pipeline._build_prompt(sample_query, context)
    assert prompt == expected_assembled_prompt


def test_deliberate_content_change_diverges(
    snapshot_pipeline: Any,
    sample_chunks: list[dict[str, Any]],
    sample_query: str,
    expected_formatted_context: str,
    expected_assembled_prompt: str,
) -> None:
    """A deliberate change to chunk content diverges from both golden files."""
    tampered = [
        dict(sample_chunks[0], chunk_text="TAMPERED CHUNK CONTENT"),
        *sample_chunks[1:],
    ]

    formatted = snapshot_pipeline._format_context(tampered)
    assert formatted != expected_formatted_context

    prompt = snapshot_pipeline._build_prompt(sample_query, formatted)
    assert prompt != expected_assembled_prompt
    # The tampered text flows through to the prompt that reaches the LLM.
    assert "TAMPERED CHUNK CONTENT" in prompt


@pytest.mark.parametrize(
    ("marker", "label"),
    [
        ("=== DOCUMENT CONTEXT START ===", "context open delimiter"),
        ("=== DOCUMENT CONTEXT END ===", "context close delimiter"),
        ("Question: ", "question prefix"),
        ("Answer:", "answer cue"),
    ],
)
def test_golden_prompt_carries_structural_markers(
    expected_assembled_prompt: str, marker: str, label: str
) -> None:
    """The golden prompt keeps the structural markers _build_prompt emits."""
    assert marker in expected_assembled_prompt, f"golden prompt lost {label}"
