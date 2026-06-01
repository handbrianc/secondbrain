# Mutation Testing Guide

## Overview

Mutation testing verifies that your tests can catch real bugs by automatically introducing small changes (mutations) to the codebase and checking if tests fail.

**High mutation score = Tests are effective at catching errors**

## Setup

Mutation testing is configured in `pyproject.toml`:

```toml
[tool.mutmut]
python_paths = ["src"]
test_command = "pytest {mutmut_test_file} -xvs"
```

## Running Mutation Tests

### Full Mutation Testing (Recommended for CI/CD)

```bash
# Run mutation testing on entire codebase
python scripts/run-mutation-testing.py

# Or directly with mutmut
mutmut run
```

**⚠️ Warning**: Full mutation testing may take 30-60 minutes depending on test suite size.

### Quick Mutation Testing (Specific Module)

```bash
# Test only the RAG factory module
python scripts/run-mutation-testing.py quick secondbrain.rag.factory

# Or directly
mutmut run --paths-to-mutate secondbrain.rag.factory
```

### Viewing Results

```bash
# Show mutation testing summary
python scripts/run-mutation-testing.py results

# Or directly
mutmut results
```

### Interactive Browser

```bash
# Open interactive mutation browser
python scripts/run-mutation-testing.py browse

# Or directly
mutmut browse
```

## Understanding Results

### Mutation Score Categories

- **Killed**: Tests detected the mutation ✅ (Good!)
- **Survived**: Tests didn't detect the mutation ❌ (Need better tests)
- **Timeout**: Mutation caused test timeout ⚠️ (May need timeout adjustment)
- **Skipped**: Test was skipped ⚠️ (Check test configuration)

### Example Output

```
- Mutation testing complete
- 150 mutations tested
- 120 killed (80% mutation score)
- 25 survived (17%)
- 5 timeout (3%)

Mutation score: 80%
Target: 85%
```

## Improving Mutation Score

If mutations survive, it means tests aren't catching certain edge cases:

1. **Identify surviving mutations**: `mutmut show`
2. **Understand the mutation**: What code path wasn't tested?
3. **Add targeted tests**: Cover the uncovered edge case
4. **Re-run mutation testing**: Verify improvement

### Common Survival Patterns

```python
# Example: Mutation survives because tests don't check error handling

# Original code
def process_data(data):
    if not data:
        raise ValueError("Data cannot be empty")
    return transform(data)

# Mutation: Change `not data` to `data`
# If tests don't test empty data case, mutation survives

# Fix: Add test for empty data
def test_process_data_empty():
    with pytest.raises(ValueError):
        process_data([])
```

## CI/CD Integration

Add mutation testing to your CI pipeline:

```yaml
# GitHub Actions example
- name: Run mutation testing
  run: |
    python scripts/run-mutation-testing.py quick secondbrain.module
    mutmut results
    
- name: Upload mutation results
  uses: actions/upload-artifact@v3
  with:
    name: mutation-results
    path: .mutmut-cache
```

## Best Practices

1. **Start small**: Test one module at a time
2. **Target 80%+**: Aim for mutation score ≥ 80%
3. **Focus on critical paths**: Prioritize core business logic
4. **Don't over-test**: Some mutations are intentional (e.g., performance optimizations)
5. **Run periodically**: Not on every commit (too slow)

## Troubleshooting

### Tests Timeout

```bash
# Increase timeout
mutmut run --swallow-timeout
```

### Tests Fail on Mutations

This is expected! Mutations should cause test failures.

### Memory Issues

```bash
# Run on smaller modules first
mutmut run --paths-to-mutate secondbrain.utils
```

### Slow Execution

```bash
# Use parallel workers
mutmut run -n 4  # 4 parallel workers
```

## Related Tools

- **cosmic-ray**: Alternative mutation testing tool
- **mutmut**: Current tool (fast, Python-native)
- **pytest-mutmut**: pytest plugin for mutation testing

## Resources

- [Mutmut Documentation](https://mutmut.readthedocs.io/)
- [Mutation Testing Principles](https://mutationtesting.org/)
- [Testing Strategies in Production](https://martinfowler.com/articles/testing-in-production.html)

---

**Last Updated**: May 30, 2026  
**Tool Version**: mutmut 3.5.0
