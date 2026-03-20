# Python CLI Best Practices Checklist

Checklist for building production-ready Python CLIs with Click.

## Command Structure

- [ ] Use Click for CLI framework
- [ ] Organize commands with groups
- [ ] Provide helpful help text
- [ ] Use subcommands for related functionality
- [ ] Support `--help` on all commands

## Options & Arguments

- [ ] Use appropriate types for options
- [ ] Provide default values
- [ ] Validate user input
- [ ] Use enums for fixed choices
- [ ] Support environment variables

### Example

```python
@click.command()
@click.option("--chunk-size", type=int, default=4096, help="Chunk size in characters")
@click.option("--verbose", is_flag=True, help="Enable verbose output")
@click.argument("path", type=click.Path(exists=True))
def ingest(path: str, chunk_size: int, verbose: bool):
    """Ingest documents from PATH."""
```

## Error Handling

- [ ] Use specific exception types
- [ ] Provide clear error messages
- [ ] Exit with appropriate codes
- [ ] Don't expose stack traces in production
- [ ] Log errors appropriately

### Example

```python
class CLIError(click.ClickException):
    """Base CLI exception."""
    exit_code = 1
    
    def show(self, file=None):
        click.echo(f"Error: {self.format_message()}", err=True)
```

## Output Formatting

- [ ] Use Rich for terminal output
- [ ] Support multiple output formats (table, json)
- [ ] Provide progress indicators for long operations
- [ ] Use colors appropriately
- [ ] Support quiet mode

### Example

```python
from rich.console import Console
from rich.table import Table

console = Console()

def display_results(results):
    table = Table(title="Results")
    table.add_column("ID")
    table.add_column("Score")
    for result in results:
        table.add_row(result.id, f"{result.score:.3f}")
    console.print(table)
```

## Configuration

- [ ] Support `.env` files
- [ ] Use environment variables
- [ ] Provide sensible defaults
- [ ] Validate configuration
- [ ] Document all options

## Testing

- [ ] Use Click's CliRunner
- [ ] Test all commands
- [ ] Test error cases
- [ ] Mock external dependencies
- [ ] Test output formatting

### Example

```python
from click.testing import CliRunner

def test_ingest_command():
    runner = CliRunner()
    result = runner.invoke(ingest, ["./docs/"])
    assert result.exit_code == 0
    assert "Successfully ingested" in result.output
```

## Documentation

- [ ] Document all commands
- [ ] Provide examples
- [ ] Explain options clearly
- [ ] Update docs with changes
- [ ] Include troubleshooting

## Performance

- [ ] Use async for I/O operations
- [ ] Support parallel processing
- [ ] Provide progress feedback
- [ ] Handle large inputs gracefully
- [ ] Cache where appropriate

## Security

- [ ] Validate all inputs
- [ ] Sanitize file paths
- [ ] Don't expose sensitive data
- [ ] Use secure defaults
- [ ] Handle errors securely

## Release Checklist

- [ ] All tests pass
- [ ] Documentation updated
- [ ] Version bumped
- [ ] Changelog updated
- [ ] Help text reviewed
- [ ] Examples tested

## Common Patterns

### Progress Indicator

```python
from rich.progress import Progress

with Progress() as progress:
    task = progress.add_task("Ingesting...", total=len(documents))
    for doc in documents:
        process(doc)
        progress.update(task, advance=1)
```

### JSON Output

```python
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
def list_docs(format: str):
    if format == "json":
        click.echo(json.dumps(results))
    else:
        display_table(results)
```

## Next Steps

- [Click Documentation](https://click.palletsprojects.com/)
- [Rich Documentation](https://rich.readthedocs.io/)
