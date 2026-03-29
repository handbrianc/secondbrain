# Contributing Guide

Detailed contribution guidelines for SecondBrain developers.

## Code Review Process

### Pull Request Workflow

1. **Fork & Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make Changes**
   - Follow code standards
   - Add tests
   - Update documentation

3. **Run Checks**
   ```bash
   ruff check .
   ruff format .
   mypy .
   pytest
   ```

4. **Commit**
   ```bash
   git commit -m "feat: add your feature"
   ```

5. **Push & Create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style

### Formatting

- **Line Length**: 88 characters
- **Indentation**: 4 spaces
- **Quotes**: Double quotes
- **Imports**: Sorted alphabetically

### Type Hints

```python
from typing import List, Optional, Dict, Any

def process_documents(
    documents: List[Dict[str, Any]],
    max_results: Optional[int] = None
) -> List[Document]:
    ...
```

### Docstrings

```python
def search_documents(
    query: str,
    limit: int = 10
) -> List[Document]:
    """Search documents by semantic similarity.
    
    Args:
        query: Search query text
        limit: Maximum number of results
    
    Returns:
        List of matching documents
    
    Raises:
        ValueError: If query is empty
    """
    ...
```

## Testing Guidelines

### Write Tests For

- New features
- Bug fixes
- Edge cases
- Public APIs

### Test Structure

```python
import pytest
from secondbrain import Document

def test_document_creation():
    """Test document can be created."""
    doc = Document(id="1", title="Test", content="Content")
    assert doc.id == "1"
    assert doc.title == "Test"
```

### Test Coverage

- Aim for 90%+ coverage
- Test both success and failure paths
- Use fixtures for setup

## Documentation Standards

### Docstrings

All public functions and classes must have docstrings.

### README Updates

Update README.md for:
- New features
- API changes
- Configuration changes

### Examples

Provide code examples for:
- New CLI commands
- API usage patterns
- Common workflows

## Commit Messages

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code restructuring
- `test`: Tests
- `chore`: Maintenance

### Examples

```
feat(search): add fuzzy search support

Add Levenshtein distance calculation for 
fuzzy matching of search terms.

Closes #123
```

## Review Checklist

### For Authors

- [ ] Code follows style guidelines
- [ ] Tests added for new features
- [ ] Documentation updated
- [ ] No type errors (`mypy .`)
- [ ] All tests pass (`pytest`)
- [ ] Linting passes (`ruff check .`)

### For Reviewers

- [ ] Code is correct
- [ ] Tests are adequate
- [ ] Documentation is clear
- [ ] No security issues
- [ ] Performance is acceptable
- [ ] Follows project conventions

## Common Tasks

### Adding a New Feature

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes
# Write tests
# Update docs

# Commit
git commit -m "feat: add new feature"

# Push
git push origin feature/new-feature
```

### Fixing a Bug

```bash
# Create bugfix branch
git checkout -b fix/bug-description

# Fix the bug
# Add test for the bug
# Verify test fails without fix

# Commit
git commit -m "fix: resolve bug description"

# Push
git push origin fix/bug-description
```

## Getting Help

- 📖 Read documentation
- 💬 Ask in GitHub Discussions
- 🐛 Open issue for bugs
- 📧 Email maintainers

## Code of Conduct

Please follow our [Code of Conduct](../CODE_OF_CONDUCT.md) in all interactions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
