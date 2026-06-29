# Contributing to SecondBrain

Thank you for your interest in contributing to SecondBrain!

## Ways to Contribute

- **Bug Fixes**: Submit pull requests fixing identified issues
- **Feature Development**: Propose and implement new features
- **Documentation**: Improve docs, examples, and inline comments
- **Testing**: Expand test coverage for edge cases
- **Reviews**: Review and test pull requests from others

## Getting Started

### 1. Fork and Clone

Fork the repository on GitHub, then clone locally:

```bash
git clone https://github.com/your-username/secondbrain.git
cd secondbrain
```

### 2. Set Up Development Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Create a Feature Branch

Work on a dedicated branch for each change:

```bash
git checkout -b feature/add-async-batch-search
# or
git checkout -b fix/search-results-sorting
```

## Development Workflow

### 1. Write Code

Follow the [Code Standards](code-standards.md) guide.

### 2. Run Tests

Ensure existing tests pass and add tests for new functionality:

```bash
# All tests
pytest

# With coverage
pytest --cov=secondbrain --cov-fail-under=75

# Watch for changes
pytest --watch
```

### 3. Run Linters

Format and check code:

```bash
# Format
ruff format src/

# Lint
ruff check src/

# Type check
mypy src/secondbrain/
```

### 4. Commit Changes

Use conventional commit format:

```bash
git add .
git commit -m "feat: add async search with batch support"
```

### 5. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Open a pull request on GitHub with:

- Clear description of the change
- Link to related issues
- Evidence tests pass

## Pull Request Checklist

- [ ] Code follows style guidelines (ruff, mypy)
- [ ] Tests pass: `pytest`
- [ ] Coverage maintained or improved
- [ ] Documentation updated if user-facing
- [ ] Commit messages follow convention
- [ ] PR description explains motivation and approach

## Issue Reporting

When filing issues, include:

1. **Environment**: OS, Python version, SecondBrain version
2. **Reproduction**: Steps to reproduce the behavior
3. **Expected vs Actual**: What you expected versus what happened
4. **Logs**: Relevant log output (with sensitive data redacted)

Issue templates available on GitHub.

## Code Review Process

Pull requests require:

- At least one approved review
- Passing CI checks
- No unresolved conversations

Reviewers check for:

- Correctness and completeness
- Test coverage
- Side effects and edge cases
- Adherence to project conventions

## Questions

For questions about contributing:

- GitHub Discussions
- GitHub Issues (labeled `question`)