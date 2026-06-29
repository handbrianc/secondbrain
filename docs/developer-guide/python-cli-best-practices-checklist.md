# CLI Best Practices Checklist

Guidelines for designing robust, user-friendly command-line interfaces.

Based on Python CLI expert recommendations, adapted for SecondBrain's implementation.

## Design Principles

### 1. Composability Over Convenience

Design commands that compose naturally:

```bash
# Good: composable primitives
secondbrain ingest ./docs --cores 4
secondbrain search "query" --top-k 10 --format json
secondbrain delete --source "./old.pdf"

# Problematic: convenience that breaks composition
secondbrain sync-and-search --ingest-path ./docs --query "..." --delete-source
```

### 2. Sensible Defaults with Explicit Override

```python
@click.option('--cores', '-c', type=int, default=None,
              help="CPU cores (default: auto-detect)")
@click.option('--chunk-size', type=int, default=None,
              help="Override configured chunk size")
```

Defaults should work for 80% of use cases. Users who need customization should be able to override precisely.

### 3. Fail Fast with Clear Messages

```python
if not any([source, chunk_id, all]):
    raise CLIValidationError(
        "Must specify --source, --chunk-id, or --all"
    )

if sum([bool(source), bool(chunk_id), all]) > 1:
    raise CLIValidationError(
        "Specify only one of --source, --chunk-id, or --all"
    )
```

## Error Handling Patterns

### Centralized Error Handler

```python
from functools import wraps

def handle_cli_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CLIValidationError as e:
            console.print(f"[red]Validation error: {e}[/red]")
            sys.exit(1)
        except ServiceUnavailableError as e:
            console.print(f"[red]Service unavailable: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")
            raise
    return wrapper
```

### Typed Exceptions Hierarchy

```python
class CLIBaseError(Exception):
    """Base exception for CLI errors."""
    pass

class CLIValidationError(CLIBaseError):
    """Invalid user input."""
    pass

class ServiceUnavailableError(CLIBaseError):
    """Required service not available."""
    pass
```

## Output Design

### Structured Output Modes

Support multiple formats for scripting:

```python
@click.option('--format', type=click.Choice(['table', 'json']),
              default='table')
def display_results(format: str):
    if format == 'json':
        console.print_json(data)
    else:
        # Render table
        pass
```

### Status Indicators

Visual feedback for operation outcomes:

```python
console.print("[green]✓ Ingestion complete[/green]")
console.print("[yellow]⚠ Some files skipped[/yellow]")
console.print("[red]✗ Error occurred[/red]")
```

## Feedback Mechanisms

### Progress Indication

For long-running operations:

```python
with console.status("[cyan]Processing...", spinner="dots"):
    results = long_running_operation()
```

### Progress Bars

Track discrete items:

```python
from rich.progress import Progress, BarColumn, TextColumn

with Progress(TextColumn("[progress.description]"), BarColumn()) as progress:
    task = progress.add_task("Processing", total=len(files))
    for f in files:
        process(f)
        progress.advance(task)
```

## Input Validation

### At Declaration Time

Leverage Click's built-in validation:

```python
@click.option('--limit', type=click.IntRange(min=0, max=MAX_LIMIT))
@click.option('--format', type=click.Choice(['table', 'json']))
```

### At Runtime

Explicit validation beyond Click's capabilities:

```python
if cores > os.cpu_count():
    console.print(
        f"[yellow]Warning: {cores} cores requested, "
        f"but only {os.cpu_count()} available[/yellow]"
    )
    cores = os.cpu_count()
```

## Interaction Patterns

### Affirmative Defaults

Ask for destructive actions:

```python
# Bad: accidental deletion
$ secondbrain delete --all

# Good: require confirmation
if not click.confirm("Delete all documents? This cannot be undone."):
    return
```

### Idempotent Flags

Make operations safe to re-run:

```python
# --yes flag bypasses confirmation for scripted use
@click.option('--yes', '-y', is_flag=True)
def delete(all: bool, yes: bool):
    if not yes:
        if not click.confirm("Proceed?"):
            return
```

## Testing CLIs

### Simulate Command Line

```python
from click.testing import CliRunner

def test_ingest_command():
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Setup test file
        Path("test.pdf").touch()
        
        result = runner.invoke(cli.main, ['ingest', 'test.pdf'])
        
        assert result.exit_code == 0
        assert "Successfully ingested" in result.output
```

### Verify Output Format

```python
result = runner.invoke(cli.main, ['search', 'query', '--format', 'json'])

assert result.exit_code == 0
data = json.loads(result.output)
assert isinstance(data, list)
```

## Performance Considerations

### Lazy Imports

Keep startup time fast:

```python
# Defer expensive imports until command execution
def ingest(path: str):
    from secondbrain.document import DocumentIngestor  # Local import
    ...
```

### Caching

Cache expensive computations:

```python
@lru_cache
def get_config() -> Config:
    return Config()
```

## Help Text Quality

### Describe Every Option

```python
@click.option('--min-score', type=float,
              help="Minimum similarity score (0.0-1.0, default: 0.46)")
```

### Provide Examples

```python
@click.command()
@click.argument('query')
def search(query):
    """Search documents with semantic query.

    Examples:
        search "machine learning"
        search "optimization" --top-k 10
        search "guide" --format json
    """
    ...
```

## Deprecation Handling

Signal deprecations clearly:

```python
if old_option_used:
    warnings.warn(
        "'--old-flag' is deprecated, use '--new-flag' instead",
        DeprecationWarning,
        stacklevel=2
    )
```

## Logging Integration

### Structured Logging

```python
logger.info("Operation completed",
            extra={"operation": "ingest", "files": len(files), "duration": elapsed})
```

### Sensitive Data Filtering

Never log sensitive configuration values:

```python
# Bad
logger.debug(f"API key: {api_key}")

# Good
logger.debug(f"API key present: {bool(api_key)}")
```