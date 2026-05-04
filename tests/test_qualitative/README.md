# Qualitative Testing Framework

## Overview

This directory contains the foundation for qualitative testing of the SecondBrain document intelligence system. Qualitative tests evaluate:

- **Safety**: Detection and handling of PII, dangerous topics, and harmful content
- **Factual Accuracy**: Verification of factual claims and hallucination detection
- **Citation Quality**: Proper attribution and source citation
- **Robustness**: Handling of edge cases, ambiguous queries, and adversarial inputs
- **LLM Judge Evaluation**: Automated evaluation using LLM-based judges

## Directory Structure

```
test_qualitative/
├── __init__.py              # Package marker
├── conftest.py              # Shared fixtures for loading test data
├── README.md                # This file
└── test_*.py                # Test implementations (to be created)

../data/qualitative/
├── pii_patterns.json        # PII detection patterns and test cases
├── dangerous_topics.json    # Dangerous topic classifications
├── factual_claims.json      # Factual claims for verification
├── citation_templates.json  # Citation format templates
├── edge_case_queries.json   # Edge case and adversarial queries
└── llm_judge_prompts.json   # LLM judge evaluation prompts
```

## Fixtures

The `conftest.py` module provides the following fixtures:

### `pii_patterns`
Load PII patterns for testing sensitive data detection.

```python
def test_pii_detection(pii_patterns):
    for pattern in pii_patterns["test_cases"]:
        # Test PII detection logic
        pass
```

### `dangerous_topics`
Load dangerous topics for testing safety filters.

```python
def test_dangerous_topic_filter(dangerous_topics):
    for topic in dangerous_topics["test_cases"]:
        # Test topic filtering
        pass
```

### `factual_claims`
Load factual claims for verification testing.

```python
def test_factual_accuracy(factual_claims):
    for claim in factual_claims["test_cases"]:
        # Test factual verification
        pass
```

### `citation_templates`
Load citation templates for citation quality testing.

```python
def test_citation_quality(citation_templates):
    for template in citation_templates["test_cases"]:
        # Test citation generation
        pass
```

### `edge_case_queries`
Load edge case queries for robustness testing.

```python
def test_edge_case_handling(edge_case_queries):
    for query in edge_case_queries["test_cases"]:
        # Test edge case handling
        pass
```

### `llm_judge_prompts`
Load LLM judge prompts for automated evaluation.

```python
def test_llm_judge_evaluation(llm_judge_prompts):
    for prompt in llm_judge_prompts["test_cases"]:
        # Test LLM judge evaluation
        pass
```

## JSON Schema

All JSON files follow a consistent schema:

```json
{
  "metadata": {
    "version": "1.0.0",
    "description": "Description of the dataset",
    "created": "2026-04-12",
    "last_updated": "2026-04-12"
  },
  "test_cases": [
    {
      "id": "unique_identifier",
      "description": "Test case description",
      "input": "Input data",
      "expected": "Expected output or behavior",
      "category": "category_name",
      "severity": "low|medium|high|critical"
    }
  ]
}
```

## Pytest Markers

Qualitative tests use the following markers (configured in `pyproject.toml`):

- `@pytest.mark.safety`: Tests for safety-related functionality (PII, dangerous topics)
- `@pytest.mark.factual`: Tests for factual accuracy and hallucination detection
- `@pytest.mark.hallucination`: Tests specifically for hallucination detection
- `@pytest.mark.robustness`: Tests for edge cases and adversarial inputs
- `@pytest.mark.llm_judge`: Tests using LLM-based evaluation

Example:
```python
import pytest

@pytest.mark.safety
@pytest.mark.pii
def test_pii_detection(pii_patterns):
    pass

@pytest.mark.factual
@pytest.mark.hallucination
def test_hallucination_detection(factual_claims):
    pass
```

## Running Qualitative Tests

```bash
# Run all qualitative tests
pytest tests/test_qualitative/

# Run with specific markers
pytest -m "safety" tests/test_qualitative/
pytest -m "factual" tests/test_qualitative/
pytest -m "hallucination" tests/test_qualitative/
pytest -m "robustness" tests/test_qualitative/
pytest -m "llm_judge" tests/test_qualitative/

# Run with coverage
pytest --cov=secondbrain tests/test_qualitative/

# Run specific test file
pytest tests/test_qualitative/test_safety.py
```

## Test Categories

### 1. Safety Tests (`test_safety.py`)
- PII detection and redaction
- Dangerous topic filtering
- Harmful content prevention

### 2. Factual Accuracy Tests (`test_factual.py`)
- Factual claim verification
- Hallucination detection
- Source attribution accuracy

### 3. Citation Tests (`test_citations.py`)
- Citation format compliance
- Source linking accuracy
- Reference completeness

### 4. Robustness Tests (`test_robustness.py`)
- Edge case handling
- Adversarial query resistance
- Ambiguous query resolution

### 5. LLM Judge Tests (`test_llm_judge.py`)
- Automated quality evaluation
- Response relevance scoring
- Safety assessment automation

## Adding New Test Cases

To add new test cases to a JSON file:

1. Open the relevant JSON file in `tests/data/qualitative/`
2. Add a new test case to the `test_cases` array
3. Ensure all required fields are present:
   - `id`: Unique identifier (use format: `category_description`)
   - `description`: Clear description of what's being tested
   - `input`: The input data or query
   - `expected`: Expected output or behavior
   - `category`: Category classification
   - `severity`: Priority level (low, medium, high, critical)

Example:
```json
{
  "id": "pii_email_detection",
  "description": "Detect email addresses in document text",
  "input": "Contact us at support@example.com for help",
  "expected": "Email address should be detected and redacted",
  "category": "email",
  "severity": "high"
}
```

## Dependencies

Install qualitative testing dependencies:

```bash
pip install -e ".[qualitative]"
```

The `qualitative` extra includes:
- `llama-cpp-python` - For local LLM judge evaluation
- `transformers` - For advanced NLP tasks
- Additional evaluation libraries as needed

## Best Practices

1. **Use descriptive IDs**: Make test case IDs self-documenting
2. **Categorize properly**: Use appropriate categories for filtering
3. **Set severity correctly**: High/critical for safety issues
4. **Keep inputs realistic**: Use real-world examples
5. **Define clear expectations**: Expected outputs should be unambiguous
6. **Version your datasets**: Track changes in metadata
7. **Review regularly**: Update test cases as system evolves

## Future Work

- [ ] Implement safety tests (Task 2)
- [ ] Implement factual accuracy tests (Task 3)
- [ ] Implement citation tests (Task 4)
- [ ] Implement robustness tests (Task 5)
- [ ] Implement LLM judge tests (Task 6)
- [ ] Add more test cases to JSON datasets
- [ ] Integrate with CI/CD pipeline
