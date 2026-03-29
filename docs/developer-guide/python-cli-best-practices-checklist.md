# Python CLI Best Practices Checklist

Best practices for building Python CLI applications with Click.

## Command Structure

### Command Organization

```python
import click

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose: bool):
    """SecondBrain CLI."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--recursive', '-r', is_flag=True, help='Process directories')
@click.pass_context
def ingest(ctx, path: str, recursive: bool):
    """Ingest documents."""
    if ctx.obj['verbose']:
        click.echo(f"Ingesting {path}")
    # Implementation...
```

### Command Groups

```python
# Logical grouping
@cli.group()
def document():
    """Document management commands."""
    pass

@document.command()
def list():
    """List all documents."""
    pass

@document.command()
@click.argument('id')
def delete(id: str):
    """Delete a document."""
    pass
```

## Options and Arguments

### Argument Types

```python
# Path with validation
@click.argument('path', type=click.Path(exists=True, file_okay=True, dir_okay=False))

# Multiple values
@click.option('--tags', '-t', multiple=True, help='Document tags')

# Choice options
@click.option('--format', '-f', type=click.Choice(['json', 'csv', 'text']))

# File handling
@click.option('--output', '-o', type=click.File('w'), default='-')  # stdout
```

### Validation

```python
def validate_positive(ctx, param, value):
    if value is not None and value <= 0:
        raise click.BadParameter("Must be positive")
    return value

@click.option('--limit', '-l', callback=validate_positive, default=10)
```

## Output Formatting

### Rich Integration

```python
from rich.console import Console
from rich.table import Table

console = Console()

def display_documents(documents):
    table = Table(title="Documents")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Created")
    
    for doc in documents:
        table.add_row(doc.id, doc.title, doc.created_at.isoformat())
    
    console.print(table)
```

### Progress Bars

```python
@click.command()
@click.argument('files', nargs=-1)
def process_files(files):
    """Process multiple files."""
    with click.progressbar(files, label='Processing files') as bar:
        for file in bar:
            process_file(file)
```

## Error Handling

### Custom Exceptions

```python
class SecondBrainError(click.ClickException):
    exit_code = 1

class DocumentNotFoundError(SecondBrainError):
    def __init__(self, doc_id):
        super().__init__(f"Document not found: {doc_id}")
```

### Error Messages

```python
try:
    doc = storage.get_document(doc_id)
except DocumentNotFoundError as e:
    click.echo(click.style(str(e), fg='red'), err=True)
    ctx.exit(1)
```

## Configuration

### Config File Support

```python
import yaml

def load_config(ctx, param, value):
    if value:
        with open(value) as f:
            config = yaml.safe_load(f)
        ctx.obj.update(config)
    return value

@click.option('--config', '-c', callback=load_config, expose_value=False)
```

### Environment Variables

```python
@click.command()
@click.option('--uri', envvar='MONGODB_URI', help='MongoDB connection string')
def connect(uri: str):
    """Connect to MongoDB."""
    pass
```

## Help Text

### Comprehensive Help

```python
@click.command()
@click.option(
    '--limit', '-l',
    default=10,
    show_default=True,
    help='Maximum number of results to return'
)
@click.option(
    '--format', '-f',
    type=click.Choice(['json', 'text', 'csv']),
    default='text',
    help='Output format'
)
def search(limit: int, format: str):
    """Search documents by semantic similarity.
    
    Search for documents matching the query using semantic similarity.
    Results are ranked by relevance.
    
    Examples:
    
        secondbrain search "machine learning"
        secondbrain search "python tutorials" --limit 20
        secondbrain search "data science" --format json
    """
    pass
```

## Testing CLI

### CliRunner

```python
from click.testing import CliRunner

def test_ingest_command():
    runner = CliRunner()
    result = runner.invoke(cli, ['ingest', 'test.pdf'])
    
    assert result.exit_code == 0
    assert "Ingested" in result.output
```

### Testing with Files

```python
def test_ingest_with_temp_file():
    runner = CliRunner()
    
    with runner.isolated_filesystem():
        # Create test file
        with open('test.pdf', 'w') as f:
            f.write('dummy content')
        
        result = runner.invoke(cli, ['ingest', 'test.pdf'])
        assert result.exit_code == 0
```

## Performance Tips

### Lazy Loading

```python
@click.command()
@click.option('--lazy', is_flag=True, help='Lazy load models')
def search(lazy: bool):
    """Search with optional lazy loading."""
    if not lazy:
        load_models()  # Eager load
    # Otherwise, models load on first use
```

### Batch Operations

```python
@click.command()
@click.argument('files', nargs=-1)
def batch_ingest(files):
    """Ingest multiple files efficiently."""
    if len(files) > 10:
        click.echo(f"Batch ingesting {len(files)} files...")
        # Use batch API
```

## Common Patterns

### Interactive Prompts

```python
@click.command()
def delete_all():
    """Delete all documents (interactive)."""
    if not click.confirm('Are you sure you want to delete all documents?'):
        click.echo('Aborted.')
        return
    # Proceed with deletion
```

### Confirmation

```python
@click.command()
def reset():
    """Reset database."""
    click.echo('This will delete all data.')
    if not click.confirm('Continue?', abort=True):
        click.echo('Aborted.')
```

## See Also

- [CLI Reference](../user-guide/cli-reference.md)
- [Click Documentation](https://click.palletsprojects.com/)
- [Code Standards](code-standards.md)
