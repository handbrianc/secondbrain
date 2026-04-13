# Golden Datasets

This directory contains golden datasets for quantitative testing of the SecondBrain CLI application.

## Purpose

Golden datasets are curated sets of input/output pairs used to:
- Validate model accuracy and consistency
- Measure performance regressions
- Test edge cases and boundary conditions
- Ensure deterministic behavior where expected

## Dataset Structure

Each dataset should follow this naming convention:
```
{domain}_{scenario}_{version}.json{z}
```

Examples:
- `search_simple_query_v1.json`
- `rag_complex_context_v2.json.gz`
- `embedding_similarity_test.json`

## Dataset Format

Datasets should be JSON files with the following structure:

```json
{
  "metadata": {
    "name": "Dataset Name",
    "version": "1.0.0",
    "created": "2026-04-12",
    "description": "Brief description of the dataset purpose",
    "tags": ["tag1", "tag2"]
  },
  "test_cases": [
    {
      "id": "test_case_1",
      "input": {
        "query": "search query here",
        "context": ["relevant context items"]
      },
      "expected_output": {
        "results": [...],
        "metrics": {
          "expected_score": 0.95,
          "threshold": 0.8
        }
      }
    }
  ]
}
```

## Adding New Datasets

1. Create a new JSON file following the format above
2. Document the dataset purpose in metadata
3. Include diverse test cases covering:
   - Normal cases
   - Edge cases
   - Error conditions
4. Add compression (.gz) for datasets > 1MB
5. Update this README with dataset summary

## Usage in Tests

```python
import json
from pathlib import Path

def load_golden_dataset(name: str) -> dict:
    """Load a golden dataset from the golden_datasets directory."""
    dataset_path = Path(__file__).parent / f"{name}.json"
    with open(dataset_path) as f:
        return json.load(f)

def test_with_golden_dataset():
    dataset = load_golden_dataset("search_simple_query_v1")
    for test_case in dataset["test_cases"]:
        result = run_search(test_case["input"])
        assert evaluate_similarity(result, test_case["expected_output"]) >= 0.8
```

## Maintenance

- Review datasets quarterly for relevance
- Version datasets when test criteria change
- Remove deprecated datasets with proper migration notes
