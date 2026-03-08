# AGENTS.md - Agent Coding Guidelines

This file provides guidelines for agentic coding agents operating in this repository.

---

## Project Overview

This is a Python CLI project with best practices for CLI application development.

---

## Build / Lint / Test Commands

### Running the Application
```bash
# Install runtime dependencies
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run the CLI
python -m <package_name> [command] [options]

# Or if entry point is configured
<cli-name> [command] [options]
```

### Linting & Code Quality
```bash
# Run linting (ruff)
ruff check .

# Run formatting (ruff)
ruff format .

# Run mypy type checking
mypy .

# Run all checks
ruff check . && ruff format --check . && mypy .
```

### Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=<package_name> --cov-report=html

# Run a single test file
pytest tests/test_filename.py

# Run a single test by name
pytest tests/test_filename.py::test_function_name

# Run tests matching a pattern
pytest -k "test_pattern"

# Run with verbose output
pytest -v

# Run with detailed failure output
pytest -vv
```

### Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate  # Windows

# Install dependencies (runtime only)
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

---

## Code Style Guidelines

### Import Conventions

1. **Standard Library First, Then Third-Party, Then Local**
   ```python
   import os
   import sys
   from pathlib import Path
   
   import click
   from typing_extensions import Protocol
   
   from . import utils
   from .core import BaseClass
   ```

2. **Avoid Relative Imports When Possible**
   Use absolute imports for clarity:
   ```python
   # Good
   from mypackage.core import engine
   
   # Avoid
   from .core import engine
   ```

3. **Sort Imports Alphabetically Within Groups**
   ```python
   # Good
   import click
   import rich
   from typing import Any, Dict, List, Optional
   ```

### Formatting

- **Line Length**: 88 characters (ruff default)
- **Indentation**: 4 spaces
- **No Trailing Whitespace**: Always remove
- **Blank Lines**: Two between top-level definitions, one between methods
- **Quotes**: Use double quotes `"string"` for regular strings, single quotes `'char'` for single characters

### Type Annotations

1. **Always Use Type Hints**
   ```python
   def process_data(users: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
       ...
   ```

2. **Use Type Aliases for Complex Types**
   ```python
   UserDict = Dict[str, str]
   ResultTuple = Tuple[int, Optional[str], List[Any]]
   ```

3. **Return Type `None` Instead of Omitting**
   ```python
   def log_message(message: str) -> None:  # Not just "-> None" is fine
       ...
   ```

### Naming Conventions

| Element | Convention | Example |
|--------|----------|--------|
| Variables | snake_case | `user_name`, `max_count` |
| Functions | snake_case | `get_user_by_id()` |
| Classes | PascalCase | `UserManager`, `ConfigLoader` |
| Constants | UPPER_SNAKE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Modules | snake_case | `user_service.py` |
| Packages | snake_case | `my_package` |

### Error Handling

1. **Use Specific Exception Types**
   ```python
   # Good - specific
   raise ValueError("Invalid email format")
   raise FileNotFoundError(f"Config file not found: {path}")
   
   # Avoid - generic
   raise Exception("Something went wrong")
   ```

2. **Never Use Bare `except`**
   ```python
   # Good
   except FileNotFoundError:
       ...
   except (ValueError, TypeError) as e:
       logger.error(f"Invalid input: {e}")
   
   # Avoid
   except:
       ...
   ```

3. **Always Handle Exceptions Explicitly**
   ```python
   # Good
   try:
       result = process()
   except ProcessingError as e:
       logger.warning(f"Processing failed: {e}")
       raise
   
   # Avoid - empty catch
   try:
       result = process()
   except ProcessingError:
       pass
   ```

4. **Provide Context in Error Messages**
   ```python
   # Good
   raise ConfigurationError(
       f"Invalid timeout value '{value}' in config file. "
       f"Expected positive integer, got '{type(value).__name__}'."
   )
   ```

### CLI Design (Click)

1. **Use Click Decorators**
   ```python
   @click.group()
   @click.option('--verbose', is_flag=True, help='Enable verbose output')
   def cli(verbose: bool):
       ...
   
   @cli.command()
   @click.option('--output', type=click.Path(), help='Output file')
   @click.argument('input_file', type=click.Path(exists=True))
   def process(output: str, input_file: str):
       ...
   ```

2. **Use Rich for Terminal Output**
   ```python
   from rich.console import Console
   from rich.table import Table
   
   console = Console()
   
   table = Table(title="Results")
   table.add_column("Name")
   table.add_row("Test")
   console.print(table)
   ```

---

## File Organization

```
project/
├── src/
│   └── package_name/
│       ├── __init__.py
│       ├── cli.py           # Entry point
│       ├── core/            # Core logic
│       ├── utils/           # Utilities
│       └── models/          # Data models
├── tests/
│   ├── test_core/
│   ├── test_utils/
│   └── conftest.py
├── pyproject.toml
└── README.md
```

---

## Configuration (pyproject.toml)

Use pyproject.toml for all project configuration:
```toml
[project]
name = "package-name"
version = "0.1.0"

[tool.ruff]
line-length = 88
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
```

---

## Git Conventions

- **Commits**: Use conventional commits format
  ```
  feat: add user authentication
  fix: resolve timeout issue in CLI
  docs: update README
  refactor: simplify config loading
  ```
- **Branches**: `feature/description`, `fix/description`, `hotfix/description`
- **PRs**: Include summary, motivation, and testing steps

---

## Testing Guidelines

1. **Use pytest fixtures for setup**
   ```python
   @pytest.fixture
   def mock_config(tmp_path):
       config_file = tmp_path / "config.json"
       config_file.write_text('{"key": "value"}')
       return config_file
   ```

2. **Test Behavior, Not Implementation**
   ```python
   # Good - test outcome
   def test_cli_outputs_formatted_table():
       result = runner.invoke(cli, ['list'])
       assert "Column1" in result.output
   
   # Avoid - test implementation details
   def test_cli_calls_formatter():
       ...
   ```

3. **Use parametrize for multiple test cases**
   ```python
   @pytest.mark.parametrize("input,expected", [
       ("a", "A"),
       ("b", "B"),
   ])
   def test_uppercase(input, expected):
       assert uppercase(input) == expected
   ```

---

## Dependencies

- **Runtime**: Keep minimal
- **Dev**: Testing, linting, type checking
- **Avoid**: Unnecessary dependencies

---

## Key Principles

1. **Clarity Over Cleverness**: Write readable code
2. **Fail Fast**: Validate inputs early
3. **Type Safety**: Use mypy, no `Any` without justification
4. **Testing**: Test critical paths, not trivial functions
5. **Documentation**: Docstrings for public APIs
6. **Error Messages**: Helpful, actionable, contextual

---

## CI/CD & Automation Policy

### GitHub Actions Policy: PROHIBITED

**GitHub Actions is explicitly PROHIBITED for this project. Agents MUST NOT:**

- Create `.github/workflows/` directories
- Add CI/CD pipeline configurations
- Set up automated testing workflows
- Configure push/PR hooks
- Add release automation
- Integrate with GitHub's CI/CD features

**Reason**: This is a local development project with minimal deployment needs. CI/CD overhead is unnecessary and contradicts the project's 12-factor app design philosophy focused on local development workflow.

**What to Do Instead**:

1. **Local Development Flow**: Agents should focus on ensuring code quality through:
   - Running `ruff check .` and `ruff format .` before committing
   - Running `mypy .` for type safety
   - Running `pytest` locally for testing
   - Using `pre-commit` hooks for validation

2. **Documentation > Automation**: Focus on comprehensive documentation in README.md and docstrings rather than automated CI/CD pipelines.

3. **Developer Responsibility**: Code quality checks should be performed by developers locally before commits, enforced by pre-commit hooks.

**If Agent Sees GitHub Actions Reference Request**:
- Do NOT implement
- Explain the project's local development philosophy
- Suggest local validation commands instead

**Example Response**:
```
Under project policy, GitHub Actions is explicitly prohibited. This is a local development CLI tool with 12-factor app principles. 

The pre-commit hooks and local validation commands (ruff check, mypy, pytest) are sufficient for quality assurance. No CI/CD infrastructure is needed or desired.
```
