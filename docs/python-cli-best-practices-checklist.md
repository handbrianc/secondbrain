# Python CLI Best Practices Checklist

A comprehensive benchmark for evaluating Python CLI project quality against industry standards. Use this checklist to assess your project's adherence to best practices for CLI development.

---

## Table of Contents

1. [CLI Framework & Architecture](#1-cli-framework--architecture)
2. [Type Safety Standards](#2-type-safety-standards)
3. [Error Handling & Exit Codes](#3-error-handling--exit-codes)
4. [Testing Standards](#4-testing-standards)
5. [User Experience & Output](#5-user-experience--output)
6. [Security & Configuration](#6-security--configuration)
7. [Code Organization & Packaging](#7-code-organization--packaging)
8. [Common Anti-Patterns](#8-common-anti-patterns)

---

## 1. CLI Framework & Architecture

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Framework Choice** | Use Click (mature, flexible) or Typer (modern, type-hint-driven) instead of argparse for complex CLIs | Required |
| **Decorator-Based Commands** | Use `@click.command()` and `@click.group()` decorators for CLI entry points | Required |
| **Subcommand Structure** | Organize related commands into subcommand groups using `@click.group()` | Required |
| **Option Definitions** | Use `@click.option()` for flags and optional arguments, `@click.argument()` for positional arguments | Required |
| **Entry Points** | Configure proper console script entry points in `pyproject.toml` | Required |
| **Modular Command Organization** | Separate commands into different modules/files and import into main CLI group | Recommended |
| **Command Callback Pattern** | Use Typer subapps (`typer.Typer()`) for composable command groups | Recommended |

**Example: Proper Click Command Structure**

```python
import click
from click import ClickException

@click.group()
@click.option('--debug/--no-debug', default=False, help='Enable debug mode')
@click.pass_context
def cli(ctx, debug):
    """Main CLI entry point."""
    ctx.ensure_object(dict)
    ctx.obj['DEBUG'] = debug

@cli.command()
@click.option('--name', '-n', required=True, help='Name to greet')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def greet(ctx, name, verbose):
    """Greet a user by name."""
    if ctx.obj['DEBUG']:
        click.echo(f"Debug: Greeting {name}")
    click.echo(f"Hello, {name}!")
```

---

## 2. Type Safety Standards

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Type Hints on All Functions** | Add type hints to all CLI command functions and parameters | Required |
| **Use Click Types** | Use built-in Click types: `click.Choice()`, `click.Path()`, `click.IntRange()`, `click.FloatRange()` | Required |
| **Custom Parameter Types** | Create `click.ParamType` subclasses for complex validation | Recommended |
| **Return Type Annotations** | Add return type annotations to all command functions | Required |
| **Strict mypy Checking** | Run mypy with strict mode enabled | Recommended |
| **Union Types for Optional** | Use `Optional[T]` or `T | None` for optional parameters | Required |
| **Enum for Choices** | Use Python enums for enumerated option choices | Recommended |

**Example: Type-Safe Click Options**

```python
import click
from enum import Enum
from pathlib import Path
from typing import Optional

class OutputFormat(str, Enum):
    json = "json"
    csv = "csv"
    text = "text"

@click.command()
@click.option('--format', '-f', type=click.Choice([f.value for f in OutputFormat]), 
              default='json', help='Output format')
@click.option('--limit', '-l', type=int, default=10, help='Limit results')
@click.option('--output', '-o', type=click.Path(writable=True), 
              help='Output file path')
@click.argument('query', type=str)
def search(query: str, format: str, limit: int, output: Optional[Path]) -> None:
    """Search for documents matching QUERY."""
    # Implementation here
    pass

# Custom validation type example
class EmailType(click.ParamType):
    name = "email"
    
    def convert(self, value, param, ctx):
        import re
        pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        if not re.match(pattern, value):
            self.fail(f'{value} is not a valid email address', param, ctx)
        return value

EMAIL = EmailType()
```

---

## 3. Error Handling & Exit Codes

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Use ClickException** | Raise `click.ClickException` or subclasses for user errors | Required |
| **Consistent Exit Codes** | Use standard exit codes: 0 (success), 1 (error), 2 (usage error) | Required |
| **Help on Usage Error** | Return exit code 2 and show help when user input is incorrect | Required |
| **Custom Error Messages** | Provide clear, actionable error messages | Required |
| **No Raw Stack Traces** | Never expose raw Python tracebacks to end users | Required |
| **Use BadParameter** | Use `click.BadParameter` for parameter-specific validation errors | Required |
| **Stderr Output** | Use `click.echo(message, err=True)` for error messages | Required |
| **Graceful Degradation** | Handle exceptions gracefully with informative messages | Required |

**Example: Proper Error Handling**

```python
import click
import sys

@click.command()
@click.argument('config', type=click.Path(exists=True))
def validate_config(config: str) -> None:
    """Validate configuration file."""
    try:
        data = load_config(config)
    except FileNotFoundError:
        raise click.ClickException(f"Configuration file not found: {config}")
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in config: {e}")
    except ValidationError as e:
        raise click.BadParameter(str(e), param='config')
    
    click.echo("Configuration is valid!", err=True)

# Exit code constants
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE_ERROR = 2
```

---

## 4. Testing Standards

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Use CliRunner** | Use `click.testing.CliRunner` for invoking CLI commands in tests | Required |
| **Test Exit Codes** | Assert correct exit codes (0, 1, 2) for success/error cases | Required |
| **Test Output** | Verify stdout and stderr content in tests | Required |
| **Isolated Filesystem** | Use `CliRunner.isolated_filesystem()` for file operation tests | Required |
| **Test Prompts** | Test interactive prompts using `input=` parameter in invoke | Recommended |
| **Fixtures** | Create reusable fixtures in `conftest.py` | Recommended |
| **Parameterized Tests** | Use pytest parametrization for multiple input combinations | Recommended |
| **Mock External Dependencies** | Mock file I/O, API calls, and external services | Required |
| **Coverage Target** | Aim for >80% test coverage on CLI layer | Recommended |

**Example: Comprehensive CLI Testing**

```python
import pytest
from click.testing import CliRunner
from my_cli import cli

@pytest.fixture
def runner():
    return CliRunner()

def test_cli_help(runner):
    """Test that --help displays correctly."""
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'Usage:' in result.output
    assert '--verbose' in result.output

def test_greet_with_name(runner):
    """Test greet command with name argument."""
    result = runner.invoke(cli, ['greet', '--name', 'World'])
    assert result.exit_code == 0
    assert 'Hello, World!' in result.output

def test_missing_required_argument(runner):
    """Test error when required argument is missing."""
    result = runner.invoke(cli, ['greet'])
    assert result.exit_code == 2
    assert 'Missing argument' in result.output

def test_invalid_option_value(runner):
    """Test error handling for invalid option values."""
    result = runner.invoke(cli, ['process', '--count', 'abc'])
    assert result.exit_code == 2
    assert 'Invalid value' in result.output

def test_file_operations(runner):
    """Test CLI with file operations using isolated filesystem."""
    with runner.isolated_filesystem():
        # Create test file
        with open('input.txt', 'w') as f:
            f.write('test data')
        
        # Run CLI command
        result = runner.invoke(cli, ['process', 'input.txt', '--output', 'output.txt'])
        
        assert result.exit_code == 0
        assert Path('output.txt').exists()

def test_interactive_prompt(runner):
    """Test interactive prompt input."""
    result = runner.invoke(
        cli, 
        ['create', '--name', 'project'],
        input='y\n'  # Simulate 'y' response to prompt
    )
    assert result.exit_code == 0
```

---

## 5. User Experience & Output

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Use click.echo()** | Use `click.echo()` instead of `print()` for output | Required |
| **Rich Output** | Use Rich library for colored output, tables, and progress bars | Recommended |
| **Help Documentation** | Include docstrings that become automatic help text | Required |
| **Help Examples** | Include usage examples in command docstrings | Recommended |
| **Progress Indicators** | Show progress for long-running operations | Recommended |
| **Verbose Mode** | Implement `--verbose` / `-v` flag for detailed output | Recommended |
| **Colored Errors** | Use `click.style()` for colored error messages | Recommended |
| **Confirmation Prompts** | Use `click.confirm()` for destructive operations | Recommended |

**Example: Rich CLI Output**

```python
import click
from rich.console import Console
from rich.table import Table

console = Console()

@click.command()
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def list_items(verbose):
    """List all items with rich formatting."""
    table = Table(title="Items", show_header=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="yellow")
    
    items = get_items()  # Your data retrieval
    
    for item in items:
        table.add_row(str(item.id), item.name, item.status)
    
    console.print(table)
    
    if verbose:
        click.echo(f"Total items: {len(items)}")
```

---

## 6. Security & Configuration

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **No Hardcoded Secrets** | Never hardcode API keys, passwords, or tokens | Required |
| **Environment Variables** | Use environment variables for sensitive configuration | Required |
| **Config Files** | Support configuration files with sensible defaults | Recommended |
| **Validation at Boundaries** | Validate all inputs at CLI layer before processing | Required |
| **Secure File Handling** | Use `click.Path()` with `exists=True` for file inputs | Required |
| **Principle of Least Privilege** | Request only necessary permissions and options | Recommended |

**Example: Secure Configuration**

```python
import click
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

class Config(BaseModel):
    api_key: str
    endpoint: str = "https://api.example.com"
    timeout: int = 30

def load_config() -> Config:
    """Load configuration from environment."""
    api_key = os.getenv('API_KEY')
    if not api_key:
        raise click.ClickException("API_KEY environment variable is required")
    
    return Config(
        api_key=api_key,
        endpoint=os.getenv('API_ENDPOINT', "https://api.example.com"),
        timeout=int(os.getenv('TIMEOUT', '30'))
    )

@click.command()
@click.option('--config', type=click.Path(exists=True), help='Config file path')
@click.pass_context
def main(ctx, config: Optional[str]):
    """Main CLI command."""
    cfg = load_config()
    # Use cfg.api_key securely
    pass
```

---

## 7. Code Organization & Packaging

| Criterion | Best Practice | Priority |
|-----------|---------------|----------|
| **Project Structure** | Follow standard Python package structure (`src/package/`) | Required |
| **pyproject.toml** | Use `pyproject.toml` for project configuration | Required |
| **Entry Points** | Define console script entry points in `[project.scripts]` | Required |
| **Version Management** | Single source of truth for version in `__version__` | Required |
| **Separate CLI from Core** | Keep CLI layer separate from business logic | Required |
| **Lazy Loading** | Use lazy imports for heavy dependencies | Recommended |
| **Type Checking** | Run mypy as part of development workflow | Recommended |

**Example: Project Structure**

```
my_cli/
├── src/
│   └── my_cli/
│       ├── __init__.py
│       ├── __version__.py
│       ├── cli.py              # CLI entry point
│       ├── commands/           # Command modules
│       │   ├── __init__.py
│       │   ├── greet.py
│       │   └── process.py
│       ├── core/               # Business logic
│       │   └── __init__.py
│       └── utils/              # Utilities
│           └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   └── commands/
├── pyproject.toml
└── README.md
```

**Example: pyproject.toml Entry Points**

```toml
[project]
name = "my-cli-tool"
version = "1.0.0"
description = "A useful CLI tool"

[project.scripts]
my-cli = "my_cli.cli:main"

[tool.poetry.scripts]  # If using Poetry
my-cli = "my_cli.cli:main"
```

---

## 8. Common Anti-Patterns

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| **Bare `except:`** | Catches everything including `KeyboardInterrupt` | Catch specific exceptions: `except ValueError:` |
| **`except Exception: pass`** | Silently swallows errors | Log error and re-raise or handle appropriately |
| **Using `print()` for logging** | No log levels, timestamps, or formatting | Use `logging` module with proper levels |
| **Hardcoded configuration** | Secrets in source code | Use environment variables or config files |
| **Scattered retry logic** | Duplicated retry logic across modules | Centralize with decorators or client wrappers |
| **Mixed I/O and business logic** | Hard to test and reuse | Separate into layers (CLI → Service → Repository) |
| **No input validation** | Invalid inputs cause runtime errors | Validate at CLI boundaries with Click types |
| **argparse to function drift** | Parser and function signatures diverge | Use Typer or ensure parser matches function |
| **Not using context managers** | Resource leaks | Always use `with` statements |
| **Wide try blocks** | Catches unintended exceptions | Wrap specific operations |

**Example: Anti-Patterns to Avoid**

```python
# BAD: Bare except
try:
    do_something()
except:  # Catches EVERYTHING including KeyboardInterrupt
    pass

# GOOD: Specific exception handling
try:
    do_something()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
    raise click.ClickException(f"Invalid value: {e}")

# BAD: Using print for CLI output
print("Processing...")

# GOOD: Using click.echo
click.echo("Processing...")

# BAD: Hardcoded secrets
API_KEY = "sk-1234567890abcdef"

# GOOD: Environment variable
import os
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise click.ClickException("API_KEY not set")

# BAD: Mixed I/O in CLI command
@click.command()
def process():
    data = fetch_from_api()  # I/O mixed with CLI
    results = transform(data)
    save_to_database(results)  # More I/O

# GOOD: Separated concerns
@click.command()
def process():
    data = api_client.fetch()  # I/O in service layer
    results = transform(data)   # Pure business logic
    storage.save(results)       # I/O in repository layer
```

---

## Quick Reference: Exit Codes

| Code | Meaning | When to Use |
|------|---------|--------------|
| `0` | Success | Command completed successfully |
| `1` | General Error | Unexpected errors, exceptions |
| `2` | Usage Error | Invalid arguments, missing required options, help displayed due to error |

---

## Tools & Dependencies Reference

| Category | Recommended Tools |
|----------|-------------------|
| CLI Framework | Click 8.x, Typer (built on Click) |
| Output Formatting | Rich, blessings, colorama |
| Configuration | pydantic, pydantic-settings, python-dotenv |
| Testing | pytest, pytest-mock, hypothesis |
| Type Checking | mypy, pyright |
| CLI Testing | click.testing.CliRunner, typer.testing |
| Logging | logging (stdlib), loguru |

---

## Running Quality Checks

```bash
# Type checking
mypy .

# Linting
ruff check .
ruff format --check .

# Testing
pytest -v --cov=src --cov-report=html

# All checks
ruff check . && ruff format --check . && mypy . && pytest
```

---

## Assessment Summary

To use this checklist for benchmarking:

1. **Rate Each Criterion**: Mark each item as Pass/Fail/Partial
2. **Calculate Scores**: Weight by priority (Required items count more)
3. **Identify Gaps**: Focus on Required items first
4. **Create Action Plan**: Address highest-impact improvements
5. **Re-evaluate**: Re-assess after implementing changes

**Target Scores**:
- **Production-Ready**: 90%+ on Required items
- **Good Quality**: 80%+ on Required items, 60%+ on Recommended
- **Needs Work**: Below 80% on Required items
